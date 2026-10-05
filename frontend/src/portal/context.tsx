// What every portal page needs to know about the signed-in person, without
// each one re-fetching it: the session, the /api/me payload, and two actions.
import { createContext, useContext } from 'react'
import type { Me, Session } from '../types'

export interface Portal {
  session: Session
  me: Me | null
  /** Re-read /api/me, e.g. after a profile photo changes. */
  refreshMe: () => void
  signOut: () => void
}

export const PortalContext = createContext<Portal | null>(null)

export function usePortal(): Portal {
  const portal = useContext(PortalContext)
  if (!portal) throw new Error('usePortal must be used inside the signed-in portal')
  return portal
}
