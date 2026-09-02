const STORAGE_KEY = 'fsi.customSessionId'

export function rememberCustomSession(sessionId: string): void {
  const id = sessionId.trim()
  if (!id || typeof sessionStorage === 'undefined') return
  sessionStorage.setItem(STORAGE_KEY, id)
}

export function readCustomSession(): string | null {
  if (typeof sessionStorage === 'undefined') return null
  const value = sessionStorage.getItem(STORAGE_KEY)
  return value && value.trim() ? value.trim() : null
}

export function clearCustomSession(): void {
  if (typeof sessionStorage === 'undefined') return
  sessionStorage.removeItem(STORAGE_KEY)
}
