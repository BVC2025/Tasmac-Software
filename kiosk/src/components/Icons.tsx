import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>
const base = (p: P) => ({
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  viewBox: '0 0 24 24',
  ...p,
})

export const BottleIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M10 2h4v3.5l1.6 2.6c.3.5.4 1 .4 1.5V20a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V9.6c0-.5.1-1 .4-1.5L10 5.5z" />
    <path d="M8 13h8M8 17h8" />
  </svg>
)
export const QrIcon = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3" />
  </svg>
)
export const MicIcon = (p: P) => (
  <svg {...base(p)}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8" />
  </svg>
)
export const KeypadIcon = (p: P) => (
  <svg {...base(p)}>
    <rect x="2" y="5" width="20" height="14" rx="2" />
    <path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 12.5h.01M10 12.5h.01M14 12.5h.01M18 12.5h.01M7 16h10" />
  </svg>
)
export const CheckIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
)
export const XIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
)
export const AlertIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" />
  </svg>
)
export const ClockIcon = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
)
export const ArrowLeftIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M19 12H5M12 19l-7-7 7-7" />
  </svg>
)
export const BackspaceIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M21 5H9l-6 7 6 7h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1zM17 9l-5 6M12 9l5 6" />
  </svg>
)
export const WrenchIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M14.7 6.3a4 4 0 0 0 5 5L21 13l-8 8-3-3 6.7-6.7a4 4 0 0 0-5-5L10 4.6 12 3z" />
  </svg>
)
export const SmsIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    <path d="M8 9h8M8 13h5" />
  </svg>
)
export const SpeakerIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14" />
  </svg>
)
export const SpeakerOffIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M11 5 6 9H2v6h4l5 4zM22 9l-6 6M16 9l6 6" />
  </svg>
)
