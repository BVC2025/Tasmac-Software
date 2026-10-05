const VPA_RE = /^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,63}$/
const MOBILE_RE = /^[6-9]\d{9}$/

export interface UpiTarget {
  vpa: string
  name: string | null
}

/** Parse a scanned UPI QR ("upi://pay?pa=x@ybl&pn=Name") or a plain UPI ID. */
export function parseUpiQr(text: string): UpiTarget | null {
  const raw = text.trim()
  if (/^upi:\/\//i.test(raw)) {
    const query = raw.slice(raw.indexOf('?') + 1)
    const params = new URLSearchParams(query)
    const vpa = (params.get('pa') ?? '').trim()
    if (!VPA_RE.test(vpa)) return null
    return { vpa: vpa.toLowerCase(), name: params.get('pn') }
  }
  return VPA_RE.test(raw) ? { vpa: raw.toLowerCase(), name: null } : null
}

export const isValidVpa = (v: string) => VPA_RE.test(v.trim())

export function normalizeMobile(v: string): string | null {
  let d = v.replace(/\D/g, '')
  if (d.length === 12 && d.startsWith('91')) d = d.slice(2)
  return MOBILE_RE.test(d) ? d : null
}

export const UPI_HANDLES = ['@ybl', '@okaxis', '@oksbi', '@okhdfcbank', '@okicici', '@paytm', '@ibl', '@axl', '@upi']
