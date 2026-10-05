// A Monday-first month grid that knows nothing about what a day holds: the caller
// renders each cell's contents and decides which days open somewhere. Below 800px the
// same cells reflow into an agenda list (see calendar.css), so there is one DOM for both.
import { useRef, type CSSProperties, type KeyboardEvent, type MouseEvent, type PointerEvent, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DAYS, monthTitle, shiftMonth, weekdayOf } from '../format'
import { dayTransitionName, navigateWithTransition } from './transition'

export interface MonthCalendarProps<T extends { date: string }> {
  month: string // YYYY-MM
  today: string // YYYY-MM-DD
  days: T[] // may be empty while loading: the grid still draws
  label: string
  renderCell: (date: string, day: T | undefined) => ReactNode
  cellClass?: (date: string, day: T | undefined) => string
  cellLabel?: (date: string, day: T | undefined) => string
  /** Where a day opens, or null when it does not. */
  hrefFor?: (date: string, day: T | undefined) => string | null
  /** A selector on the page `hrefFor` leads to; when given, opening a day morphs its date into that page. */
  morphInto?: (date: string) => string
}

const STEP: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }

export function MonthCalendar<T extends { date: string }>(props: MonthCalendarProps<T>) {
  const { month, today, days, label, renderCell, cellClass, cellLabel, hrefFor, morphInto } = props
  const navigate = useNavigate()
  const gridRef = useRef<HTMLOListElement>(null)

  // the days slide in from the side the month was paged from; the first month just appears
  const shown = useRef({ month, dir: '' })
  if (shown.current.month !== month) shown.current = { month, dir: month > shown.current.month ? 'next' : 'prev' }
  const { dir } = shown.current

  const [y, m] = month.split('-').map(Number)
  const length = new Date(y, m, 0).getDate()
  const lead = weekdayOf(`${month}-01`)
  const trail = (7 - ((lead + length) % 7)) % 7
  const byDate = new Map(days.map((d) => [d.date, d]))
  const dates = Array.from({ length }, (_, i) => `${month}-${String(i + 1).padStart(2, '0')}`)

  // arrow keys walk the days that open somewhere, skipping the ones that do not
  function onKeyDown(e: KeyboardEvent<HTMLOListElement>) {
    const step = STEP[e.key]
    const from = (e.target as HTMLElement).closest<HTMLElement>('[data-date]')?.dataset.date
    if (!step || !from) return
    let i = dates.indexOf(from) + step
    while (i >= 0 && i < length) {
      const el = gridRef.current?.querySelector<HTMLElement>(`a[data-date="${dates[i]}"]`)
      if (el) {
        e.preventDefault()
        el.focus()
        return
      }
      i += step
    }
  }

  // a press ripples out from where the pointer went down
  function press(e: PointerEvent<HTMLAnchorElement>) {
    const el = e.currentTarget
    const box = el.getBoundingClientRect()
    el.style.setProperty('--rx', `${e.clientX - box.left}px`)
    el.style.setProperty('--ry', `${e.clientY - box.top}px`)
    el.classList.remove('is-pressed')
    void el.offsetWidth // restart the animation on a second press
    el.classList.add('is-pressed')
  }

  function open(e: MouseEvent<HTMLAnchorElement>, date: string, href: string) {
    if (!morphInto || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
    if (navigateWithTransition(navigate, href, morphInto(date))) e.preventDefault()
  }

  return (
    <div className="cal" aria-label={label}>
      <div className="cal-weekdays" aria-hidden="true">
        {DAYS.map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
      <ol key={month} className={`cal-grid${dir ? ` is-paged-${dir}` : ''}`} ref={gridRef} onKeyDown={onKeyDown}>
        {Array.from({ length: lead }, (_, i) => (
          <li key={`lead-${i}`} className="cal-pad" aria-hidden="true" />
        ))}
        {dates.map((date, n) => {
          const day = byDate.get(date)
          const href = hrefFor?.(date, day) ?? null
          const wd = weekdayOf(date)
          const cls = [
            'cal-cell',
            wd === 6 && 'is-sunday',
            date === today && 'is-today',
            date < today && 'is-past',
            cellClass?.(date, day),
          ]
            .filter(Boolean)
            .join(' ')
          const body = (
            <>
              <span className="cal-date">
                <span className="cal-num" style={{ viewTransitionName: href && morphInto ? dayTransitionName(date) : undefined }}>
                  {Number(date.slice(8))}
                </span>
                <span className="cal-wd">{DAYS[wd]}</span>
                {date === today && <span className="cal-today-tag">Today</span>}
              </span>
              {renderCell(date, day)}
            </>
          )
          return (
            <li key={date} className="cal-slot" style={{ '--n': lead + n } as CSSProperties}>
              {href ? (
                <Link
                  to={href}
                  className={cls}
                  data-date={date}
                  aria-label={cellLabel?.(date, day)}
                  onPointerDown={press}
                  onAnimationEnd={(e) => e.animationName === 'cal-ripple' && e.currentTarget.classList.remove('is-pressed')}
                  onClick={(e) => open(e, date, href)}
                >
                  {body}
                </Link>
              ) : (
                <div className={cls} data-date={date} aria-label={cellLabel?.(date, day)}>
                  {body}
                </div>
              )}
            </li>
          )
        })}
        {Array.from({ length: trail }, (_, i) => (
          <li key={`trail-${i}`} className="cal-pad" aria-hidden="true" />
        ))}
      </ol>
    </div>
  )
}

export function MonthNav({ month, today, onChange, min, max, children }: {
  month: string
  today: string
  onChange: (month: string) => void
  min?: string | null
  max?: string | null
  children?: ReactNode
}) {
  const thisMonth = today.slice(0, 7)
  return (
    <div className="cal-nav">
      <h2 className="cal-title" aria-live="polite">
        {monthTitle(month)}
      </h2>
      <span className="cal-nav-buttons">
        <button type="button" className="icon-btn" onClick={() => onChange(shiftMonth(month, -1))} disabled={!!min && month <= min} aria-label="Previous month">
          <Chevron dir="left" />
        </button>
        <button type="button" onClick={() => onChange(thisMonth)} disabled={month === thisMonth}>
          Today
        </button>
        <button type="button" className="icon-btn" onClick={() => onChange(shiftMonth(month, 1))} disabled={!!max && month >= max} aria-label="Next month">
          <Chevron dir="right" />
        </button>
      </span>
      {children}
    </div>
  )
}

function Chevron({ dir }: { dir: 'left' | 'right' }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={dir === 'left' ? 'M15 5l-7 7 7 7' : 'M9 5l7 7-7 7'} />
    </svg>
  )
}
