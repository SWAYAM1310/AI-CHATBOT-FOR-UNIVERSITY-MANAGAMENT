// The signed-in session, remembered across reloads. The token is the only
// secret; role and subject are convenience copies of what the token carries.
import { setToken } from './api'
import type { Session } from './types'

const KEY = 'uniassist.session'

export function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const s = JSON.parse(raw) as Session
    setToken(s.token)
    return s
  } catch {
    return null
  }
}

export function saveSession(s: Session | null) {
  setToken(s?.token ?? null)
  try {
    if (s) localStorage.setItem(KEY, JSON.stringify(s))
    else localStorage.removeItem(KEY)
  } catch {
    // storage unavailable: the session lives for this tab only
  }
}
