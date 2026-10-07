/** Which browser camera the kiosk uses for the UPI QR scan (chosen in the DEV panel). */
const KEY = 'rvm-kiosk-camera'

export function getCameraId(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setCameraId(id: string | null): void {
  try {
    if (id) localStorage.setItem(KEY, id)
    else localStorage.removeItem(KEY)
  } catch {
    /* storage unavailable */
  }
}

export function videoConstraints(): MediaTrackConstraints {
  const id = getCameraId()
  return id ? { deviceId: { exact: id }, width: 1280, height: 720 } : { facingMode: 'user', width: 640, height: 480 }
}
