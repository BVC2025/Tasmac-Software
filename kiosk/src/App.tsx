import { useEffect, useRef } from 'react'
import { Clock } from './components/Clock'
import { DevPanel } from './components/DevPanel'
import { BottleIcon, SpeakerIcon, SpeakerOffIcon } from './components/Icons'
import { LangProvider, useLang } from './i18n'
import { Confirm, RefundMethod, Result } from './screens/RefundFlow'
import { Checking, Connecting, isCheckingState, OutOfService, Paying, Ready, Rejecting, Starting } from './screens/StatusScreens'
import { useMachine, type MachineView } from './useMachine'
import { cueFor, useVoice, VoiceProvider } from './voice'

function VoiceToggle() {
  const { enabled, available, blocked, toggle } = useVoice()
  if (!available) return null
  return (
    <button
      onClick={toggle}
      aria-label={enabled ? 'Mute voice' : 'Unmute voice'}
      className={`relative flex h-14 w-14 items-center justify-center rounded-full ${enabled ? 'bg-white/15' : 'bg-white/5 text-white/60'}`}
    >
      {enabled ? <SpeakerIcon className="h-7 w-7" /> : <SpeakerOffIcon className="h-7 w-7" />}
      {enabled && blocked && <span className="absolute top-2 right-2 h-3 w-3 animate-pulse rounded-full bg-accent" />}
    </button>
  )
}

function Header({ view }: { view: MachineView }) {
  const { t, lang, setLang } = useLang()
  return (
    <header className="flex items-center justify-between gap-4 bg-brand-700 px-6 py-4 text-white shadow">
      <div className="flex items-center gap-3">
        <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/15">
          <BottleIcon className="h-8 w-8" />
        </span>
        <div>
          <p className="text-2xl leading-tight font-extrabold">{t.appTitle}</p>
          <p className="text-sm opacity-80">TASMAC · {view.machineId || '—'}</p>
        </div>
      </div>
      <Clock />
      <div className="flex items-center gap-3">
      <VoiceToggle />
      <div className="flex rounded-full bg-white/15 p-1">
        {(['ta', 'en'] as const).map((l) => (
          <button
            key={l}
            onClick={() => setLang(l)}
            className={`min-h-12 rounded-full px-5 text-lg font-semibold ${lang === l ? 'bg-white text-brand-700' : 'text-white'}`}
          >
            {l === 'ta' ? 'தமிழ்' : 'English'}
          </button>
        ))}
      </div>
      </div>
    </header>
  )
}

function Body({ view, clearResult }: { view: MachineView; clearResult: () => void }) {
  const s = view.state
  if (!view.connected) return <Connecting />
  if (s === 'OUT_OF_SERVICE') return <OutOfService reason={view.fault ?? view.stateData.reason} showReason={view.simulation} />
  // Hold the outcome screen for a few seconds after the session ends
  if (view.result && (s === 'READY' || s === 'REJECTING')) return <Result result={view.result} onDone={clearResult} />
  if (s === 'STARTING' || s === 'HEALTH_CHECK') return <Starting />
  if (s === 'READY') return <Ready />
  if (isCheckingState(s)) return <Checking view={view} />
  if (s === 'SELECT_REFUND_METHOD') return <RefundMethod key={view.stateAt} view={view} />
  if (s === 'CONFIRMING') return <Confirm key={view.stateAt} view={view} />
  if (s === 'PAYING' || s === 'ACCEPTING') return <Paying />
  if (s === 'REJECTING') return <Rejecting reason={view.stateData.reason} />
  return <Starting />
}

function Kiosk() {
  const [view, clearResult] = useMachine()
  const { setLang } = useLang()

  const voice = useVoice()

  // Back to Tamil for the next customer (silently: the old prompt must not replay)
  const hadResult = useRef(false)
  useEffect(() => {
    if (view.result) hadResult.current = true
    else if (hadResult.current) {
      hadResult.current = false
      voice.forget()
      setLang('ta')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.result, setLang])

  // Spoken guidance: one clip per new instruction, in the selected language.
  // Played a tick later so a language reset in the same update is applied first.
  const cue = cueFor(view)
  const cueKey = cue?.key
  const cueClip = cue?.clip
  useEffect(() => {
    if (!cueClip) return
    const t = window.setTimeout(() => voice.play(cueClip), 60)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cueKey])

  return (
    <div className="flex h-full flex-col">
      <Header view={view} />
      <main className="flex flex-1 flex-col overflow-y-auto">
        <Body view={view} clearResult={clearResult} />
      </main>
      {view.simulation && <DevPanel view={view} />}
    </div>
  )
}

export default function App() {
  return (
    <LangProvider>
      <VoiceProvider>
        <Kiosk />
      </VoiceProvider>
    </LangProvider>
  )
}
