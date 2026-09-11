import { useEffect, useState } from 'react'
import { api } from './api'
import { Chat } from './Chat'
import { Login } from './Login'
import { loadSession, saveSession } from './session'
import type { Me, Session } from './types'

export default function App() {
  const [session, setSession] = useState<Session | null>(() => loadSession())
  const [me, setMe] = useState<Me | null>(null)

  useEffect(() => {
    if (!session) {
      setMe(null)
      return
    }
    let cancelled = false
    api
      .me()
      .then((m) => {
        if (!cancelled) setMe(m)
      })
      .catch(() => {
        // an expired or rejected token: back to sign-in rather than a dead screen
        if (!cancelled) signOut()
      })
    return () => {
      cancelled = true
    }
  }, [session])

  function signIn(s: Session) {
    saveSession(s)
    setSession(s)
  }

  function signOut() {
    saveSession(null)
    setSession(null)
  }

  if (!session) return <Login onSignedIn={signIn} />
  return <Chat session={session} me={me} onSignOut={signOut} />
}
