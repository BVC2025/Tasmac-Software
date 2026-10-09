import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useLang } from './i18n'
import type { MachineView } from './useMachine'

/**
 * Plays the pre-generated voice prompts (public/voice/<lang>/<id>.mp3, made by
 * scripts/generate-voice.mjs with Sarvam AI) in the language selected on screen.
 *
 * - One clip at a time; a new clip stops the previous one.
 * - Switching language replays the current instruction in the new language.
 * - If the browser blocks autoplay (dev browsers), the first tap unlocks audio.
 *   On the machine, Chromium runs with --autoplay-policy=no-user-gesture-required.
 */

interface Manifest {
  clips: Record<string, Partial<Record<'ta' | 'en', string>>>
}

interface VoiceCtx {
  enabled: boolean
  available: boolean
  blocked: boolean
  toggle: () => void
  /** Resolves when the clip ends (or immediately if muted / missing).
   *  queue: wait for the clip that is playing instead of cutting it off. */
  play: (id: string, opts?: { queue?: boolean }) => Promise<void>
  stop: () => void
  /** Stop and forget the last clip (so a language reset does not replay it). */
  forget: () => void
}

const Ctx = createContext<VoiceCtx | null>(null)
const PREF_KEY = 'rvm-voice-enabled'
const REPLAY_ON_LANG_CHANGE_MS = 20_000

function readPref(): boolean {
  try {
    return localStorage.getItem(PREF_KEY) !== '0'
  } catch {
    return true
  }
}

export function VoiceProvider({ children }: { children: ReactNode }) {
  const { lang } = useLang()
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [enabled, setEnabled] = useState(readPref)
  const [blocked, setBlocked] = useState(false)
  const audio = useRef<HTMLAudioElement | null>(null)
  const finish = useRef<((interrupted: boolean) => void) | null>(null)
  const last = useRef<{ id: string; at: number } | null>(null)
  const queue = useRef<string[]>([])
  const langRef = useRef(lang)
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled

  useEffect(() => {
    fetch('/voice/manifest.json')
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => {
        if (m?.clips) setManifest(m)
        else console.info('[voice] no manifest - run "npm run voice" to generate prompts')
      })
      .catch(() => console.info('[voice] no manifest - run "npm run voice" to generate prompts'))
  }, [])

  const halt = useCallback(() => {
    const f = finish.current
    finish.current = null
    audio.current?.pause()
    audio.current = null
    f?.(true) // interrupted: settle its promise, but do not start the queue
  }, [])

  const stop = useCallback(() => {
    queue.current = []
    halt()
  }, [halt])

  const playIn = useCallback(
    (id: string, l: 'ta' | 'en'): Promise<void> => {
      halt()
      last.current = { id, at: Date.now() }
      if (!enabledRef.current || !manifest?.clips[id]?.[l]) return Promise.resolve()
      const a = new Audio(`/voice/${l}/${id}.mp3?v=${manifest.clips[id][l]}`)
      audio.current = a
      return new Promise<void>((resolve) => {
        let settled = false
        const done = (interrupted: boolean) => {
          if (settled) return
          settled = true
          if (finish.current === done) finish.current = null
          resolve()
          if (interrupted) return
          const next = queue.current.shift()
          if (next) playRef.current?.(next, langRef.current)
        }
        finish.current = done
        a.onended = () => done(false)
        a.onerror = () => done(false)
        a.play().then(
          () => setBlocked(false),
          (err: DOMException) => {
            if (err.name === 'NotAllowedError') setBlocked(true)
            done(false)
          },
        )
      })
    },
    [manifest, halt],
  )
  const playRef = useRef<typeof playIn | null>(null)
  playRef.current = playIn

  const play = useCallback(
    (id: string, opts?: { queue?: boolean }) => {
      if (opts?.queue && finish.current) {
        queue.current.push(id)   // something is playing: speak after it
        return Promise.resolve()
      }
      if (!opts?.queue) queue.current = []   // a new instruction supersedes anything still waiting
      return playIn(id, langRef.current)
    },
    [playIn],
  )

  // Replay the current instruction when the customer switches language
  useEffect(() => {
    if (langRef.current === lang) return
    langRef.current = lang
    const l = last.current
    if (l && Date.now() - l.at < REPLAY_ON_LANG_CHANGE_MS) playIn(l.id, lang)
  }, [lang, playIn])

  // Autoplay blocked: the first tap anywhere unlocks audio and repeats the last prompt
  useEffect(() => {
    if (!blocked) return
    const unlock = () => {
      setBlocked(false)
      const l = last.current
      if (l) playIn(l.id, langRef.current)
    }
    window.addEventListener('pointerdown', unlock, { once: true })
    return () => window.removeEventListener('pointerdown', unlock)
  }, [blocked, playIn])

  const forget = useCallback(() => {
    stop()
    last.current = null
  }, [stop])

  const toggle = useCallback(() => {
    setEnabled((e) => {
      const next = !e
      try {
        localStorage.setItem(PREF_KEY, next ? '1' : '0')
      } catch {
        /* storage unavailable */
      }
      if (!next) stop()
      return next
    })
  }, [stop])

  return (
    <Ctx.Provider value={{ enabled, available: !!manifest, blocked, toggle, play, stop, forget }}>
      {children}
    </Ctx.Provider>
  )
}

export function useVoice() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useVoice outside VoiceProvider')
  return c
}

/** Clip for a rejection reason code (see voice-prompts.json). */
export function rejectClip(reason: string | null | undefined): string {
  switch (reason) {
    case 'CUSTOMER_CANCELLED':
      return 'cancelled'
    case 'REFUND_QR_INVALID_FORMAT':
    case 'REFUND_QR_FORGED':
      return 'reject_REFUND_QR_INVALID'
    case 'MFG_QR_INVALID_FORMAT':
    case 'MFG_QR_FORGED':
      return 'reject_MFG_QR_INVALID'
    case 'REFUND_QR_IN_USE':
    case 'BOTTLE_IN_USE':
      return 'reject_IN_USE'
    case 'BOTTLE_DAMAGED':
    case 'BOTTLE_FOREIGN':
    case 'REFUND_QR_NOT_FOUND':
    case 'REFUND_QR_ALREADY_USED':
    case 'MFG_QR_NOT_FOUND':
    case 'BRAND_NOT_ELIGIBLE':
    case 'BOTTLE_ALREADY_RETURNED':
    case 'INVALID_DESTINATION':
    case 'CUSTOMER_TIMEOUT':
    case 'PAYOUT_FAILED':
    case 'PAYOUT_PENDING':
    case 'BACKEND_UNAVAILABLE':
      return `reject_${reason}`
    default:
      return 'reject_default'
  }
}

const INPUT_ERROR_CLIP: Record<string, string> = {
  INVALID_DESTINATION: 'error_invalid_destination',
  DESTINATION_NOT_FOUND: 'error_destination_not_found',
  INVALID_SMS_MOBILE: 'error_invalid_sms_mobile',
}

const CHECKING = new Set(['COLLECTING', 'CHECKING'])

/**
 * Which clip the current machine state calls for. The returned `key` changes
 * only when a new instruction is due, so each instruction plays once.
 */
export function cueFor(view: MachineView): { key: string; clip: string; queue?: boolean } | null {
  const s = view.state
  if (!view.connected) return null
  if (s === 'OUT_OF_SERVICE') return { key: 'oos', clip: 'out_of_service' }
  if (view.result && (s === 'READY' || s === 'REJECTING' || s === 'CLOSED')) {
    if (view.result.outcome === 'ACCEPTED') {
      const pending = view.result.final?.code === 'REFUND_PENDING'
      return { key: `result-${view.stateAt}`, clip: pending ? 'pending' : 'success' }
    }
    return null // returned bottles already got their message while REJECTING
  }
  if (s === 'READY') return { key: `ready-${view.stateAt}`, clip: 'insert_bottle' }
  if (CHECKING.has(s)) {
    if (view.message?.code === 'REMOVE_HAND') return { key: `hand-${view.message.at}`, clip: 'remove_hand' }
    return { key: 'checking', clip: 'checking' }
  }
  if (s === 'SELECT_REFUND_METHOD') {
    const attempt = view.stateData.attempt ?? 1
    const err = attempt > 1 && view.inputError ? INPUT_ERROR_CLIP[view.inputError] : null
    // queued: rejected bottles of the batch are announced first
    return { key: `method-${view.stateAt}`, clip: err ?? 'choose_method', queue: !err }
  }
  if (s === 'CONFIRMING') return { key: `confirm-${view.stateAt}`, clip: 'confirm_refund' }
  if (s === 'PAYING' || s === 'ACCEPTING') return { key: 'paying', clip: 'paying' }
  if (s === 'REJECTING') {
    // every bottle failed its own check: each one was already announced
    const bottles = (view.stateData.bottles ?? []) as { step: string }[]
    if (bottles.length && bottles.every((b) => b.step === 'REJECTED')) return null
    return { key: `reject-${view.stateAt}`, clip: rejectClip(view.stateData.reason), queue: true }
  }
  return null
}
