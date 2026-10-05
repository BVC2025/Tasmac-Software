import { useCallback, useEffect, useRef, useState } from 'react'
import { Banner, Button } from '../components/ui'
import { DigitDisplay } from '../components/Keypads'
import { MicIcon } from '../components/Icons'
import { useLang } from '../i18n'
import { spokenToDigits } from '../lib/speechNumbers'
import { normalizeMobile } from '../lib/upi'

// Minimal Web Speech API typings (not in every TS DOM lib)
interface SpeechResultList {
  length: number
  [i: number]: { 0: { transcript: string }; isFinal: boolean }
}
interface Recognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((e: { results: SpeechResultList }) => void) | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
  start(): void
  stop(): void
  abort(): void
}
type RecognitionCtor = new () => Recognition

const getRecognition = (): RecognitionCtor | null => {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

/**
 * Speak mobile number -> speech-to-text -> live number display.
 *
 * Uses the browser Web Speech API for now (Chrome needs internet for it).
 * Production plan: offline STT on the machine (Vosk / faster-whisper) behind
 * the same screen. The dev panel can inject text via window event "kiosk:voice".
 */
export function VoiceInput({ onResult, onTypeInstead }: { onResult: (mobile: string) => void; onTypeInstead: () => void }) {
  const { t, lang } = useLang()
  const Ctor = getRecognition()
  const recRef = useRef<Recognition | null>(null)
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [digits, setDigits] = useState('')
  const [error, setError] = useState<string | null>(null)

  const apply = useCallback((text: string) => {
    setTranscript(text)
    let d = spokenToDigits(text)
    if (d.length > 10 && d.startsWith('91')) d = d.slice(2)
    setDigits(d.slice(0, 10))
    if (d.length >= 10) recRef.current?.stop()
  }, [])

  const start = useCallback(() => {
    if (!Ctor) return
    recRef.current?.abort()
    setTranscript('')
    setDigits('')
    setError(null)
    const rec = new Ctor()
    rec.lang = lang === 'ta' ? 'ta-IN' : 'en-IN'
    rec.continuous = true
    rec.interimResults = true
    rec.onresult = (e) => {
      let text = ''
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript + ' '
      apply(text)
    }
    rec.onerror = (e) => setError(e.error)
    rec.onend = () => setListening(false)
    recRef.current = rec
    rec.start()
    setListening(true)
  }, [Ctor, lang, apply])

  useEffect(() => {
    const onSim = (e: Event) => apply((e as CustomEvent<string>).detail)
    window.addEventListener('kiosk:voice', onSim)
    if (Ctor) start()
    return () => {
      window.removeEventListener('kiosk:voice', onSim)
      recRef.current?.abort()
    }
    // start once when the screen opens
  }, [])

  const mobile = normalizeMobile(digits)

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <p className="text-center text-xl text-slate-600">{t.voiceSub}</p>

      {!Ctor && <Banner tone="warn">{t.voiceUnsupported}</Banner>}

      <button
        onClick={start}
        disabled={!Ctor}
        className="relative flex h-36 w-36 items-center justify-center rounded-full bg-brand-600 text-white disabled:bg-slate-300"
      >
        {listening && <span className="animate-pulse-ring absolute inset-0 rounded-full bg-brand-500/50" />}
        <MicIcon className="relative h-16 w-16" />
      </button>
      <p className="text-lg font-semibold text-brand-700">{listening ? t.voiceListening : t.voiceTapToSpeak}</p>

      <DigitDisplay digits={digits} />
      {transcript && <p className="max-w-full truncate text-center text-base text-slate-500">"{transcript.trim()}"</p>}
      {error && error !== 'aborted' && <p className="text-sm text-red-600">({error})</p>}

      {mobile ? (
        <div className="w-full space-y-3">
          <p className="text-center text-2xl font-bold text-brand-900">{t.voiceIsCorrect}</p>
          <div className="grid grid-cols-2 gap-4">
            <Button variant="secondary" onClick={start} disabled={!Ctor}>
              {t.voiceRetry}
            </Button>
            <Button onClick={() => onResult(mobile)}>{t.next}</Button>
          </div>
        </div>
      ) : (
        <Button variant="ghost" onClick={onTypeInstead}>
          {t.voiceTypeInstead}
        </Button>
      )}
    </div>
  )
}
