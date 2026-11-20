import { useState } from 'react'
import type { AnnouncementItem } from '../types'
import { CATEGORIES, categorize, categoryOptions, type Category } from './categories'
import { CategoryTag, FilterChips, FilterSummary, SearchField } from './Filters'
import { matchesQuery, useClearParams, useParamFilter } from './filtering'
import { formatDate } from './format'
import { Empty } from './ui'

// who a notice was sent to, widest first
const SCOPES = ['university', 'department', 'course'] as const
type Scope = (typeof SCOPES)[number]
const SCOPE_LABEL: Record<string, string> = { university: 'University', department: 'Department', course: 'Course' }

/** Every notice in full, newest first, filtered by what it is about, who it was sent to and a search. */
export function AnnouncementFeed({ items }: { items: AnnouncementItem[] }) {
  const [category, setCategory] = useParamFilter<Category>('cat', CATEGORIES)
  const [scope, setScope] = useParamFilter<Scope>('from', SCOPES)
  const [query, setQuery] = useState('')
  const clearParams = useClearParams(['cat', 'from'])
  if (items.length === 0) return <Empty>No announcements for you right now.</Empty>

  const tagged = items.map((a) => ({ ...a, category: categorize(a) }))
  // the category counts follow the other two filters, so a chip's number is what it would show
  const narrowed = tagged.filter((a) => (!scope || a.scope === scope) && matchesQuery(query, a.title, a.body))
  const shown = category ? narrowed.filter((a) => a.category === category) : narrowed
  const scopeCount = (s: string) => items.filter((a) => a.scope === s).length
  const active = Boolean(category || scope || query.trim())

  return (
    <>
      <div className="toolbar filter-bar">
        <SearchField label="Search announcements" placeholder="Search announcements" value={query} onChange={setQuery} />
        <label className="field-inline">
          <span>Sent to</span>
          <select value={scope} onChange={(e) => setScope(e.target.value as Scope | '')}>
            <option value="">Everyone ({items.length})</option>
            {SCOPES.filter((s) => scopeCount(s) > 0).map((s) => (
              <option key={s} value={s}>
                {s === 'university' ? 'The whole university' : s === 'department' ? 'My department' : 'My courses'} ({scopeCount(s)})
              </option>
            ))}
          </select>
        </label>
      </div>
      <FilterChips label="Filter by category" options={categoryOptions(narrowed)} value={category} onChange={setCategory} total={narrowed.length} />
      <FilterSummary
        shown={shown.length}
        total={items.length}
        noun={['notice', 'notices']}
        active={active}
        onClear={() => {
          clearParams()
          setQuery('')
        }}
      />

      {shown.length === 0 ? (
        <Empty>No announcement matches these filters.</Empty>
      ) : (
        <ul className="plain-list ann-list">
          {shown.map((a, i) => (
            <li key={`${a.posted_at}-${i}`}>
              <span className="ann-meta">
                <CategoryTag category={a.category} />
                <span className="muted small">
                  {SCOPE_LABEL[a.scope] ?? a.scope}
                  {a.posted_at ? `, ${formatDate(a.posted_at)}` : ''}
                </span>
              </span>
              <strong className="ann-title">{a.title}</strong>
              {a.body && <p className="ann-body">{a.body}</p>}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
