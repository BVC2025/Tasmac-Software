import { useEffect, useRef } from 'react'
import { Clock } from './components/Clock'
import { DevPanel } from './components/DevPanel'
import { BottleIcon } from './components/Icons'
import { LangProvider, useLang } from './i18n'
import { Confirm, RefundMethod, Result } from './screens/RefundFlow'
import { Checking, Connecting, isCheckingState, OutOfService, Paying, Ready, Rejecting, Starting } from './screens/StatusScreens'
import { useMachine, type MachineView } from './useMachine'

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

  // Back to Tamil for the next customer
  const hadResult = useRef(false)
  useEffect(() => {
    if (view.result) hadResult.current = true
    else if (hadResult.current) {
      hadResult.current = false
      setLang('ta')
    }
  }, [view.result, setLang])

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
      <Kiosk />
    </LangProvider>
  )
}
