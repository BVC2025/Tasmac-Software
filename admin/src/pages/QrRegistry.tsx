import { useRef, useState } from 'react'
import { del, patch, post, type Brand, type QrCodeRow } from '../api'
import { readQrCodes } from '../lib/qrImage'
import { Btn, ErrorText, Field, fmtTime, inputCls, mono, Table, usePoll } from '../ui'
import type { PageProps } from './Operations'

type Kind = 'refund' | 'mfg'

const KIND_CLS: Record<string, string> = {
  refund: 'bg-emerald-100 text-emerald-800',
  mfg: 'bg-orange-100 text-orange-800',
}

function KindBadge({ kind }: { kind: QrCodeRow['kind'] }) {
  if (!kind) return <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">Unknown</span>
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${KIND_CLS[kind]}`}>
      {kind === 'refund' ? 'Refund QR' : 'Manufacturing QR'}
    </span>
  )
}

const short = (s: string, n = 48) => (s.length > n ? s.slice(0, n) + '…' : s)

/** Real TASMAC bottle QRs accepted for the demo / pilot, until TASMAC's verification API is connected. */
export function QrRegistry({ can }: PageProps) {
  const [tab, setTab] = useState<'unknown' | 'registered'>('unknown')
  const unknown = usePoll<QrCodeRow[]>('/qr-codes?status=unknown')
  const registered = usePoll<QrCodeRow[]>('/qr-codes?status=registered')
  const { data: brands } = usePoll<Brand[]>('/brands', 0)
  const formRef = useRef<HTMLDivElement>(null)

  const [raw, setRaw] = useState('')
  const [kind, setKind] = useState<Kind>('refund')
  const [brand, setBrand] = useState('')
  const [batch, setBatch] = useState('')
  const [label, setLabel] = useState('')
  const [photoCodes, setPhotoCodes] = useState<string[]>([])
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')

  const operator = can('OPERATOR')
  const reload = () => {
    unknown.reload()
    registered.reload()
  }

  const prefill = (text: string, k: Kind) => {
    setRaw(text)
    setKind(k)
    setErr('')
    setOk('')
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const readPhoto = async (files: FileList | null) => {
    setErr('')
    setPhotoCodes([])
    try {
      const all: string[] = []
      for (const f of Array.from(files ?? [])) all.push(...(await readQrCodes(f)))
      const unique = [...new Set(all)]
      setPhotoCodes(unique)
      if (unique.length === 1) setRaw(unique[0])
      if (!unique.length) setErr('No QR found in the photo. Take it closer, flat and sharp, with good light.')
    } catch {
      setErr('Could not read that file as an image')
    }
  }

  const register = async () => {
    setErr('')
    setOk('')
    try {
      const row = await post<QrCodeRow>('/qr-codes', {
        raw, kind, brand: kind === 'mfg' ? brand : null, batch: kind === 'mfg' && batch ? batch : null, label: label || null,
      })
      setOk(`Registered ${row.kind === 'refund' ? 'refund' : 'manufacturing'} QR - serial ${row.serial}`)
      setRaw('')
      setLabel('')
      setPhotoCodes([])
      reload()
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  const rows = (tab === 'unknown' ? unknown.data : registered.data) ?? []
  const activeBrands = (brands ?? []).filter((b) => b.active)

  return (
    <>
      <div className="mb-5 rounded-xl bg-sky-50 p-4 text-sm text-sky-900 ring-1 ring-sky-100">
        <p>
          <b>For the demo and pilot.</b> Until TASMAC&apos;s own QR verification is connected, a real bottle QR is accepted only
          if it is registered here. Every QR a machine reads but does not recognise appears under <b>Seen by machines</b>.
        </p>
        <p className="mt-1">The one-time-use rule still applies: each refund QR and each bottle is paid only once.</p>
      </div>

      {operator && (
        <div ref={formRef} className="mb-6 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
          <h2 className="mb-3 text-base font-bold text-slate-800">Register a bottle QR</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-3">
              <Field label="QR text (paste from a phone QR scanner app, or read it from a photo)">
                <textarea className={`${inputCls} font-mono`} rows={3} value={raw} onChange={(e) => setRaw(e.target.value)} />
              </Field>
              <Field label="Or read from a photo">
                <input type="file" accept="image/*" multiple onChange={(e) => readPhoto(e.target.files)}
                  className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:font-semibold file:text-slate-700 hover:file:bg-slate-200" />
              </Field>
              {photoCodes.length > 1 && (
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-slate-600">{photoCodes.length} QRs in the photo - pick one:</p>
                  {photoCodes.map((c) => (
                    <button key={c} onClick={() => setRaw(c)}
                      className={`block w-full rounded-lg px-3 py-1.5 text-left font-mono text-xs break-all ring-1 ${raw === c ? 'bg-brand-50 ring-brand-600' : 'ring-slate-200 hover:bg-slate-50'}`}>
                      {c}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="space-y-3">
              <Field label="Type">
                <div className="flex gap-2">
                  {(['refund', 'mfg'] as Kind[]).map((k) => (
                    <button key={k} onClick={() => setKind(k)}
                      className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold ring-1 ${kind === k ? 'bg-brand-700 text-white ring-brand-700' : 'bg-white text-slate-700 ring-slate-300'}`}>
                      {k === 'refund' ? 'Refund QR' : 'Manufacturing QR'}
                    </button>
                  ))}
                </div>
              </Field>
              {kind === 'mfg' && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Brand">
                    <select className={inputCls} value={brand} onChange={(e) => setBrand(e.target.value)}>
                      <option value="">Select…</option>
                      {activeBrands.map((b) => <option key={b.code} value={b.code}>{b.code} - {b.name}</option>)}
                    </select>
                  </Field>
                  <Field label="Batch (optional)">
                    <input className={inputCls} value={batch} onChange={(e) => setBatch(e.target.value)} />
                  </Field>
                </div>
              )}
              <Field label="Label (optional, e.g. 'Demo bottle 3 - 750 ml')">
                <input className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} />
              </Field>
              <div className="flex items-center gap-3">
                <Btn disabled={!raw.trim() || (kind === 'mfg' && !brand)} onClick={register}>Register</Btn>
                {ok && <span className="text-sm font-semibold text-emerald-700">{ok}</span>}
              </div>
              <ErrorText>{err}</ErrorText>
            </div>
          </div>
        </div>
      )}

      <div className="mb-3 flex gap-2">
        {([['unknown', `Seen by machines (${unknown.data?.length ?? 0})`], ['registered', `Registered (${registered.data?.length ?? 0})`]] as const).map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold ${tab === k ? 'bg-brand-700 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-300'}`}>
            {l}
          </button>
        ))}
      </div>

      {tab === 'unknown' ? (
        <Table
          empty="No unknown QRs yet. Insert a real bottle on a machine (or upload its photo in the kiosk DEV panel)."
          head={['QR text', 'Times seen', 'Last seen', 'Machine', '']}
          rows={rows.map((r) => [
            <span className="font-mono text-xs" title={r.raw}>{short(r.raw, 56)}</span>,
            r.seen_count,
            fmtTime(r.last_seen_at),
            mono(r.last_machine_id),
            operator ? (
              <div className="flex flex-wrap gap-2 whitespace-nowrap">
                <Btn variant="secondary" onClick={() => prefill(r.raw, 'refund')}>As refund QR</Btn>
                <Btn variant="secondary" onClick={() => prefill(r.raw, 'mfg')}>As mfg QR</Btn>
                <Btn variant="link" onClick={async () => { await del(`/qr-codes/${r.code_hash}`); reload() }}>Ignore</Btn>
              </div>
            ) : null,
          ])}
        />
      ) : (
        <Table
          empty="Nothing registered yet."
          head={['Type', 'Label / serial', 'Brand', 'QR text', 'Registered', 'Status', '']}
          rows={rows.map((r) => [
            <KindBadge kind={r.kind} />,
            <span>{r.label ?? '—'}<br />{mono(r.serial)}</span>,
            r.brand ? <b>{r.brand}</b> : '—',
            <span className="font-mono text-xs" title={r.raw}>{short(r.raw, 30)}</span>,
            <span className="text-xs">{fmtTime(r.created_at)}<br /><span className="text-slate-500">{r.registered_by}</span></span>,
            r.active ? <span className="font-semibold text-emerald-700">Accepted</span> : <span className="text-red-600">Disabled</span>,
            operator ? (
              <div className="flex gap-3 whitespace-nowrap">
                <Btn variant="link" onClick={async () => { await patch(`/qr-codes/${r.code_hash}`, { active: !r.active }); reload() }}>
                  {r.active ? 'Disable' : 'Enable'}
                </Btn>
                <Btn variant="link" className="text-red-700" onClick={async () => {
                  if (window.confirm('Remove this QR from the registry? Refunds already paid with it stay recorded.')) {
                    await del(`/qr-codes/${r.code_hash}`)
                    reload()
                  }
                }}>Remove</Btn>
              </div>
            ) : null,
          ])}
        />
      )}
    </>
  )
}
