// A faculty member's month of teaching: what was held, what still needs marking, what
// is coming, and the holidays, breaks and exams that suspend the timetable. Used for all
// of a faculty member's sections (the Calendar page) and for one (a course's Attendance tab).
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import type { CalendarClass, CalendarDay } from '../../types'
import { batchLabel, formatDay, plural, todayISO, weekdayOf } from '../format'
import { Notice } from '../ui'
import { useLoad } from '../useLoad'
import { MonthCalendar, MonthNav } from './MonthCalendar'

const SHOWN = 3 // chips per cell before "+N more"
const OFF = new Set(['holiday', 'break'])

export function presentShare(c: CalendarClass): number | null {
  const present = c.sessions.reduce((n, s) => n + s.present, 0)
  const total = present + c.sessions.reduce((n, s) => n + s.absent, 0)
  return total ? present / total : null
}

const STATUS_WORD = { held: 'held', due: 'not marked yet', upcoming: 'coming up' } as const

export function TeachingCalendar({ offeringId, dayHref, morphInto }: {
  offeringId?: number
  dayHref: (date: string) => string
  morphInto: (date: string) => string
}) {
  const [params, setParams] = useSearchParams()
  const today = todayISO()
  const month = /^\d{4}-\d{2}$/.test(params.get('month') ?? '') ? params.get('month')! : today.slice(0, 7)
  const cal = useLoad(() => api.facultyCalendar(month, offeringId), `calendar-${offeringId ?? 'all'}-${month}`, true)
  const single = offeringId !== undefined

  const data = cal.data?.month === month ? cal.data : null
  const term = data?.term
  const classes = data?.days.flatMap((d) => d.classes) ?? []
  const held = classes.filter((c) => c.status === 'held').length
  const due = classes.filter((c) => c.status === 'due').length

  const inTerm = (date: string) => !!term?.start && !!term.end && date >= term.start && date <= term.end

  return (
    <section className="teaching-cal">
      <MonthNav
        month={month}
        today={today}
        onChange={(m) => setParams((p) => (p.set('month', m), p), { replace: true })}
        min={term?.start?.slice(0, 7)}
        max={term?.end?.slice(0, 7)}
      >
        <p className="cal-summary" aria-live="polite">
          {data &&
            (classes.length === 0
              ? 'No classes this month.'
              : `${plural(held, 'class', 'classes')} held${due ? `, ${due} still to mark` : ''}`)}
        </p>
      </MonthNav>

      {cal.error && <Notice tone="error">{cal.error}</Notice>}

      <div className={`cal-frame${data ? '' : ' is-loading'}`} aria-busy={!data}>
        <MonthCalendar<CalendarDay>
          month={month}
          today={data?.today ?? today}
          days={data?.days ?? []}
          label={single ? 'Attendance calendar for this section' : 'Your teaching calendar'}
          morphInto={morphInto}
          hrefFor={(date, day) => {
            if (!data || date > data.today) return null
            if (day?.classes.length) return dayHref(date)
            return single && inTerm(date) ? dayHref(date) : null
          }}
          cellClass={(date, day) => {
            const types = new Set(day?.events.map((e) => e.event_type))
            return [
              [...types].some((t) => OFF.has(t)) && 'is-holiday',
              types.has('exam') && 'is-exam',
              day?.classes.some((c) => c.status === 'due') && 'has-due',
              !day?.classes.length && !day?.events.length && 'is-quiet',
              data && !inTerm(date) && 'is-outside',
            ]
              .filter(Boolean)
              .join(' ')
          }}
          cellLabel={(date, day) => {
            const parts = [formatDay(date)]
            day?.events.forEach((e) => parts.push(e.event))
            day?.classes.forEach((c) => parts.push(`${c.course} ${batchLabel(c)} ${STATUS_WORD[c.status]}`))
            return parts.join(', ')
          }}
          renderCell={(_, day) => <DayContents day={day} single={single} />}
        />
      </div>

      <Legend />
    </section>
  )
}

/** A multi-day event is named where it starts, and again at the top of each week and month;
 * on the days between, the cell's tint or rule carries it. */
function labelled(e: CalendarDay['events'][number], date: string): boolean {
  return e.start_date === date || weekdayOf(date) === 0 || date.endsWith('-01')
}

function DayContents({ day, single }: { day: CalendarDay | undefined; single: boolean }) {
  if (!day) return null
  const shown = day.classes.slice(0, SHOWN)
  return (
    <>
      {day.events.filter((e) => labelled(e, day.date)).map((e) => (
        <span
          key={e.event}
          className={OFF.has(e.event_type) ? 'cal-holiday' : e.event_type === 'exam' ? 'cal-exam' : 'cal-note'}
        >
          {e.event}
        </span>
      ))}
      {shown.length > 0 && (
        <span className="cal-chips">
          {shown.map((c, i) => (
            <Chip key={c.offering_id} c={c} single={single} index={i} />
          ))}
          {day.classes.length > SHOWN && <span className="cal-more">+{day.classes.length - SHOWN} more</span>}
        </span>
      )}
    </>
  )
}

function Chip({ c, single, index }: { c: CalendarClass; single: boolean; index: number }) {
  const share = presentShare(c)
  const style = { '--share': share ?? 0, '--i': index } as CSSProperties
  const detail = !single
    ? c.name
    : c.status === 'held'
      ? share === null ? 'Recorded' : `${Math.round(share * 100)}% present`
      : c.status === 'due'
        ? 'Not marked'
        : ''
  return (
    <span className={`cal-chip is-${c.status}`} style={style}>
      <span className="cal-chip-head">
        <span className="cal-chip-code">{single ? (c.start_time ?? 'Class') : c.course}</span>
        <span className="cal-chip-batch">{batchLabel(c)}</span>
      </span>
      {detail && <span className="cal-chip-detail">{detail}</span>}
      {c.status === 'held' && <span className="cal-chip-bar" aria-hidden="true" />}
    </span>
  )
}

function Legend() {
  return (
    <ul className="cal-legend" aria-label="Key">
      <li>
        <span className="cal-key is-held" /> Held, with the share present
      </li>
      <li>
        <span className="cal-key is-due" /> Not marked yet
      </li>
      <li>
        <span className="cal-key is-upcoming" /> Coming up
      </li>
      <li>
        <span className="cal-key is-holiday" /> Holiday or break
      </li>
      <li>
        <span className="cal-key is-exam" /> Exam days
      </li>
    </ul>
  )
}
