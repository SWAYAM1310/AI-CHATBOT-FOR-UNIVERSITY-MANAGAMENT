// The filter controls every list page shares: chips with live counts, a search box, a
// "showing N of M" line and the category tag on a notice. State helpers are in filtering.ts.
import { CATEGORY_LABEL, type Category } from './categories'
import { plural } from './format'

export interface ChipOption<T extends string = string> {
  value: T
  label: string
  count: number
  /** an extra class on the chip, e.g. "overdue" (red count) */
  tone?: string
  /** a class for a small colour swatch before the label, e.g. "cat-exams" */
  swatch?: string
}

/** One row of filter chips: "All", then one chip per option. A chip with nothing in it is hidden unless it is chosen. */
export function FilterChips<T extends string>({
  label,
  options,
  value,
  onChange,
  total,
}: {
  label: string
  options: ChipOption<T>[]
  value: T | ''
  onChange: (value: T | '') => void
  total: number
}) {
  const visible = options.filter((o) => o.count > 0 || o.value === value)
  // nothing to tell apart: no options, or one option that holds everything "All" does
  if (visible.length === 0 || (visible.length === 1 && visible[0].count === total && value === '')) return null
  return (
    <div className="chips" role="group" aria-label={label}>
      <button type="button" className={value === '' ? 'chip active' : 'chip'} aria-pressed={value === ''} onClick={() => onChange('')}>
        All <span className="chip-count">{total}</span>
      </button>
      {visible.map((o) => (
        <button
          key={o.value}
          type="button"
          className={['chip', o.tone, value === o.value && 'active'].filter(Boolean).join(' ')}
          aria-pressed={value === o.value}
          onClick={() => onChange(value === o.value ? '' : o.value)}
        >
          {o.swatch && <span className={`swatch ${o.swatch}`} aria-hidden="true" />}
          {o.label} <span className="chip-count">{o.count}</span>
        </button>
      ))}
    </div>
  )
}

export function SearchField({ value, onChange, label, placeholder }: { value: string; onChange: (value: string) => void; label: string; placeholder: string }) {
  return (
    <label className="field-inline">
      <span className="sr-only">{label}</span>
      <input type="search" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}

/** "Showing 4 of 33 notices. Clear filters" while a filter is on; nothing otherwise. */
export function FilterSummary({ shown, total, noun, active, onClear }: { shown: number; total: number; noun: [string, string]; active: boolean; onClear: () => void }) {
  if (!active) return null
  return (
    <p className="filter-summary small muted" aria-live="polite">
      Showing {shown} of {plural(total, noun[0], noun[1])}.
      <button type="button" className="linklike" onClick={onClear}>
        Clear filters
      </button>
    </p>
  )
}

/** What a notice is about, as a small coloured label. */
export function CategoryTag({ category }: { category: Category }) {
  return <span className={`cat-tag cat-${category}`}>{CATEGORY_LABEL[category]}</span>
}
