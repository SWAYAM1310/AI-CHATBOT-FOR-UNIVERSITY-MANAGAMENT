import { useState } from 'react'
import type { AnnouncementItem } from '../types'
import { formatDate } from './format'
import { Empty } from './ui'

// who a notice was sent to, widest first
const SCOPES = ['university', 'department', 'course']
const SCOPE_LABEL: Record<string, string> = { university: 'University', department: 'Department', course: 'Course' }

/** Every notice in full, newest first, with a filter by who it was sent to. */
export function AnnouncementFeed({ items }: { items: AnnouncementItem[] }) {
  const [scope, setScope] = useState('')
  if (items.length === 0) return <Empty>No announcements for you right now.</Empty>
  const count = (s: string) => items.filter((a) => a.scope === s).length
  const shown = scope ? items.filter((a) => a.scope === scope) : items
  return (
    <>
      <div className="chips" role="group" aria-label="Filter by who it is for">
        <button type="button" className={scope === '' ? 'chip active' : 'chip'} aria-pressed={scope === ''} onClick={() => setScope('')}>
          All <span className="chip-count">{items.length}</span>
        </button>
        {SCOPES.filter((s) => count(s) > 0).map((s) => (
          <button
            key={s}
            type="button"
            className={scope === s ? 'chip active' : 'chip'}
            aria-pressed={scope === s}
            onClick={() => setScope(scope === s ? '' : s)}
          >
            {SCOPE_LABEL[s]} <span className="chip-count">{count(s)}</span>
          </button>
        ))}
      </div>

      <ul className="plain-list ann-list">
        {shown.map((a, i) => (
          <li key={`${a.posted_at}-${i}`}>
            <span className="ann-head">
              <strong>{a.title}</strong>
              <span className="muted small">
                {SCOPE_LABEL[a.scope] ?? a.scope}
                {a.posted_at ? `, ${formatDate(a.posted_at)}` : ''}
              </span>
            </span>
            {a.body && <p className="ann-body">{a.body}</p>}
          </li>
        ))}
      </ul>
    </>
  )
}
