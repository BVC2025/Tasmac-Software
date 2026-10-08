import jsQR from 'jsqr'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Banner, Button, ScanFrame, Spinner, StatusBadge } from '../components/ui'
import { ArrowRightIcon, CheckIcon, QrIcon } from '../components/Icons'
import { useLang } from '../i18n'
import { videoConstraints } from '../lib/camera'
import { parseUpiQr, type UpiTarget } from '../lib/upi'
import { useVoice } from '../voice'

/**
 * Reads a UPI QR from:
 *  - the kiosk camera (getUserMedia + jsQR), or the machine's own camera when the
 *    machine runs with vision_driver: camera (it already holds the device, e.g. DroidCam)
 *  - a USB/HID QR scanner (types the payload + Enter like a keyboard)
 *  - the dev panel (window event "kiosk:scan")
 */
export function QrScan({ onResult }: { onResult: (t: UpiTarget) => void }) {
  const { t } = useLang()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [camera, setCamera] = useState<'starting' | 'on' | 'off'>(() => (navigator.mediaDevices ? 'starting' : 'off'))
  const [found, setFound] = useState<UpiTarget | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [source, setSource] = useState<'unknown' | 'machine' | 'browser'>('unknown')
  const [frame, setFrame] = useState<string | null>(null)

  useEffect(() => {
    api.cameraStatus().then(
      (s) => setSource(s.enabled ? 'machine' : 'browser'),
      () => setSource('browser'),
    )
  }, [])

  const { play } = useVoice()
  const handle = useCallback((text: string) => {
    const target = parseUpiQr(text)
    if (target) {
      setFound((prev) => {
        if (!prev) play('qr_found')
        return target
      })
      setInvalid(false)
    } else {
      setInvalid(true)
    }
  }, [play])

  // Machine camera: poll its preview (codes are decoded on the machine)
  useEffect(() => {
    if (found || source !== 'machine') return
    let stopped = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const p = await api.cameraPreview(1, 640)
        if (stopped) return
        setFrame(p.image)
        setCamera(p.image ? 'on' : 'off')
        const upi = p.codes.find((c) => parseUpiQr(c.text))
        if (upi) handle(upi.text)
        else if (p.codes.length) setInvalid(true)
      } catch {
        if (!stopped) setCamera('off')
      }
      if (!stopped) timer = window.setTimeout(tick, 350)
    }
    tick()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [found, source, handle])

  // Browser camera scanning
  useEffect(() => {
    if (found || source !== 'browser') return
    let stream: MediaStream | null = null
    let timer: number | undefined
    let stopped = false
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d', { willReadFrequently: true })

    navigator.mediaDevices
      ?.getUserMedia({ video: videoConstraints() })
      .then((s) => {
        if (stopped) return s.getTracks().forEach((tr) => tr.stop())
        stream = s
        const v = videoRef.current!
        v.srcObject = s
        v.play().catch(() => {})
        setCamera('on')
        const tick = () => {
          if (v.readyState >= 2 && ctx) {
            canvas.width = v.videoWidth
            canvas.height = v.videoHeight
            ctx.drawImage(v, 0, 0)
            const img = ctx.getImageData(0, 0, canvas.width, canvas.height)
            const code = jsQR(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' })
            if (code?.data) handle(code.data)
          }
          timer = window.setTimeout(tick, 200)
        }
        tick()
      })
      .catch(() => setCamera('off'))

    return () => {
      stopped = true
      window.clearTimeout(timer)
      stream?.getTracks().forEach((tr) => tr.stop())
    }
  }, [found, source, handle])

  // HID scanner (keyboard wedge) + dev panel simulation
  useEffect(() => {
    let buffer = ''
    let last = 0
    const onKey = (e: KeyboardEvent) => {
      const now = Date.now()
      if (now - last > 100) buffer = '' // scanners type fast; humans don't
      last = now
      if (e.key === 'Enter') {
        if (buffer.length > 4) handle(buffer)
        buffer = ''
      } else if (e.key.length === 1) {
        buffer += e.key
      }
    }
    const onSim = (e: Event) => handle((e as CustomEvent<string>).detail)
    window.addEventListener('keydown', onKey)
    window.addEventListener('kiosk:scan', onSim)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('kiosk:scan', onSim)
    }
  }, [handle])

  if (found) {
    return (
      <div className="flex w-full flex-col items-center">
        <StatusBadge size="md"><CheckIcon className="h-14 w-14" strokeWidth={3} /></StatusBadge>
        <p className="mb-6 text-3xl font-extrabold text-brand-900">{t.upiDetected}</p>
        <div className="w-full rounded-3xl bg-white px-8 py-6 text-center shadow-sm ring-1 ring-slate-200">
          <p className="text-lg text-slate-500">UPI ID</p>
          <p className="mt-1 text-3xl font-bold break-all text-brand-900">{found.vpa}</p>
          {found.name && <p className="mt-2 text-xl text-slate-600">{found.name}</p>}
        </div>
        <div className="mt-8 grid w-full grid-cols-3 gap-4">
          <Button variant="secondary" onClick={() => setFound(null)}>
            {t.change}
          </Button>
          <Button className="col-span-2" onClick={() => onResult(found)}>
            {t.next} <ArrowRightIcon className="h-7 w-7" />
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <p className="text-center text-xl text-slate-600">{t.qrSub}</p>
      <ScanFrame scanning={camera === 'on'}>
        {source === 'machine' ? (
          frame && <img src={frame} alt="" className="h-full w-full -scale-x-100 object-cover" />
        ) : (
          <video ref={videoRef} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
        )}
        {camera !== 'on' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 p-6 text-center text-slate-300">
            <QrIcon className="h-24 w-24" />
            {camera === 'off' && <p className="text-lg">{t.qrNoCamera}</p>}
          </div>
        )}
      </ScanFrame>
      {camera === 'on' && (
        <p className="flex items-center gap-3 text-lg text-slate-600">
          <Spinner className="h-6 w-6" thin /> {t.scanning}
        </p>
      )}
      {invalid && <Banner tone="error">{t.qrInvalid}</Banner>}
    </div>
  )
}
