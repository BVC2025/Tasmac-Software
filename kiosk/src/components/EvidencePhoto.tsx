import { useState } from 'react'
import { MACHINE_API } from '../api'
import { CameraIcon } from './Icons'
import { useLang } from '../i18n'

/** The machine camera's photo of a rejected bottle, with the damaged area boxed (proof for the customer). */
export function EvidencePhoto({ sessionId, lane, compact = false }: { sessionId: string; lane: number; compact?: boolean }) {
  const { t } = useLang()
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    <figure className={`w-full overflow-hidden rounded-3xl bg-slate-900 shadow-xl ring-4 ring-red-200 ${compact ? 'max-w-xs' : 'max-w-xl'}`}>
      <img
        src={`${MACHINE_API}/api/evidence/${encodeURIComponent(sessionId)}/${lane}`}
        alt={t.evidenceCaption}
        className="w-full object-contain"
        onError={() => setFailed(true)}
      />
      <figcaption className="flex items-center justify-center gap-2 bg-red-50 px-4 py-2 text-base font-semibold text-red-800">
        <CameraIcon className="h-5 w-5" /> {t.evidenceCaption}
      </figcaption>
    </figure>
  )
}
