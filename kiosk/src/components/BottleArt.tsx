/**
 * Realistic-looking bottle and sticker artwork for the check screens (pure SVG, no photos).
 *
 * Every code drawn here is a DUMMY: the QR has the three corner squares but random
 * modules and no format information, so no scanner can decode it; the barcode has
 * no digits. No brand names or logos.
 */

/** Deterministic pseudo-random QR-looking matrix (not a real QR: nothing to decode). */
function dummyQr(size: number, seed: number): boolean[][] {
  let x = seed
  const rnd = () => {
    x = (x * 1103515245 + 12345) & 0x7fffffff
    return x / 0x7fffffff
  }
  const m = Array.from({ length: size }, () => Array.from({ length: size }, () => rnd() > 0.52))
  const finder = (r0: number, c0: number) => {
    for (let r = -1; r <= 7; r++)
      for (let c = -1; c <= 7; c++) {
        const rr = r0 + r
        const cc = c0 + c
        if (rr < 0 || cc < 0 || rr >= size || cc >= size) continue
        const ring = Math.max(Math.abs(r - 3), Math.abs(c - 3))
        m[rr][cc] = r >= 0 && c >= 0 && r <= 6 && c <= 6 && ring !== 2
      }
  }
  finder(0, 0)
  finder(0, size - 7)
  finder(size - 7, 0)
  return m
}

function DummyQr({ x, y, size, seed = 7, cells = 21 }: { x: number; y: number; size: number; seed?: number; cells?: number }) {
  const m = dummyQr(cells, seed)
  const s = size / cells
  return (
    <g>
      <rect x={x - s} y={y - s} width={size + 2 * s} height={size + 2 * s} fill="#fff" />
      {m.flatMap((row, r) =>
        row.map((on, c) => (on ? <rect key={`${r}-${c}`} x={x + c * s} y={y + r * s} width={s + 0.05} height={s + 0.05} fill="#111" /> : null)),
      )}
    </g>
  )
}

function DummyBarcode({ x, y, w, h, seed = 3 }: { x: number; y: number; w: number; h: number; seed?: number }) {
  let v = seed
  const bars: { x: number; w: number }[] = []
  let cx = x
  while (cx < x + w - 2) {
    v = (v * 1103515245 + 12345) & 0x7fffffff
    const bw = 1 + (v % 3)
    const gap = 1 + ((v >> 3) % 3)
    if (cx + bw > x + w) break
    bars.push({ x: cx, w: bw })
    cx += bw + gap
  }
  return (
    <g>
      <rect x={x - 6} y={y - 6} width={w + 12} height={h + 12} fill="#fff" rx="2" />
      {bars.map((b, i) => <rect key={i} x={b.x} y={y} width={b.w} height={h} fill="#111" />)}
    </g>
  )
}

function GlassDefs() {
  return (
    <defs>
      <linearGradient id="ba-glass" x1="0" x2="1">
        <stop offset="0" stopColor="#2a1203" />
        <stop offset="0.18" stopColor="#6b3409" />
        <stop offset="0.38" stopColor="#b8701f" />
        <stop offset="0.5" stopColor="#d18a33" />
        <stop offset="0.7" stopColor="#7a3e0c" />
        <stop offset="1" stopColor="#241002" />
      </linearGradient>
      <linearGradient id="ba-cap" x1="0" x2="1">
        <stop offset="0" stopColor="#7a6a2e" />
        <stop offset="0.45" stopColor="#f3e3a1" />
        <stop offset="1" stopColor="#6d5d24" />
      </linearGradient>
      <linearGradient id="ba-label" x1="0" x2="1">
        <stop offset="0" stopColor="#b9b2a2" />
        <stop offset="0.45" stopColor="#f7f2e6" />
        <stop offset="1" stopColor="#9d9686" />
      </linearGradient>
      <linearGradient id="ba-shade" x1="0" x2="1">
        <stop offset="0" stopColor="#000" stopOpacity="0.55" />
        <stop offset="0.3" stopColor="#000" stopOpacity="0" />
        <stop offset="0.7" stopColor="#000" stopOpacity="0" />
        <stop offset="1" stopColor="#000" stopOpacity="0.6" />
      </linearGradient>
      <radialGradient id="ba-glow" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor="#22c55e" stopOpacity="0.25" />
        <stop offset="1" stopColor="#22c55e" stopOpacity="0" />
      </radialGradient>
    </defs>
  )
}

const BOTTLE_PATH =
  'M86 34 L114 34 L116 150 C118 186 160 200 160 252 L160 490 Q160 506 144 506 L56 506 Q40 506 40 490 L40 252 C40 200 82 186 84 150 Z'

/** Full amber glass bottle; its label slides sideways so the bottle looks like it turns on the rollers. */
export function RealBottle({ className = '', turning = true }: { className?: string; turning?: boolean }) {
  return (
    <svg viewBox="0 0 200 540" className={className} role="img" aria-label="Bottle">
      <GlassDefs />
      <defs>
        <clipPath id="ba-body">
          <path d={BOTTLE_PATH} />
        </clipPath>
      </defs>
      <ellipse cx="100" cy="512" rx="78" ry="10" fill="#000" opacity="0.45" />
      <path d={BOTTLE_PATH} fill="url(#ba-glass)" />
      <g clipPath="url(#ba-body)">
        {/* label band that wraps around the bottle: two copies side by side, sliding */}
        <g className={turning ? 'ba-turn' : ''}>
          {[0, 160].map((dx) => (
            <g key={dx} transform={`translate(${dx} 0)`}>
              <rect x="20" y="300" width="160" height="150" fill="url(#ba-label)" />
              <rect x="20" y="300" width="160" height="22" fill="#1e3a5f" />
              <rect x="20" y="428" width="160" height="22" fill="#1e3a5f" />
              <circle cx="100" cy="368" r="26" fill="none" stroke="#1e3a5f" strokeWidth="5" />
              <rect x="62" y="402" width="76" height="7" rx="3" fill="#1e3a5f" opacity="0.7" />
              <rect x="74" y="414" width="52" height="5" rx="2" fill="#1e3a5f" opacity="0.5" />
            </g>
          ))}
        </g>
        {/* neck sticker (refund QR) */}
        <g className={turning ? 'ba-turn' : ''}>
          {[0, 160].map((dx) => (
            <g key={dx} transform={`translate(${dx} 0)`}>
              <rect x="80" y="92" width="40" height="46" fill="#f8fafc" />
              <rect x="80" y="92" width="40" height="7" fill="#1d4ed8" />
              <DummyQr x={88} y={104} size={24} cells={13} seed={11} />
            </g>
          ))}
        </g>
        <rect x="0" y="0" width="200" height="540" fill="url(#ba-shade)" />
      </g>
      {/* glass shine */}
      <path d="M58 262 Q56 380 60 488" stroke="#fff" strokeWidth="7" strokeLinecap="round" opacity="0.28" fill="none" />
      <path d="M92 40 L93 146" stroke="#fff" strokeWidth="4" strokeLinecap="round" opacity="0.3" />
      {/* crown cap */}
      <rect x="80" y="14" width="40" height="24" rx="4" fill="url(#ba-cap)" />
      {[84, 90, 96, 102, 108, 114].map((x) => <rect key={x} x={x} y="30" width="2" height="8" fill="#5c4d1a" opacity="0.6" />)}
    </svg>
  )
}

/**
 * Close-up of the sticker being read. kind = refund: neck sticker with a QR;
 * kind = mfg: back label with a barcode and a small QR.
 */
export function StickerCloseup({ kind, className = '' }: { kind: 'refund' | 'mfg'; className?: string }) {
  return (
    <svg viewBox="0 0 400 300" className={className} role="img" aria-label={kind === 'refund' ? 'Refund QR sticker' : 'Manufacturing label'}>
      <GlassDefs />
      <defs>
        <linearGradient id="ba-glass-h" x1="0" x2="1">
          <stop offset="0" stopColor="#1c0b01" />
          <stop offset="0.25" stopColor="#7a3e0c" />
          <stop offset="0.5" stopColor="#c98431" />
          <stop offset="0.75" stopColor="#7a3e0c" />
          <stop offset="1" stopColor="#1c0b01" />
        </linearGradient>
        <clipPath id="ba-cyl">
          <rect x={kind === 'refund' ? 95 : 30} y="-10" width={kind === 'refund' ? 210 : 340} height="320" rx="30" />
        </clipPath>
      </defs>
      <rect x="0" y="0" width="400" height="300" fill="url(#ba-glow)" />
      {/* glass cylinder seen up close */}
      <rect x={kind === 'refund' ? 95 : 30} y="-10" width={kind === 'refund' ? 210 : 340} height="320" fill="url(#ba-glass-h)" />
      <g clipPath="url(#ba-cyl)">
        <g className="ba-turn-in">
          {kind === 'refund' ? (
            <g>
              <rect x="128" y="58" width="144" height="184" rx="6" fill="#f8fafc" />
              <rect x="128" y="58" width="144" height="24" rx="6" fill="#1d4ed8" />
              <rect x="146" y="66" width="70" height="8" rx="3" fill="#fff" opacity="0.85" />
              <DummyQr x={152} y={94} size={96} cells={21} seed={7} />
              <rect x="150" y="222" width="100" height="8" rx="3" fill="#1d4ed8" opacity="0.5" />
            </g>
          ) : (
            <g>
              <rect x="60" y="40" width="280" height="220" rx="6" fill="#f3efe3" />
              <rect x="60" y="40" width="280" height="26" rx="6" fill="#1e3a5f" />
              {[84, 98, 112, 126, 140, 154].map((y) => <rect key={y} x="78" y={y} width={120 - (y % 3) * 14} height="6" rx="3" fill="#1e3a5f" opacity="0.35" />)}
              <DummyBarcode x={86} y={182} w={150} h={52} seed={5} />
              <DummyQr x={262} y={92} size={62} cells={17} seed={23} />
            </g>
          )}
        </g>
        <rect x="0" y="-10" width="400" height="320" fill="url(#ba-shade)" opacity="0.8" />
      </g>
      <path d={kind === 'refund' ? 'M128 -10 L128 310' : 'M70 -10 L70 310'} stroke="#fff" strokeWidth="6" opacity="0.18" />
    </svg>
  )
}
