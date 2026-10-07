import { useEffect, useState } from 'react'
import { api, type SessionRow, type SimBottle } from '../api'
import type { MachineView } from '../useMachine'
import { WrenchIcon, XIcon } from './Icons'
import { RealQrTest } from './RealQrTest'

const SAMPLE_QR = 'upi://pay?pa=ravi.kumar@okaxis&pn=Ravi%20Kumar&cu=INR'
const SAMPLE_VOICE = 'ஒன்பது எட்டு ஏழு ஆறு ஐந்து நான்கு மூன்று இரண்டு ஒன்று பூஜ்ஜியம்'

/** Simulation-only tools: insert test bottles, fake QR/voice input, e-stop, session log. */
export function DevPanel({ view }: { view: MachineView }) {
  const [open, setOpen] = useState(false)
  const [bottles, setBottles] = useState<SimBottle[]>([])
  const [sessions, setSessions] = useState<SessionRow[]>([])
  const [qr, setQr] = useState(SAMPLE_QR)
  const [voice, setVoice] = useState(SAMPLE_VOICE)
  const [note, setNote] = useState('')
  const [estop, setEstop] = useState(false)
  const [lane, setLane] = useState<number | undefined>(undefined)
  const [batch, setBatch] = useState<string[]>(['happy-path-upi', 'damaged-bottle', 'happy-path-mobile'])
  const laneNumbers = Array.from({ length: view.laneCount }, (_, i) => i + 1)

  useEffect(() => {
    if (!open) return
    api.simBottles().then(setBottles).catch(() => {})
    const load = () => api.sessions().then(setSessions).catch(() => {})
    load()
    const id = window.setInterval(load, 2000)
    return () => window.clearInterval(id)
  }, [open])

  const insert = async (name?: string) => {
    try {
      const r = await api.simInsert(name, lane)
      setNote(r.inserted ? `Inserted ${r.bottle} in inlet ${r.lane}` : 'Not inserted (inlet closed or busy)')
    } catch (e) {
      setNote((e as Error).message)
    }
  }

  const insertBatch = async () => {
    try {
      const r = await api.simInsertBatch(batch.slice(0, view.laneCount).map((b) => b || null))
      setNote(r.inserted.length ? `Inserted together: ${r.inserted.map((i) => `${i.lane}=${i.bottle}`).join(', ')}` : 'Not inserted (inlets busy)')
    } catch (e) {
      setNote((e as Error).message)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed right-4 bottom-4 z-50 flex items-center gap-2 rounded-full bg-slate-900 px-4 py-3 text-sm font-semibold text-amber-300 shadow-lg"
      >
        <WrenchIcon className="h-5 w-5" /> DEV
      </button>
    )
  }

  const input = 'w-full rounded-lg bg-slate-800 px-3 py-2 font-mono text-xs text-slate-100 ring-1 ring-slate-700'
  const btn = 'rounded-lg bg-slate-700 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-600'

  return (
    <aside className="fixed top-0 right-0 bottom-0 z-50 flex w-96 flex-col gap-4 overflow-y-auto bg-slate-900 p-4 text-sm text-slate-200 shadow-2xl select-text">
      <div className="flex items-center justify-between">
        <h2 className="font-bold text-amber-300">Developer panel (simulation)</h2>
        <button onClick={() => setOpen(false)} aria-label="Close">
          <XIcon className="h-5 w-5" />
        </button>
      </div>

      <section className="rounded-lg bg-slate-800/60 p-3 font-mono text-xs">
        <div>state: <b className="text-emerald-300">{view.state}</b></div>
        <div>plc: {view.plc ? `${view.plc.state} fault=${view.plc.fault} bin=${view.plc.bin_fill_pct}%` : '-'}</div>
        <div>ws: {view.connected ? 'connected' : 'disconnected'} · {view.machineId}</div>
        {view.message && <div className="truncate">msg: {JSON.stringify({ ...view.message, at: undefined, type: undefined })}</div>}
      </section>

      <RealQrTest lane={lane} input={input} btn={btn} />

      <section className="space-y-2">
        <h3 className="font-semibold text-slate-400">1. Insert test bottles</h3>
        {view.laneCount > 1 && (
          <div className="space-y-2 rounded-lg bg-slate-800/60 p-2">
            <p className="text-xs font-semibold text-emerald-300">Several bottles at the same moment (one per inlet)</p>
            {laneNumbers.map((ln, i) => (
              <label key={ln} className="flex items-center gap-2 text-xs">
                <span className="w-14 shrink-0 text-slate-400">Inlet {ln}</span>
                <select
                  className={input}
                  value={batch[i] ?? ''}
                  onChange={(e) => setBatch((prev) => Object.assign([...prev], { [i]: e.target.value }))}
                >
                  <option value="">(empty)</option>
                  {bottles.map((b) => (
                    <option key={b.name} value={b.name}>{b.name}</option>
                  ))}
                </select>
              </label>
            ))}
            <button className={`${btn} w-full bg-emerald-700 hover:bg-emerald-600`} onClick={insertBatch}>
              Insert all at once
            </button>
          </div>
        )}
        <div className="flex items-center gap-1 text-xs">
          <span className="mr-1 text-slate-400">Single / real bottle into</span>
          {[undefined, ...laneNumbers].map((ln) => (
            <button key={ln ?? 'auto'} onClick={() => setLane(ln)}
              className={`rounded-md px-2 py-1 font-semibold ${lane === ln ? 'bg-amber-400 text-slate-900' : 'bg-slate-700 text-white'}`}>
              {ln ?? 'auto'}
            </button>
          ))}
        </div>
        <button className={`${btn} w-full bg-emerald-700 hover:bg-emerald-600`} onClick={() => insert()}>
          Insert next bottle
        </button>
        <div className="grid grid-cols-1 gap-1">
          {bottles.map((b) => (
            <button key={b.name} className="rounded-md bg-slate-800 px-2 py-1.5 text-left text-xs hover:bg-slate-700" onClick={() => insert(b.name)}>
              <span className="font-semibold">{b.name}</span>
              <span className="block text-[10px] text-slate-400">
                {b.condition} · refundQR {b.has_refund_qr ? '✓' : '✗'} · mfgQR {b.has_mfg_qr ? '✓' : '✗'} · payout {b.payout}
              </span>
            </button>
          ))}
        </div>
        <button
          className={`${btn} w-full`}
          onClick={() => api.simRefresh().then((r) => setNote(`Fresh QR codes for ${r.refreshed} test bottles`))}
        >
          Fresh QR codes (after a full round, QRs are "already used")
        </button>
        {note && <p className="text-xs text-amber-200">{note}</p>}
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-slate-400">2. Simulate UPI QR scan</h3>
        <input className={input} value={qr} onChange={(e) => setQr(e.target.value)} />
        <div className="flex flex-wrap gap-1">
          <button className={btn} onClick={() => window.dispatchEvent(new CustomEvent('kiosk:scan', { detail: qr }))}>Scan</button>
          <button className={btn} onClick={() => setQr('upi://pay?pa=fail.test@okaxis&pn=Fail%20Test')}>fail</button>
          <button className={btn} onClick={() => setQr('upi://pay?pa=slow.test@okaxis&pn=Slow%20Test')}>slow</button>
          <button className={btn} onClick={() => setQr('upi://pay?pa=invalid.user@okaxis')}>not found</button>
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-slate-400">3. Simulate voice (Tamil / English words)</h3>
        <textarea className={input} rows={2} value={voice} onChange={(e) => setVoice(e.target.value)} />
        <div className="flex flex-wrap gap-1">
          <button className={btn} onClick={() => window.dispatchEvent(new CustomEvent('kiosk:voice', { detail: voice }))}>Speak</button>
          <button className={btn} onClick={() => setVoice('nine eight seven six five double four three two one')}>English</button>
          <button className={btn} onClick={() => setVoice('onbadhu ettu ezhu aaru anju naalu moonu rendu onnu poojyam')}>Thanglish</button>
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-slate-400">4. Faults</h3>
        <button
          className={`${btn} w-full ${estop ? 'bg-red-700 hover:bg-red-600' : ''}`}
          onClick={async () => {
            await api.simEstop(!estop)
            setEstop(!estop)
          }}
        >
          {estop ? 'Release E-STOP' : 'Press E-STOP'}
        </button>
      </section>

      <section className="space-y-1">
        <h3 className="font-semibold text-slate-400">Recent sessions</h3>
        {sessions.map((s) => (
          <div key={s.id} className="rounded-md bg-slate-800 px-2 py-1.5 font-mono text-[11px]">
            <span className={s.outcome === 'ACCEPTED' ? 'text-emerald-300' : 'text-amber-300'}>{s.outcome}</span> {s.reason}
            {s.outcome === 'ACCEPTED' && <span className="text-emerald-300"> ₹{s.amount_paise / 100}</span>}
            <span className="block text-slate-300">
              {s.bottles.map((b) => `#${b.lane} ${b.step}${b.reason && b.step !== 'ACCEPTED' ? ` (${b.reason})` : ''}`).join(' · ')}
            </span>
            <span className="block text-slate-400">
              {s.txn_id ?? ''} {s.destination ?? ''} {s.payout_status ?? ''}
            </span>
          </div>
        ))}
      </section>
    </aside>
  )
}
