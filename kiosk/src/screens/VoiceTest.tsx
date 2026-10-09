import { useState } from 'react'
import { Banner, Button, Screen, StatusBadge, Title } from '../components/ui'
import { ArrowLeftIcon, CheckIcon } from '../components/Icons'
import { useLang } from '../i18n'
import { VoiceInput } from './VoiceInput'

/**
 * Simulation only: try "speak your mobile number" straight from the welcome screen,
 * without inserting a bottle. Same VoiceInput the customer gets on the refund screen.
 */
export function VoiceTest({ onClose }: { onClose: () => void }) {
  const { lang } = useLang()
  const [result, setResult] = useState<string | null>(null)
  const [round, setRound] = useState(0)

  return (
    <Screen>
      <div className="mb-6 flex w-full items-center justify-between">
        <Button variant="ghost" className="min-h-12 px-4" onClick={onClose}>
          <ArrowLeftIcon className="h-6 w-6" /> Home
        </Button>
        <span className="rounded-full bg-amber-100 px-4 py-1.5 text-sm font-bold text-amber-800">
          TEST MODE · {lang === 'ta' ? 'Tamil (ta-IN)' : 'English (en-IN)'}
        </span>
      </div>
      <Title sub="Speak a 10-digit mobile number. Digits should appear while you speak.">Voice input test</Title>

      {result ? (
        <div className="flex w-full flex-col items-center">
          <StatusBadge size="md"><CheckIcon className="h-14 w-14" strokeWidth={3} /></StatusBadge>
          <p className="text-xl text-slate-600">Number the customer would confirm:</p>
          <p className="mt-2 text-5xl font-extrabold tracking-widest text-brand-900 tabular-nums">{result}</p>
          <div className="mt-10 grid w-full max-w-md grid-cols-2 gap-4">
            <Button variant="secondary" onClick={onClose}>Home</Button>
            <Button onClick={() => { setResult(null); setRound((r) => r + 1) }}>Test again</Button>
          </div>
        </div>
      ) : (
        <>
          <VoiceInput key={round} onResult={setResult} onTypeInstead={onClose} />
          <div className="mt-8 w-full">
            <Banner tone="info">
              Switch Tamil / English at the top to test both recognisers. Chrome needs microphone permission and internet.
            </Banner>
          </div>
        </>
      )}
    </Screen>
  )
}
