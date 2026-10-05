import type { ReactNode } from 'react'

/** A message that stays on screen until the thing it describes changes. */
export function Notice({ tone, children }: { tone: 'error' | 'success' | 'info'; children: ReactNode }) {
  return (
    <p className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </p>
  )
}

export function Loading({ what }: { what: string }) {
  return <p className="muted loading">Loading {what}…</p>
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty-note">{children}</p>
}
