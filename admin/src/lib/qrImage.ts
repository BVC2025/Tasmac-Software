import jsQR from 'jsqr'

const MAX_SIDE = 1600

/** Codes in one canvas: jsQR finds one code per pass, so each found code is painted over and the
 *  canvas is scanned again. */
function scan(ctx: CanvasRenderingContext2D, w: number, h: number, found: Set<string>, max: number) {
  for (let i = 0; i < max; i++) {
    const img = ctx.getImageData(0, 0, w, h)
    const code = jsQR(img.data, w, h, { inversionAttempts: 'attemptBoth' })
    if (!code?.data) return
    found.add(code.data)
    const l = code.location
    const pad = 12
    ctx.fillStyle = '#fff'
    ctx.beginPath()
    ctx.moveTo(l.topLeftCorner.x - pad, l.topLeftCorner.y - pad)
    ctx.lineTo(l.topRightCorner.x + pad, l.topRightCorner.y - pad)
    ctx.lineTo(l.bottomRightCorner.x + pad, l.bottomRightCorner.y + pad)
    ctx.lineTo(l.bottomLeftCorner.x - pad, l.bottomLeftCorner.y + pad)
    ctx.closePath()
    ctx.fill()
  }
}

/** Every QR in a photo. jsQR often fails when two codes are in view (a bottle photo usually has the
 *  refund and the manufacturing QR), so the photo is also scanned in overlapping pieces. */
export async function readQrCodes(file: Blob, max = 4): Promise<string[]> {
  const bmp = await createImageBitmap(file)
  const scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height))
  const W = Math.round(bmp.width * scale)
  const H = Math.round(bmp.height * scale)

  // whole photo, halves, then a 3x3 grid of overlapping windows (each 1/2 of the photo)
  const windows: [number, number, number, number][] = [[0, 0, 1, 1], [0, 0, 0.55, 1], [0.45, 0, 0.55, 1], [0, 0, 1, 0.55], [0, 0.45, 1, 0.55]]
  for (const y of [0, 0.25, 0.5]) for (const x of [0, 0.25, 0.5]) windows.push([x, y, 0.5, 0.5])

  const found = new Set<string>()
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return []
  for (const [x, y, w, h] of windows) {
    canvas.width = Math.round(W * w)
    canvas.height = Math.round(H * h)
    ctx.drawImage(bmp, (x * W) / scale, (y * H) / scale, (w * W) / scale, (h * H) / scale, 0, 0, canvas.width, canvas.height)
    scan(ctx, canvas.width, canvas.height, found, max)
    if (found.size >= max) break
  }
  bmp.close()
  return [...found]
}
