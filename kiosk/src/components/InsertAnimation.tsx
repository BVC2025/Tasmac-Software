/**
 * "Insert your bottle" animation (8 s loop), modelled on the reference video:
 * a glass bottle drops onto the inlet ring, the machine scans it (brackets,
 * arrow, sweep line), the ring glows and the bottle sinks into the inlet.
 * Pure SVG + CSS keyframes (see index.css, .ia-*), honours reduced motion.
 */
export function InsertAnimation({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 480" className={className} role="img" aria-label="Insert the bottle into the opening">
      <defs>
        <linearGradient id="ia-panel" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#13503a" />
          <stop offset="1" stopColor="#0a2c20" />
        </linearGradient>
        <radialGradient id="ia-hole" cx="0.5" cy="0.42" r="0.6">
          <stop offset="0" stopColor="#020a06" />
          <stop offset="0.75" stopColor="#06170f" />
          <stop offset="1" stopColor="#0d2f22" />
        </radialGradient>
        <linearGradient id="ia-glass" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.30" />
          <stop offset="0.35" stopColor="#ffffff" stopOpacity="0.06" />
          <stop offset="0.7" stopColor="#ffffff" stopOpacity="0.10" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0.28" />
        </linearGradient>
        <filter id="ia-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="7" />
        </filter>
      </defs>

      {/* machine window */}
      <rect x="8" y="8" width="384" height="464" rx="28" fill="url(#ia-panel)" />
      <rect x="8" y="8" width="384" height="464" rx="28" fill="none" stroke="#7fe0c0" strokeOpacity="0.15" strokeWidth="2" />

      {/* HUD: side rails at ring level */}
      <g stroke="#7fe0c0" strokeLinecap="round" fill="none">
        <path d="M34 300 H118 M282 300 H366" strokeOpacity="0.45" strokeWidth="2" />
        <path d="M34 300 V392 H130 M366 300 V392 H270" strokeOpacity="0.25" strokeWidth="1.5" />
      </g>
      <g fill="#7fe0c0">
        <rect x="44" y="372" width="34" height="8" rx="2" opacity="0.55" />
        <rect x="82" y="372" width="18" height="8" rx="2" opacity="0.3" />
        <rect x="306" y="286" width="40" height="5" rx="2" opacity="0.4" />
        {/* tiny bottle glyphs (bottom right) */}
        <path d="M330 352h4v5l2 3v18h-8v-18l2-3z M344 352h4v5l2 3v18h-8v-18l2-3z" opacity="0.45" />
      </g>

      {/* scan brackets around the bottle */}
      <g className="ia-brackets" stroke="#7fe0c0" strokeWidth="3" fill="none" strokeLinecap="round">
        <path d="M120 70 V48 H142 M258 48 H280 V70 M120 238 V260 H142 M280 238 V260 H258" />
      </g>

      {/* inlet hole */}
      <circle cx="200" cy="318" r="66" fill="none" stroke="#7fe0c0" strokeOpacity="0.12" strokeWidth="2" />
      <circle cx="200" cy="318" r="56" fill="url(#ia-hole)" />

      {/* bottle (drops in, waits, sinks) */}
      <g className="ia-bottle">
        <path
          d="M188 96 h24 v8 h-2 v44 c0 10 22 24 22 44 v128 c0 9 -7 16 -16 16 h-32 c-9 0 -16 -7 -16 -16 v-128 c0 -20 22 -34 22 -44 v-44 h-2 z"
          fill="url(#ia-glass)"
          stroke="#e9fff6"
          strokeOpacity="0.75"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <path d="M178 214 v104" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="4" strokeLinecap="round" />
        <path d="M222 220 v60" stroke="#ffffff" strokeOpacity="0.2" strokeWidth="3" strokeLinecap="round" />
        <path d="M188 104 h24" stroke="#e9fff6" strokeOpacity="0.6" strokeWidth="2" />
        {/* down arrow on the bottle */}
        <path className="ia-arrow" d="M190 226 h20 l-10 12 z" fill="#7fe0c0" />
      </g>

      {/* ring drawn over the bottle base so the bottle sits "in" the inlet */}
      <circle className="ia-ring-glow" cx="200" cy="318" r="56" fill="none" stroke="#9ff5d6" strokeWidth="14" filter="url(#ia-glow)" />
      <circle className="ia-ring" cx="200" cy="318" r="56" fill="none" stroke="#a8f0d4" strokeWidth="8" />

      {/* scan sweep line */}
      <rect className="ia-sweep" x="126" y="60" width="148" height="3" rx="1.5" fill="#9ff5d6" />
    </svg>
  )
}
