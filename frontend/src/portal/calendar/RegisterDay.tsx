// The pages a calendar day opens: the faculty-wide /calendar/:date (every class that day,
// one register at a time) and a course's /courses/:id/attendance/:date (that one class).
import { Link, Navigate, useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import type { CalendarDay } from '../../types'
import type { CourseContext } from '../faculty/CourseLayout'
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

// --- the faculty-wide calendar -----------------------------------------------------------

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
  const cal = useLoad(() => api.facultyCalendar(month), ISO_DAY.test(date) ? `calendar-day-${month}` : null)
  const day = cal.data?.days.find((d) => d.date === date)
  const asked = Number(params.get('offering'))
  const chosen = day?.classes.find((c) => c.offering_id === asked) ?? day?.classes[0]
  const roster = useLoad(() => api.roster(chosen!.offering_id), chosen ? `roster-${chosen.offering_id}` : null)

  if (!ISO_DAY.test(date)) return <Navigate to="/calendar" replace />

  return (
    <div className="page">
      <DayHeading date={date} day={day} back={`/calendar?month=${month}`} backLabel="Calendar" level={1} />
      {cal.error && <Notice tone="error">{cal.error}</Notice>}
      {!cal.data && !cal.error && <Loading what="the day" />}
      {cal.data && !day?.classes.length && <Empty>No classes of yours fall on this day.</Empty>}

      {day && day.classes.length > 0 && (
        <>
          {day.classes.length > 1 && (
            <nav className="reg-classes" aria-label="Classes this day">
              {day.classes.map((c) => (
                <button
                  key={c.offering_id}
                  type="button"
                  className={`reg-class is-${c.status}`}
                  aria-current={c.offering_id === chosen?.offering_id ? 'true' : undefined}
                  onClick={() => setParams({ offering: String(c.offering_id) }, { replace: true })}
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
          {chosen && (
            <>
              <h2 className="reg-class-title">
                {chosen.name}
                <span className="muted"> {batchLabel(chosen)}</span>
              </h2>
              {date > todayISO() ? (
                <Notice tone="info">This class has not happened yet. Its register opens on the day.</Notice>
              ) : roster.error ? (
                <Notice tone="error">{roster.error}</Notice>
              ) : !roster.data || roster.data.offering.offering_id !== chosen.offering_id ? (
                <Loading what="the class list" />
              ) : (
                <RegisterSheet
                  key={chosen.offering_id}
                  offeringId={chosen.offering_id}
                  date={date}
                  students={roster.data.students}
                  onSaved={roster.reload}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

// --- one course ----------------------------------------------------------------------------

/** The course's Attendance tab: its calendar. */
export function CourseCalendar() {
  const { offering } = useOutletContext<CourseContext>()
  const base = `/courses/${offering.offering_id}/attendance`
  return <TeachingCalendar offeringId={offering.offering_id} dayHref={(date) => `${base}/${date}`} morphInto={headingFor} />
}

export function CourseRegisterDay() {
  const { offering, students, reload } = useOutletContext<CourseContext>()
  const { date = '' } = useParams()
  const id = offering.offering_id
  const month = date.slice(0, 7)
  const cal = useLoad(() => api.facultyCalendar(month, id), ISO_DAY.test(date) ? `calendar-day-${id}-${month}` : null)
  const base = `/courses/${id}/attendance`

  if (!ISO_DAY.test(date)) return <Navigate to={base} replace />

  return (
    <>
      <DayHeading date={date} day={cal.data?.days.find((d) => d.date === date)} back={`${base}?month=${month}`} backLabel="Attendance calendar" level={2} />
      {date > todayISO() ? (
        <Notice tone="info">This day has not happened yet. Its register opens on the day.</Notice>
      ) : (
        <RegisterSheet offeringId={id} date={date} students={students} onSaved={reload} />
      )}
    </>
  )
}

// --- shared heading ------------------------------------------------------------------------

function DayHeading({ date, day, back, backLabel, level }: {
  date: string
  day: CalendarDay | undefined
  back: string
  backLabel: string
  level: 1 | 2
}) {
  const navigate = useNavigate()
  const { weekday, date: dayMonth } = longDay(date)
  const [num, ...rest] = dayMonth.split(' ')
  const Heading = level === 1 ? 'h1' : 'h2'
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
        {backLabel}
      </Link>
      <p className="reg-weekday">{weekday}</p>
      <Heading className="reg-day-title">
        <span className="reg-day-num" data-date={date} style={{ viewTransitionName: dayTransitionName(date) }}>
          {num}
        </span>{' '}
        {rest.join(' ')}
      </Heading>
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
