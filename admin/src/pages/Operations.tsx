import { useEffect, useState, type ComponentType, type ReactNode, type SVGProps } from 'react'
import { DailyChart } from '../components/DailyChart'
import {
  AlertIcon, BottleIcon, CameraIcon, CheckCircleIcon, ClockIcon, CopyIcon, DownloadIcon, ExpandIcon, ReturnIcon, RupeeIcon, WifiIcon,
  XCircleIcon,
} from '../components/Icons'
import { fetchImage, post, type AlertRow, type AuditRow, type ClaimRow, type MachineRow, type SessionRow, type SmsRow, type Stats, type TxnRow } from '../api'
import { Badge, Btn, ErrorText, Field, inputCls, Modal, mono, Table, fmtTime, rupees, usePoll } from '../ui'

export interface PageProps {
  can: (role: 'OPERATOR' | 'ADMIN') => boolean
  go: (page: string) => void
}

type Icon = ComponentType<SVGProps<SVGSVGElement>>

interface KpiTheme {
  card: string
  ring: string
  strip: string
  ghost: string
  badge: string
  label: string
  pill: string
}

// Full class strings (Tailwind only generates classes it can see in the source)
const KPI_THEMES: Record<'emerald' | 'sky' | 'amber' | 'violet', KpiTheme> = {
  emerald: {
    card: 'from-white to-emerald-50/70', ring: 'ring-emerald-100', strip: 'from-emerald-500 to-teal-400',
    ghost: 'text-emerald-500/10', badge: 'from-emerald-500 to-emerald-700', label: 'text-emerald-700', pill: 'bg-emerald-100/80 text-emerald-800',
  },
  sky: {
    card: 'from-white to-sky-50/70', ring: 'ring-sky-100', strip: 'from-sky-500 to-cyan-400',
    ghost: 'text-sky-500/10', badge: 'from-sky-500 to-sky-700', label: 'text-sky-700', pill: 'bg-sky-100/80 text-sky-800',
  },
  amber: {
    card: 'from-white to-amber-50/70', ring: 'ring-amber-100', strip: 'from-amber-500 to-orange-400',
    ghost: 'text-amber-500/10', badge: 'from-amber-500 to-orange-600', label: 'text-amber-700', pill: 'bg-amber-100/80 text-amber-900',
  },
  violet: {
    card: 'from-white to-violet-50/70', ring: 'ring-violet-100', strip: 'from-violet-500 to-fuchsia-400',
    ghost: 'text-violet-500/10', badge: 'from-violet-500 to-violet-700', label: 'text-violet-700', pill: 'bg-violet-100/80 text-violet-800',
  },
}

const online = (m: MachineRow) => !!m.last_seen_at && Date.now() - new Date(m.last_seen_at).getTime() < 120_000

export function Overview({ go }: PageProps) {
  const { data: s } = usePoll<Stats>('/stats')
  const { data: machines } = usePoll<MachineRow[]>('/machines')
  const { data: alerts } = usePoll<AlertRow[]>('/alerts?status=OPEN&limit=5')
  const active = (machines ?? []).filter((m) => m.active)

  const kpis: { label: string; value: ReactNode; sub: string; icon: Icon; theme: KpiTheme; page: string }[] = s
    ? [
        { label: 'Refunded today', value: rupees(s.amount_refunded_today_paise), sub: `${s.refunds_success_today} successful payouts`, icon: RupeeIcon, theme: KPI_THEMES.emerald, page: 'transactions' },
        { label: 'Bottles accepted', value: s.bottles_accepted_today, sub: `${s.sessions_today} bottles inserted today`, icon: BottleIcon, theme: KPI_THEMES.sky, page: 'sessions' },
        { label: 'Bottles returned', value: s.bottles_returned_today, sub: 'Rejected or cancelled today', icon: ReturnIcon, theme: KPI_THEMES.amber, page: 'sessions' },
        { label: 'Machines online', value: `${s.machines_online} / ${s.machines_total}`, sub: 'Reported in the last 2 minutes', icon: WifiIcon, theme: KPI_THEMES.violet, page: 'machines' },
      ]
    : []
  const health: { label: string; value: number; icon: Icon; tone: string; page: string }[] = s
    ? [
        { label: 'Payouts pending', value: s.refunds_pending, icon: ClockIcon, tone: 'text-amber-600', page: 'transactions' },
        { label: 'Payouts failed today', value: s.refunds_failed_today, icon: XCircleIcon, tone: 'text-red-600', page: 'transactions' },
        { label: 'Open alerts', value: s.open_alerts, icon: AlertIcon, tone: 'text-red-600', page: 'alerts' },
      ]
    : []

  return (
    <div className="space-y-6">
      {!!alerts?.length && (
        <button onClick={() => go('alerts')} className="flex w-full items-start gap-4 rounded-2xl bg-red-50 p-5 text-left ring-1 ring-red-200 hover:bg-red-100/70">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-100 text-red-600"><AlertIcon className="h-5 w-5" /></span>
          <span>
            <span className="block font-semibold text-red-900">{s?.open_alerts ?? alerts.length} open alert(s) need attention</span>
            {alerts.slice(0, 3).map((a) => <span key={a.id} className="block text-sm text-red-700">{a.message}</span>)}
          </span>
          <span className="ml-auto self-center text-sm font-semibold whitespace-nowrap text-red-700">Review →</span>
        </button>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((k) => (
          <button
            key={k.label}
            onClick={() => go(k.page)}
            className={`group relative overflow-hidden rounded-2xl bg-gradient-to-br ${k.theme.card} p-5 text-left shadow-sm ring-1 ${k.theme.ring} transition hover:-translate-y-0.5 hover:shadow-lg`}
          >
            {/* accent strip */}
            <span className={`absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r ${k.theme.strip}`} />
            {/* large faded icon */}
            <k.icon className={`pointer-events-none absolute -right-4 -bottom-5 h-28 w-28 ${k.theme.ghost}`} strokeWidth={1.2} />

            <div className="relative flex items-center gap-3">
              <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${k.theme.badge} text-white shadow-md`}>
                <k.icon className="h-5 w-5" strokeWidth={2.2} />
              </span>
              <p className={`text-[13px] font-bold tracking-wider uppercase ${k.theme.label}`}>{k.label}</p>
            </div>
            <p className="relative mt-4 text-4xl font-extrabold tracking-tight text-slate-900 tabular-nums">{k.value}</p>
            <div className="relative mt-3 flex items-center justify-between">
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${k.theme.pill}`}>{k.sub}</span>
              <span className={`text-sm font-semibold opacity-0 transition group-hover:opacity-100 ${k.theme.label}`}>View →</span>
            </div>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-2"><DailyChart /></div>
        <div className="flex flex-col gap-3 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div>
            <h3 className="font-semibold text-slate-900">Payout health</h3>
            <p className="text-sm text-slate-500">Anything above zero needs a look</p>
          </div>
          {health.map((h) => (
            <button key={h.label} onClick={() => go(h.page)} className="flex items-center gap-3 rounded-xl px-3 py-3 text-left ring-1 ring-slate-100 hover:bg-slate-50">
              <h.icon className={`h-5 w-5 ${h.value ? h.tone : 'text-slate-300'}`} />
              <span className="flex-1 text-sm text-slate-700">{h.label}</span>
              <span className="text-lg font-bold text-slate-900 tabular-nums">{h.value}</span>
            </button>
          ))}
          <div className="mt-auto flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-3 text-sm text-emerald-800">
            <CheckCircleIcon className="h-5 w-5 shrink-0" /> Each refund QR can be paid only once
          </div>
        </div>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">Machines</h2>
          <button onClick={() => go('machines')} className="text-sm font-semibold text-brand-700 hover:underline">Manage machines →</button>
        </div>
        <Table
          head={['Machine', 'Location', 'Connection', 'State', 'Bin fill', 'Version', 'Last seen']}
          rows={active.map((m) => [
            <b>{m.id}</b>,
            m.location ?? '—',
            online(m)
              ? <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-700"><span className="h-2 w-2 rounded-full bg-emerald-500" />Online</span>
              : <span className="inline-flex items-center gap-1.5 text-slate-400"><span className="h-2 w-2 rounded-full bg-slate-300" />Offline</span>,
            <span title={m.fault_reason ?? ''}><Badge value={m.state} /> {m.fault_reason && <span className="text-xs text-red-600">{m.fault_reason}</span>}</span>,
            <BinBar pct={m.bin_fill_pct} />,
            m.software_version ?? '—',
            fmtTime(m.last_seen_at),
          ])}
          empty="No machines registered yet"
        />
      </div>
    </div>
  )
}

export function BinBar({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-slate-400">—</span>
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full ${pct >= 85 ? 'bg-red-500' : 'bg-brand-600'}`} style={{ width: `${pct}%` }} />
      </div>
      {pct}%
    </div>
  )
}

export function Alerts({ can }: PageProps) {
  const [status, setStatus] = useState('OPEN')
  const { data, reload } = usePoll<AlertRow[]>(`/alerts?limit=200${status ? `&status=${status}` : '&status='}`)
  const [resolving, setResolving] = useState<AlertRow | null>(null)
  return (
    <>
      <Filters value={status} onChange={setStatus} options={[['OPEN', 'Open'], ['RESOLVED', 'Resolved'], ['', 'All']]} />
      <p className="mb-4 text-sm text-slate-500">
        Automatic alerts (offline, fault, bin full, payout stuck) close themselves when the problem clears.
        "Paid bottle returned" needs a person to check and resolve.
      </p>
      <Table
        head={['Raised', 'Severity', 'Type', 'Machine', 'Message', 'Status', 'Resolution', '']}
        rows={(data ?? []).map((a) => [
          fmtTime(a.created_at), <Badge value={a.severity} />, <b className="text-xs">{a.type}</b>, a.machine_id ?? '—',
          <span className="block max-w-md truncate whitespace-normal">{a.message}</span>, <Badge value={a.status} />,
          a.resolved_by ? <span className="text-xs">{a.resolved_by}: {a.note}</span> : '—',
          a.status === 'OPEN' && can('OPERATOR') ? <Btn variant="secondary" onClick={() => setResolving(a)}>Resolve</Btn> : null,
        ])}
        empty={status === 'OPEN' ? 'No open alerts 🎉' : 'No alerts'}
      />
      {resolving && <ResolveModal alert={resolving} onClose={() => setResolving(null)} onDone={reload} />}
    </>
  )
}

function ResolveModal({ alert, onClose, onDone }: { alert: AlertRow; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  const submit = async () => {
    try {
      await post(`/alerts/${alert.id}/resolve`, { note })
      onDone()
      onClose()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <Modal title="Resolve alert" onClose={onClose}>
      <p className="mb-4 text-sm text-slate-600">{alert.message}</p>
      <Field label="What was done? (saved in the audit log)">
        <textarea className={inputCls} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText>{err}</ErrorText>
      <div className="mt-4 flex justify-end gap-2">
        <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
        <Btn disabled={note.trim().length < 3} onClick={submit}>Resolve</Btn>
      </div>
    </Modal>
  )
}

function Filters({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {options.map(([v, label]) => (
        <button key={label} onClick={() => onChange(v)}
          className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${value === v ? 'bg-brand-700 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200'}`}>
          {label}
        </button>
      ))}
    </div>
  )
}

function Search({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return <input className={`${inputCls} mb-4 max-w-sm`} placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
}

export function Transactions({ can }: PageProps) {
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const params = new URLSearchParams({ limit: '200' })
  if (status) params.set('status', status)
  if (q.trim()) params.set('q', q.trim())
  const { data, reload } = usePoll<TxnRow[]>(`/transactions?${params}`)
  const [busy, setBusy] = useState<string | null>(null)
  const recheck = async (id: string) => {
    setBusy(id)
    try {
      await post(`/transactions/${id}/recheck`)
      await reload()
    } finally {
      setBusy(null)
    }
  }
  return (
    <>
      <div className="flex flex-wrap items-start gap-4">
        <Filters value={status} onChange={setStatus} options={[['', 'All'], ['SUCCESS', 'Success'], ['PENDING', 'Pending'], ['FAILED', 'Failed']]} />
        <Search value={q} onChange={setQ} placeholder="Search transaction, refund QR, UPI or mobile" />
      </div>
      <Table
        head={['Created', 'Transaction', 'Machine', 'Amount', 'Destination', 'Payout', 'Bottle', 'SMS', 'Provider ref', 'Failure', '']}
        rows={(data ?? []).map((t) => [
          fmtTime(t.created_at), mono(t.id), t.machine_id, rupees(t.amount_paise),
          <span><span className="text-xs text-slate-400 uppercase">{t.dest_kind}</span> {t.dest_value}</span>,
          <Badge value={t.status} />, <Badge value={t.bottle_status} />, t.sms_sent ? '✓' : '—',
          mono(t.provider_ref), t.failure_reason ?? '—',
          t.status === 'PENDING' && can('OPERATOR') ? (
            <Btn variant="secondary" disabled={busy === t.id} onClick={() => recheck(t.id)}>{busy === t.id ? 'Checking…' : 'Re-check'}</Btn>
          ) : null,
        ])}
      />
    </>
  )
}

const EVIDENCE_REASON: Record<string, { title: string; detail: string }> = {
  BOTTLE_DAMAGED: { title: 'Bottle damaged', detail: 'The camera found damage on the bottle (crack, chip or broken glass).' },
  BOTTLE_FOREIGN: { title: 'Not an accepted bottle', detail: 'The item in the inlet is not a bottle the machine accepts.' },
}

function ReportRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 py-2.5 last:border-0">
      <dt className="shrink-0 text-xs font-semibold tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className="text-right text-sm font-semibold text-slate-800">{children}</dd>
    </div>
  )
}

/** The machine camera's photo of a rejected bottle: a one-page inspection report (proof of the rejection). */
function EvidenceModal({ session, lane, onClose }: { session: SessionRow; lane: number; onClose: () => void }) {
  const [img, setImg] = useState<{ url: string; reason: string; at: string; box: number[] | null } | null>(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const { data: machines } = usePoll<MachineRow[]>('/machines', 0)
  const machine = machines?.find((m) => m.id === session.machine_id)

  useEffect(() => {
    let url = ''
    fetchImage(`/sessions/${session.id}/bottles/${lane}/evidence`).then(
      (r) => {
        url = r.url
        const box = r.headers.get('X-Evidence-Box')
        setImg({ url: r.url, reason: r.headers.get('X-Evidence-Reason') ?? '', at: r.headers.get('X-Evidence-At') ?? '', box: box ? JSON.parse(box) : null })
      },
      (e) => setErr((e as Error).message),
    )
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [session.id, lane])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const info = EVIDENCE_REASON[img?.reason ?? ''] ?? { title: img?.reason ?? 'Rejected', detail: 'The machine camera rejected this bottle.' }
  const at = img?.at ? new Date(img.at) : null
  const ist = (o: Intl.DateTimeFormatOptions) => at?.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', ...o }) ?? '—'
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(session.id)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard blocked */ }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* header */}
        <div className="flex items-center justify-between gap-4 border-b border-slate-200 bg-slate-50 px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-100 text-red-600">
              <CameraIcon className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Rejection evidence</h2>
              <p className="text-xs text-slate-500">Camera inspection report · bottle {lane} · {session.machine_id}</p>
            </div>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-2 text-2xl leading-none text-slate-400 hover:bg-slate-200 hover:text-slate-700">×</button>
        </div>

        <div className="grid flex-1 gap-0 overflow-y-auto md:grid-cols-[1.45fr_1fr]">
          {/* photo */}
          <div className="flex flex-col bg-slate-950 p-5">
            {img ? (
              <a href={img.url} target="_blank" rel="noreferrer" className="group relative block overflow-hidden rounded-xl ring-1 ring-white/10" title="Open full size">
                <img src={img.url} alt="Rejected bottle" className="w-full object-contain" />
                <span className="absolute top-3 right-3 flex items-center gap-1.5 rounded-lg bg-black/60 px-2.5 py-1.5 text-xs font-semibold text-white opacity-0 transition group-hover:opacity-100">
                  <ExpandIcon className="h-4 w-4" /> Full size
                </span>
              </a>
            ) : err ? (
              <div className="flex aspect-[4/3] items-center justify-center rounded-xl bg-slate-900 p-6 text-center text-sm text-red-300">{err}</div>
            ) : (
              <div className="aspect-[4/3] animate-pulse rounded-xl bg-slate-800" />
            )}
            <p className="mt-3 flex items-center gap-2 text-xs text-slate-400">
              <span className="inline-block h-3 w-3 rounded-sm border-2 border-red-500" /> Red box = area the inspection flagged
            </p>
          </div>

          {/* details */}
          <div className="flex flex-col p-6">
            <div className="rounded-xl bg-red-50 p-4 ring-1 ring-red-100">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-bold tracking-wide text-white uppercase">
                <XCircleIcon className="h-3.5 w-3.5" /> Rejected
              </span>
              <p className="mt-2 text-xl font-extrabold text-red-900">{info.title}</p>
              <p className="mt-1 text-sm text-red-800/80">{info.detail}</p>
            </div>

            <dl className="mt-5">
              <ReportRow label="Date">{ist({ day: '2-digit', month: 'short', year: 'numeric' })}</ReportRow>
              <ReportRow label="Time">{at ? `${ist({ hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }).toUpperCase()} IST` : '—'}</ReportRow>
              <ReportRow label="Machine">
                {session.machine_id}
                {machine && <span className="block text-xs font-normal text-slate-500">{machine.name}{machine.location ? ` · ${machine.location}` : ''}</span>}
              </ReportRow>
              <ReportRow label="Inlet">{lane}</ReportRow>
              <ReportRow label="Damaged area">
                {img?.box ? `${Math.round(img.box[2] * 100)}% × ${Math.round(img.box[3] * 100)}% of frame` : 'Whole item'}
              </ReportRow>
              <ReportRow label="Session outcome"><Badge value={session.outcome} /></ReportRow>
              <ReportRow label="Session ID">
                <button onClick={copy} className="inline-flex items-center gap-1.5 font-mono text-xs text-slate-700 hover:text-brand-700" title="Copy session ID">
                  {session.id.slice(0, 16)}… <CopyIcon className="h-3.5 w-3.5" />
                </button>
                {copied && <span className="block text-xs font-normal text-emerald-600">Copied</span>}
              </ReportRow>
            </dl>

            <div className="mt-auto flex gap-2 pt-6">
              {img && (
                <a href={img.url} download={`evidence-${session.machine_id}-${session.id.slice(0, 8)}-bottle${lane}.jpg`}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-600">
                  <DownloadIcon className="h-4 w-4" /> Download photo
                </a>
              )}
              <Btn variant="secondary" onClick={onClose}>Close</Btn>
            </div>
            <p className="mt-3 text-[11px] leading-snug text-slate-400">
              Stored with the session as proof of the rejection. Simulation pictures are marked "SIMULATION - NOT A REAL PHOTO".
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export function Sessions() {
  const [outcome, setOutcome] = useState('')
  const [photo, setPhoto] = useState<{ session: SessionRow; lane: number } | null>(null)
  const { data } = usePoll<SessionRow[]>(`/sessions?limit=200${outcome ? `&outcome=${outcome}` : ''}`)
  return (
    <>
      <Filters value={outcome} onChange={setOutcome} options={[['', 'All'], ['ACCEPTED', 'Accepted'], ['RETURNED', 'Returned'], ['IN_PROGRESS', 'In progress']]} />
      <Table
        head={['Started', 'Session', 'Machine', 'Bottles', 'Brand', 'Refund QR', 'Outcome', 'Reason']}
        rows={(data ?? []).map((s) => [
          fmtTime(s.started_at), mono(s.id.slice(0, 12)), s.machine_id,
          <div className="space-y-1">
            {s.bottles.map((b) => (
              <div key={b.lane} className="flex items-center gap-2 text-xs">
                <span className="text-slate-400">#{b.lane}</span>
                <Badge value={b.status} />
                {b.reason && b.status !== 'ACCEPTED' && <span className="text-slate-600">{b.reason}</span>}
                {b.evidence && (
                  <button onClick={() => setPhoto({ session: s, lane: b.lane })}
                    className="rounded-md bg-red-50 px-2 py-0.5 font-semibold text-red-700 ring-1 ring-red-200 hover:bg-red-100">
                    📷 Evidence
                  </button>
                )}
              </div>
            ))}
          </div>,
          s.brand ?? '—', mono(s.refund_serial), <Badge value={s.outcome} />, s.reason ?? '—',
        ])}
      />
      {photo && <EvidenceModal session={photo.session} lane={photo.lane} onClose={() => setPhoto(null)} />}
    </>
  )
}

export function Claims() {
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const params = new URLSearchParams({ limit: '200' })
  if (status) params.set('status', status)
  if (q.trim()) params.set('q', q.trim())
  const { data } = usePoll<ClaimRow[]>(`/claims?${params}`)
  return (
    <>
      <p className="mb-4 text-sm text-slate-500">
        One row per refund QR. <b>CONSUMED</b> = refund paid and bottle in the bin; the QR can never be used again.
        <b> RESERVED</b> = a session is using it right now. <b>RELEASED</b> = session ended without accepting the bottle (customer may retry).
      </p>
      <div className="flex flex-wrap items-start gap-4">
        <Filters value={status} onChange={setStatus} options={[['', 'All'], ['CONSUMED', 'Consumed'], ['RESERVED', 'Reserved'], ['RELEASED', 'Released']]} />
        <Search value={q} onChange={setQ} placeholder="Search refund or manufacturing serial" />
      </div>
      <Table
        head={['Updated', 'Refund QR', 'Mfg QR', 'Brand', 'Status', 'Machine', 'Consumed at']}
        rows={(data ?? []).map((c) => [
          fmtTime(c.updated_at), mono(c.refund_serial), mono(c.mfg_serial), c.brand, <Badge value={c.status} />,
          c.machine_id, fmtTime(c.consumed_at),
        ])}
      />
    </>
  )
}

export function Sms() {
  const { data } = usePoll<SmsRow[]>('/sms?limit=200')
  return (
    <Table
      head={['Sent', 'Mobile', 'Status', 'Transaction', 'Message']}
      rows={(data ?? []).map((m) => [
        fmtTime(m.created_at), mono(m.mobile), <Badge value={m.status} />, mono(m.txn_id),
        <span className="block max-w-xl truncate whitespace-normal">{m.body}</span>,
      ])}
    />
  )
}

export function Audit() {
  const [q, setQ] = useState('')
  const { data } = usePoll<AuditRow[]>(`/audit?limit=300${q.trim() ? `&actor=${encodeURIComponent(q.trim())}` : ''}`)
  return (
    <>
      <Search value={q} onChange={setQ} placeholder="Filter by actor (e.g. admin, machine:RVM)" />
      <Table
        head={['Time', 'Actor', 'Action', 'Entity', 'Details']}
        rows={(data ?? []).map((a) => [
          fmtTime(a.at), mono(a.actor),
          <span className={`font-semibold ${a.action.startsWith('ALERT') ? 'text-red-600' : ''}`}>{a.action}</span>,
          <span>{a.entity} {mono(a.entity_id)}</span>,
          <span className="font-mono text-xs text-slate-500">{a.data ? JSON.stringify(a.data) : ''}</span>,
        ])}
      />
    </>
  )
}
