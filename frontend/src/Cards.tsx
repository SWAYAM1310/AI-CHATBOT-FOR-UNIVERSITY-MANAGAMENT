import { useMemo, useState } from 'react'
import type { Card } from './types'

// Typed cards from the backend (app/ai/cards.py). Each one draws what the
// prose says: bars against the 75% line, the week as a grid, a table that
// sorts. Anything unknown falls back to its JSON so nothing is silently lost.

interface AttendanceCard {
  type: 'attendance'
  threshold: number
  rows: { course: string; name: string; attended: number; total: number; percent: number }[]
}
interface MarksCard {
  type: 'marks'
  rows: { course: string; assessment: string; score: number | null; max_marks: number | null; absent: boolean }[]
}
interface TimetableCard {
  type: 'timetable'
  rows: { day: number; start: string; end: string; course: string; name: string; kind: string | null; room: string | null }[]
}
interface StudentTableCard {
  type: 'student_table'
  title: string
  columns: string[]
  rows: (string | number | boolean | null)[][]
  total: number
}
interface DeniedCard {
  type: 'denied'
  tool: string
}

export function DataCard({ card }: { card: Card }) {
  switch (card.type) {
    case 'attendance':
      return <Attendance card={card as unknown as AttendanceCard} />
    case 'marks':
      return <Marks card={card as unknown as MarksCard} />
    case 'timetable':
      return <Timetable card={card as unknown as TimetableCard} />
    case 'student_table':
      return <StudentTable card={card as unknown as StudentTableCard} />
    case 'denied':
      return <Denied card={card as unknown as DeniedCard} />
    default:
      return <pre className="card-raw">{JSON.stringify(card, null, 2)}</pre>
  }
}

// --- attendance: one bar per course, the threshold as a line ------------------

function Attendance({ card }: { card: AttendanceCard }) {
  const t = card.threshold
  return (
    <figure className="card attendance">
      <figcaption>
        Attendance by course — the line marks the {t}% needed to sit the end-semester exam
      </figcaption>
      <ul>
        {card.rows.map((r) => {
          const pct = Math.max(0, Math.min(100, r.percent ?? 0))
          const short = pct < t
          return (
            <li key={`${r.course}-${r.name}`} className={short ? 'short' : ''}>
              <span className="att-label">
                <span className="att-course">{r.course}</span> {r.name}
              </span>
              <span className="att-bar" role="img" aria-label={`${pct}% attendance${short ? ', below the threshold' : ''}`}>
                <span className="att-fill" style={{ width: `${pct}%` }} />
                <span className="att-line" style={{ left: `${t}%` }} />
              </span>
              <span className="att-value">
                {pct}% <span className="muted">({r.attended}/{r.total})</span>
              </span>
            </li>
          )
        })}
      </ul>
    </figure>
  )
}

// --- marks: score out of max per assessment, grouped by course -------------------

function Marks({ card }: { card: MarksCard }) {
  const byCourse = new Map<string, MarksCard['rows']>()
  for (const r of card.rows) byCourse.set(r.course, [...(byCourse.get(r.course) ?? []), r])
  return (
    <figure className="card marks">
      <figcaption>Marks so far</figcaption>
      {[...byCourse.entries()].map(([course, rows]) => (
        <div key={course} className="marks-course">
          <span className="att-course">{course}</span>
          <ul>
            {rows.map((r, i) => {
              const pct = r.max_marks ? Math.round(((r.score ?? 0) / r.max_marks) * 100) : 0
              return (
                <li key={i}>
                  <span className="att-label">{r.assessment}</span>
                  <span className="att-bar" role="img" aria-label={r.absent ? 'absent' : `${r.score} of ${r.max_marks}`}>
                    {!r.absent && <span className="att-fill" style={{ width: `${pct}%` }} />}
                  </span>
                  <span className="att-value">{r.absent ? 'absent' : `${r.score}/${r.max_marks}`}</span>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </figure>
  )
}

// --- timetable: days across, sessions listed in time order ----------------------

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function Timetable({ card }: { card: TimetableCard }) {
  const days = [...new Set(card.rows.map((r) => r.day))].sort((a, b) => a - b)
  return (
    <figure className="card timetable">
      <figcaption>Weekly timetable</figcaption>
      <div className="tt-grid" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(112px, 1fr))` }}>
        {days.map((d) => (
          <section key={d} className="tt-day" aria-label={DAYS[d] ?? `Day ${d}`}>
            <h4>{DAYS[d] ?? `Day ${d}`}</h4>
            {card.rows
              .filter((r) => r.day === d)
              .sort((a, b) => a.start.localeCompare(b.start))
              .map((r, i) => (
                <div key={i} className={`tt-slot ${(r.kind ?? '').toLowerCase().includes('lab') ? 'lab' : ''}`}>
                  <span className="tt-time">
                    {r.start}–{r.end}
                  </span>
                  <span className="tt-name">{r.name}</span>
                  <span className="muted small">
                    {r.course}
                    {r.room ? ` · ${r.room}` : ''}
                  </span>
                </div>
              ))}
          </section>
        ))}
      </div>
    </figure>
  )
}

// --- student table: sortable, exportable ---------------------------------------

function StudentTable({ card }: { card: StudentTableCard }) {
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null)
  const rows = useMemo(() => {
    if (!sort) return card.rows
    const { col, dir } = sort
    return [...card.rows].sort((a, b) => {
      const x = a[col]
      const y = b[col]
      if (x == null) return 1
      if (y == null) return -1
      if (typeof x === 'number' && typeof y === 'number') return (x - y) * dir
      return String(x).localeCompare(String(y)) * dir
    })
  }, [card.rows, sort])

  function toggle(col: number) {
    setSort((s) => (s && s.col === col ? { col, dir: s.dir === 1 ? -1 : 1 } : { col, dir: 1 }))
  }

  function exportCsv() {
    const esc = (v: unknown) => `"${String(v ?? '').replaceAll('"', '""')}"`
    const csv = [card.columns, ...card.rows].map((r) => r.map(esc).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${card.title.replaceAll(' ', '_')}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <figure className="card student-table">
      <figcaption>
        {card.title} — {card.total} {card.total === 1 ? 'row' : 'rows'}
        {card.total > card.rows.length ? ` (first ${card.rows.length} shown)` : ''}
        <button type="button" className="linklike small" onClick={exportCsv}>
          Download CSV
        </button>
      </figcaption>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {card.columns.map((c, i) => (
                <th key={c} aria-sort={sort?.col === i ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" className="th-sort" onClick={() => toggle(i)}>
                    {c.replaceAll('_', ' ')}
                    {sort?.col === i ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {r.map((v, j) => (
                  <td key={j}>{v === null || v === undefined ? '—' : typeof v === 'boolean' ? (v ? 'yes' : 'no') : String(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  )
}

// --- denied: the RBAC story, made visible ------------------------------------------

function Denied({ card }: { card: DeniedCard }) {
  return (
    <aside className="card denied" role="note">
      <strong>Not available to your role.</strong> The request needed <code>{card.tool.replaceAll('_', ' ')}</code>,
      which your account is not allowed to run; the server refused it before any data was read.
    </aside>
  )
}
