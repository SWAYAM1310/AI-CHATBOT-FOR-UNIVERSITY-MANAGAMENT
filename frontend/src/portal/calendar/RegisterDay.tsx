// The faculty Calendar and the page each of its days opens, /calendar/:date: every class
// timetabled that day, one register at a time, plus any class held off the timetable.
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import type { CalendarDay } from '../../types'
import { batchLabel, longDay, todayISO } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { useLoad } from '../useLoad'
import { RegisterSheet } from './RegisterSheet'
import { TeachingCalendar } from './TeachingCalendar'
import { dayTransitionName, navigateWithTransition } from './transition'

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/
const OFF = new Set(['holiday', 'break'])

/** The selector a calendar day morphs into, and the one a register morphs back into. */
const headingFor = (date: string) => `.reg-day-num[data-date="${date}"]`
const cellFor = (date: string) => `a.cal-cell[data-date="${date}"]`

export function CalendarPage() {
  return (
    <div className="page">
      <PageHeader title="Calendar" lede="Every class you teach this term. Open a day to take or correct its register." />
      <TeachingCalendar dayHref={(date) => `/calendar/${date}`} morphInto={headingFor} />
    </div>
  )
}

export function CalendarRegisterDay() {
  const { date = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const month = date.slice(0, 7)
  const valid = ISO_DAY.test(date)
  const cal = useLoad(() => api.facultyCalendar(month), valid ? `calendar-day-${month}` : null)
  const courses = useLoad(() => api.facultyCourses(), valid ? 'faculty-courses' : null)
  const day = cal.data?.days.find((d) => d.date === date)
  const scheduled = day?.classes ?? []
  const term = cal.data?.term
  const past = date <= todayISO()
  // a class can be recorded on any term day up to today, timetabled or not
  const open = past && !!term?.start && !!term.end && date >= term.start && date <= term.end
  const extra = open ? (courses.data ?? []).filter((c) => !scheduled.some((s) => s.offering_id === c.offering_id)) : []

  const asked = Number(params.get('offering'))
  const chosen = scheduled.find((c) => c.offering_id === asked) ?? extra.find((c) => c.offering_id === asked) ?? scheduled[0]
  const chosenId = chosen?.offering_id
  const roster = useLoad(() => api.roster(chosenId!), chosenId ? `roster-${chosenId}` : null)
  const pick = (id: number) => setParams({ offering: String(id) }, { replace: true })

  if (!valid) return <Navigate to="/calendar" replace />

  return (
    <div className="page">
      <DayHeading date={date} day={day} back={`/calendar?month=${month}`} />
      {cal.error && <Notice tone="error">{cal.error}</Notice>}
      {!cal.data && !cal.error && <Loading what="the day" />}
      {cal.data && scheduled.length === 0 && (
        <Empty>{open ? 'None of your classes is timetabled on this day.' : 'No classes of yours fall on this day.'}</Empty>
      )}

      {(scheduled.length > 1 || (scheduled.length > 0 && extra.length > 0)) && (
        <nav className="reg-classes" aria-label="Classes this day">
          {scheduled.map((c) => (
            <button
              key={c.offering_id}
              type="button"
              className={`reg-class is-${c.status}`}
              aria-current={c.offering_id === chosenId ? 'true' : undefined}
              onClick={() => pick(c.offering_id)}
            >
              <span className="reg-class-code">
                {c.course} <span className="reg-class-batch">{batchLabel(c)}</span>
              </span>
              <span className="reg-class-meta">
                {c.start_time ? `${c.start_time}–${c.end_time}` : 'Off the timetable'}
                {c.status === 'held' ? ', recorded' : ''}
              </span>
            </button>
          ))}
        </nav>
      )}

      {extra.length > 0 && (
        <label className="reg-extra field-inline">
          <span>{scheduled.length ? 'Held another class today?' : 'Record a class held on this day'}</span>
          <select value={extra.some((c) => c.offering_id === chosenId) ? chosenId : ''} onChange={(e) => e.target.value && pick(Number(e.target.value))}>
            <option value="">Choose a section…</option>
            {extra.map((c) => (
              <option key={c.offering_id} value={c.offering_id}>
                {c.course} {batchLabel(c)}, {c.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {chosen && (
        <>
          <h2 className="reg-class-title">
            {chosen.name}
            <span className="muted"> {batchLabel(chosen)}</span>
          </h2>
          {!past ? (
            <Notice tone="info">This class has not happened yet. Its register opens on the day.</Notice>
          ) : roster.error ? (
            <Notice tone="error">{roster.error}</Notice>
          ) : !roster.data || roster.data.offering.offering_id !== chosenId ? (
            <Loading what="the class list" />
          ) : (
            <RegisterSheet
              key={chosenId}
              offeringId={chosenId!}
              date={date}
              students={roster.data.students}
              onSaved={() => {
                roster.reload()
                cal.reload() // an extra class now shows as held
              }}
            />
          )}
        </>
      )}
    </div>
  )
}

function DayHeading({ date, day, back }: { date: string; day: CalendarDay | undefined; back: string }) {
  const navigate = useNavigate()
  const { weekday, date: dayMonth } = longDay(date)
  const [num, ...rest] = dayMonth.split(' ')
  const off = day?.events.filter((e) => OFF.has(e.event_type)) ?? []
  const other = day?.events.filter((e) => !OFF.has(e.event_type)) ?? []

  return (
    <header className={`reg-head${off.length ? ' is-holiday' : ''}`}>
      <Link
        to={back}
        className="reg-back"
        onClick={(e) => {
          if (e.button === 0 && !e.metaKey && !e.ctrlKey && navigateWithTransition(navigate, back, cellFor(date))) e.preventDefault()
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M15 5l-7 7 7 7" />
        </svg>
        Calendar
      </Link>
      <p className="reg-weekday">{weekday}</p>
      <h1 className="reg-day-title">
        <span className="reg-day-num" data-date={date} style={{ viewTransitionName: dayTransitionName(date) }}>
          {num}
        </span>{' '}
        {rest.join(' ')}
      </h1>
      {off.map((e) => (
        <p key={e.event} className="reg-holiday">
          {e.event}. The timetable does not run, but you can still record a class held today.
        </p>
      ))}
      {other.map((e) => (
        <p key={e.event} className={e.event_type === 'exam' ? 'reg-exam' : 'reg-note'}>
          {e.event}
        </p>
      ))}
    </header>
  )
}
