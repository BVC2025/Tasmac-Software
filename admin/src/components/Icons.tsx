import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>
const I = ({ children, ...p }: P) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden {...p}>
    {children}
  </svg>
)

export const GridIcon = (p: P) => <I {...p}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></I>
export const BellIcon = (p: P) => <I {...p}><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0" /></I>
export const ReceiptIcon = (p: P) => <I {...p}><path d="M4 2v20l3-2 3 2 2-2 2 2 3-2 3 2V2l-3 2-3-2-2 2-2-2-3 2zM8 9h8M8 13h8M8 17h5" /></I>
export const ListIcon = (p: P) => <I {...p}><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></I>
export const QrIcon = (p: P) => <I {...p}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3" /></I>
export const ScanIcon = (p: P) => <I {...p}><path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 12h10" /></I>
export const MessageIcon = (p: P) => <I {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></I>
export const ChartIcon = (p: P) => <I {...p}><path d="M3 3v18h18M8 17v-5M13 17V8M18 17v-9" /></I>
export const MachineIcon = (p: P) => <I {...p}><rect x="4" y="2" width="16" height="20" rx="2" /><circle cx="12" cy="9" r="3" /><path d="M9 17h6" /></I>
export const TagIcon = (p: P) => <I {...p}><path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8zM7 7h.01" /></I>
export const UsersIcon = (p: P) => <I {...p}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8" /><circle cx="9" cy="7" r="4" /></I>
export const ShieldIcon = (p: P) => <I {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4" /></I>
export const LogoutIcon = (p: P) => <I {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></I>
export const EyeIcon = (p: P) => <I {...p}><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></I>
export const EyeOffIcon = (p: P) => <I {...p}><path d="M9.9 4.2A10 10 0 0 1 12 4c6.4 0 10 8 10 8a17 17 0 0 1-2.2 3.3M6.6 6.6C3.9 8.4 2 12 2 12s3.6 8 10 8a9.6 9.6 0 0 0 5.4-1.6M14.1 14.1a3 3 0 1 1-4.2-4.2M2 2l20 20" /></I>
export const UserIcon = (p: P) => <I {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></I>
export const LockIcon = (p: P) => <I {...p}><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></I>
export const RupeeIcon = (p: P) => <I {...p}><path d="M6 3h12M6 8h12M6 13l8.5 8M6 13h3a5 5 0 0 0 0-10" /></I>
export const BottleIcon = (p: P) => <I {...p}><path d="M10 2h4v3.5l1.6 2.6c.3.5.4 1 .4 1.5V20a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V9.6c0-.5.1-1 .4-1.5L10 5.5z" /><path d="M8 13h8" /></I>
export const ReturnIcon = (p: P) => <I {...p}><path d="M9 14 4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3" /></I>
export const CheckCircleIcon = (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></I>
export const ClockIcon = (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></I>
export const AlertIcon = (p: P) => <I {...p}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" /></I>
export const XCircleIcon = (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="m15 9-6 6M9 9l6 6" /></I>
export const WifiIcon = (p: P) => <I {...p}><path d="M5 12.6a10 10 0 0 1 14 0M8.5 16.1a5 5 0 0 1 7 0M2 8.8a15 15 0 0 1 20 0M12 20h.01" /></I>
export const ActivityIcon = (p: P) => <I {...p}><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></I>
