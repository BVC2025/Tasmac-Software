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
    <figure className={`w-full ${compact ? 'max-w-xs' : 'max-w-2xl'}`}>
      <div className="overflow-hidden rounded-3xl bg-slate-900 shadow-2xl ring-4 ring-red-100">
        <img
          src={`${MACHINE_API}/api/evidence/${encodeURIComponent(sessionId)}/${lane}`}
          alt={t.evidenceCaption}
          className="block w-full object-contain"
          onError={() => setFailed(true)}
        />
      </div>
      <figcaption className="mt-4 flex items-center justify-center gap-2 text-lg font-semibold text-red-700">
        <CameraIcon className="h-6 w-6" /> {t.evidenceCaption}
      </figcaption>
    </figure>
  )
}
