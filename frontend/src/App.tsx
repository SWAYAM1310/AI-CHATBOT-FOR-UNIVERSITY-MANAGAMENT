import { useCallback, useEffect, useMemo, useState } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { api } from './api'
import { Login } from './Login'
import { PortalContext } from './portal/context'
import { PortalRoutes } from './portal/PortalRoutes'
import { loadSession, saveSession } from './session'
import type { Me, Session } from './types'

export default function App() {
  const [session, setSession] = useState<Session | null>(() => loadSession())
  const [me, setMe] = useState<Me | null>(null)

  const signOut = useCallback(() => {
    saveSession(null)
    setSession(null)
  }, [])

  const refreshMe = useCallback(() => {
    api
      .me()
      .then(setMe)
      .catch(() => undefined) // the next full load will sort out an expired token
  }, [])

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
  }, [session, signOut])

  const portal = useMemo(
    () => (session ? { session, me, refreshMe, signOut } : null),
    [session, me, refreshMe, signOut],
  )

  function signIn(s: Session) {
    saveSession(s)
    window.history.replaceState(null, '', '/') // signing in always lands on Home, whatever URL was open
    setSession(s)
  }

  if (!portal) return <Login onSignedIn={signIn} />
  return (
    <BrowserRouter>
      <PortalContext.Provider value={portal}>
        <PortalRoutes role={portal.session.role} />
      </PortalContext.Provider>
    </BrowserRouter>
  )
}
