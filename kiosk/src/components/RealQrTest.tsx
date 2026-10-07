import { useEffect, useState } from 'react'
import { api, type CameraPreview, type CameraStatus, type DecodedCode } from '../api'
import { getCameraId, setCameraId } from '../lib/camera'

const KIND_STYLE: Record<string, string> = {
  refund: 'bg-emerald-800 text-emerald-100',
  mfg: 'bg-orange-800 text-orange-100',
  unknown: 'bg-red-900 text-red-100',
}

function KindBadge({ kind }: { kind: DecodedCode['kind'] }) {
  const k = kind ?? 'unknown'
  const label = kind === 'refund' ? 'Refund QR' : kind === 'mfg' ? 'Mfg QR' : 'Unknown - register in Admin'
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${KIND_STYLE[k]}`}>{label}</span>
}

/**
 * Testing with REAL bottles before the machine exists:
 *  - machine camera mode (vision_driver: camera, e.g. DroidCam): live preview, insert, show the QRs
 *  - otherwise: photo upload / pasted QR text -> a simulated bottle carrying those QRs
 *  - which browser camera the UPI scan screen uses
 */
export function RealQrTest({ lane, input, btn }: { lane?: number; input: string; btn: string }) {
  const [cam, setCam] = useState<CameraStatus | null>(null)
  const [preview, setPreview] = useState<CameraPreview | null>(null)
  const [refund, setRefund] = useState('')
  const [mfg, setMfg] = useState('')
  const [condition, setCondition] = useState('ok')
  const [decoded, setDecoded] = useState<DecodedCode[]>([])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.cameraStatus().then(setCam, () => setCam({ enabled: false, lanes: {} }))
  }, [])

  useEffect(() => {
    if (!cam?.enabled) return
    let stopped = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const p = await api.cameraPreview(lane ?? 1, 480)
        if (!stopped) setPreview(p)
      } catch {
        /* machine restarting */
      }
      if (!stopped) timer = window.setTimeout(tick, 600)
    }
    tick()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [cam, lane])

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    setNote('')
    try {
      const all: DecodedCode[] = []
      for (const f of Array.from(files)) {
        const r = await api.qrDecode(f)
        if (!r.codes.length) setNote(`No QR found in ${f.name} - try a closer, sharper photo`)
        all.push(...r.codes)
      }
      const unique = all.filter((c, i) => all.findIndex((x) => x.text === c.text) === i)
      setDecoded(unique)
      const r = unique.find((c) => c.kind === 'refund')
      const m = unique.find((c) => c.kind === 'mfg')
      if (r) setRefund(r.text)
      if (m) setMfg(m.text)
    } catch (e) {
      setNote((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const camLane = String(lane ?? 1)
  const rotation = cam?.lanes[camLane]?.rotate ?? cam?.lanes['1']?.rotate ?? 0
  const rotate = async () => {
    try {
      const r = await api.cameraRotate(lane ?? 1, (rotation + 90) % 360)
      setCam((c) => c && { ...c, lanes: Object.fromEntries(Object.entries(c.lanes).map(([k, v]) => [k, { ...v, rotate: r.rotate }])) })
      setNote(`Picture turned ${r.rotate}°. To keep it after a restart: camera.rotate: ${r.rotate} in machine.camera.yaml`)
    } catch (e) {
      setNote((e as Error).message)
    }
  }

  const insert = async (withCodes: boolean) => {
    try {
      const r = await api.simInsertCustom({
        refund_qr: withCodes ? refund : undefined,
        mfg_qr: withCodes ? mfg : undefined,
        condition,
        lane,
      })
      setNote(r.inserted ? `Inserted in inlet ${r.lane}${withCodes ? '' : ' - now show the QRs to the camera'}` : 'Not inserted (inlet closed or busy)')
    } catch (e) {
      setNote((e as Error).message)
    }
  }

  const conditionSelect = (
    <label className="flex items-center gap-2 text-xs">
      <span className="w-16 shrink-0 text-slate-400">Condition</span>
      <select className={input} value={condition} onChange={(e) => setCondition(e.target.value)}>
        <option value="ok">ok (vision passes)</option>
        <option value="damaged">damaged</option>
        <option value="foreign">foreign object</option>
      </select>
    </label>
  )

  return (
    <section className="space-y-2 rounded-lg bg-slate-800/60 p-2">
      <h3 className="font-semibold text-sky-300">0. Real bottle QR test</h3>

      {cam?.enabled ? (
        <>
          <p className="text-[11px] text-slate-400">
            Machine camera: {Object.values(cam.lanes)[0]?.source}
            {preview && (preview.connected ? ' · connected' : ` · ${preview.error ?? 'not connected'}`)}
          </p>
          <div className="aspect-video w-full overflow-hidden rounded-md bg-black">
            {preview?.image ? (
              <img src={preview.image} alt="camera" className="h-full w-full object-contain" />
            ) : (
              <p className="p-4 text-center text-xs text-slate-400">No picture yet - is DroidCam started?</p>
            )}
          </div>
          <button className={`${btn} w-full`} onClick={rotate}>
            Rotate picture ↻ (now {rotation}°)
          </button>
          {preview?.codes.map((c) => (
            <div key={c.text} className="space-y-0.5 rounded bg-slate-900 p-1.5">
              <KindBadge kind={c.kind} />
              <p className="font-mono text-[10px] break-all text-slate-300">{c.text}</p>
            </div>
          ))}
          {conditionSelect}
          <button className={`${btn} w-full bg-sky-700 hover:bg-sky-600`} onClick={() => insert(false)}>
            Insert bottle - camera reads its QRs
          </button>
          <p className="text-[11px] text-slate-400">
            After Insert, hold the bottle in front of the camera: refund QR first, then the manufacturing QR (about 15 s).
          </p>
        </>
      ) : (
        <>
          <label className="block text-xs text-slate-400">
            Photo of the bottle QRs (one photo with both, or two photos)
            <input type="file" accept="image/*" multiple disabled={busy} onChange={(e) => upload(e.target.files)}
              className="mt-1 block w-full text-xs text-slate-300 file:mr-2 file:rounded-md file:border-0 file:bg-slate-700 file:px-2 file:py-1 file:text-white" />
          </label>
          {busy && <p className="text-xs text-slate-400">Reading...</p>}
          {decoded.map((c) => (
            <div key={c.text} className="space-y-1 rounded bg-slate-900 p-1.5">
              <div className="flex items-center gap-1">
                <KindBadge kind={c.kind} />
                <span className="ml-auto flex gap-1">
                  <button className="rounded bg-emerald-800 px-1.5 text-[10px]" onClick={() => setRefund(c.text)}>use as refund</button>
                  <button className="rounded bg-orange-800 px-1.5 text-[10px]" onClick={() => setMfg(c.text)}>use as mfg</button>
                </span>
              </div>
              <p className="font-mono text-[10px] break-all text-slate-300">{c.text}</p>
            </div>
          ))}
          <label className="block text-xs text-slate-400">
            Refund QR text
            <textarea className={input} rows={2} value={refund} onChange={(e) => setRefund(e.target.value)}
              placeholder="paste from a phone QR scanner app" />
          </label>
          <label className="block text-xs text-slate-400">
            Manufacturing QR text
            <textarea className={input} rows={2} value={mfg} onChange={(e) => setMfg(e.target.value)} />
          </label>
          {conditionSelect}
          <button className={`${btn} w-full bg-sky-700 hover:bg-sky-600`} disabled={!refund && !mfg} onClick={() => insert(true)}>
            Insert bottle with these QRs
          </button>
          <p className="text-[11px] text-slate-400">
            Real TASMAC QRs are rejected until registered: Admin → QR registry lists every unknown QR seen here.
          </p>
        </>
      )}
      {note && <p className="text-xs text-amber-200">{note}</p>}
      <BrowserCameraPicker input={input} btn={btn} />
    </section>
  )
}

/** The browser camera used by the UPI QR scan screen (e.g. DroidCam instead of a laptop webcam). */
function BrowserCameraPicker({ input, btn }: { input: string; btn: string }) {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [chosen, setChosen] = useState(getCameraId() ?? '')

  const load = () =>
    navigator.mediaDevices?.enumerateDevices().then((d) => setDevices(d.filter((x) => x.kind === 'videoinput')))

  useEffect(() => {
    load()
  }, [])

  const allowNames = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true })
      s.getTracks().forEach((t) => t.stop())
    } catch {
      /* no camera / denied */
    }
    load()
  }

  const unnamed = devices.some((d) => !d.label)
  return (
    <div className="space-y-1 border-t border-slate-700 pt-2">
      <p className="text-xs text-slate-400">Camera for the UPI QR scan screen (browser)</p>
      {devices.length === 0 ? (
        <p className="text-[11px] text-slate-500">No camera found by the browser.</p>
      ) : (
        <select className={input} value={chosen} onChange={(e) => {
          setChosen(e.target.value)
          setCameraId(e.target.value || null)
        }}>
          <option value="">Default camera</option>
          {devices.map((d, i) => (
            <option key={d.deviceId || i} value={d.deviceId}>{d.label || `Camera ${i + 1}`}</option>
          ))}
        </select>
      )}
      {unnamed && <button className={btn} onClick={allowNames}>Show camera names</button>}
    </div>
  )
}
