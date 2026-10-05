import { Link } from 'react-router-dom'
import type { FacultyDashboard, TodayClass } from '../../types'
import { usePortal } from '../context'
import { clockNow, firstName, fullDate, greeting, plural, sectionLabel, todayISO } from '../format'
import { PageHeader } from '../PageHeader'
import { ThoughtOfTheDay } from '../Thought'
import { SLOT_TAG, slotStates, useClock, type SlotState } from '../today'
import { Empty, Loading, Notice } from '../ui'
import { useFacultyDashboard } from './dashboard'

const SUNDAY = 6 // the timetable runs Monday to Saturday

const where = (c: TodayClass) => (c.room ? ` in room ${c.room}` : '')

/** The line that opens the day: what is on, what is happening now, what still needs attendance. */
function todayLine(d: FacultyDashboard, states: SlotState[]): string {
  const slots = d.today
  const n = slots.length
  if (n === 0) {
    return d.weekday === SUNDAY
      ? 'No classes today. Enjoy your Sunday.'
      : 'No classes on your timetable today. A good day for marking or planning.'
  }
  const on = slots.filter((_, i) => states[i] === 'now')
  const done = states.filter((s) => s === 'done').length
  const later = states.filter((s) => s === 'later' || s === 'next').length
  const next = slots[states.indexOf('next')]

  let line: string
  if (on.length === 1) {
    line = `You're teaching ${on[0].name} (${sectionLabel(on[0])}) right now, until ${on[0].end_time}.`
  } else if (on.length > 1) {
    line = `You have ${on.length} classes on right now, ${on.map((c) => c.name).join(' and ')}, until ${on[0].end_time}.`
  } else if (done === n) {
    line = `That's all your classes for today: ${n === 1 ? 'the one class is' : `all ${n} are`} over.`
  } else if (done > 0 && next) {
    line = `Next up is ${next.name} at ${next.start_time}${where(next)}. ${done} of ${n} done.`
  } else {
    line = `You have ${plural(n, 'class', 'classes')} today, starting with ${slots[0].name} at ${slots[0].start_time}${where(slots[0])}.`
  }
  if (on.length > 0) line += later === 0 ? ' It is your last class today.' : ` ${plural(later, 'more class', 'more classes')} after this.`

  // attendance is due once a class has begun
  const unmarked = slots.filter((c, i) => (states[i] === 'now' || states[i] === 'done') && !c.attendance_marked).length
  if (unmarked > 0) {
    line += ` Attendance is still to be taken for ${plural(unmarked, 'class that has', 'classes that have')} started.`
  } else if (done + on.length > 0) {
    line += ' Attendance is up to date.'
  }
  return line
}

export function FacultyHome() {
  const { me } = usePortal()
  const { data: d, error } = useFacultyDashboard()
  const clock = useClock()
  const name = firstName(me?.full_name ?? d?.faculty.full_name)
  const day = d?.date ?? todayISO()
  const states = d ? slotStates(d.today, d.date === todayISO(), clockNow(clock)) : []

  return (
    <div className="page">
      <PageHeader
        eyebrow={fullDate(day)}
        title={name ? `${greeting(clock)}, ${name}` : 'Welcome'}
        lede={
          d
            ? `Welcome back to UniAssist. You teach ${plural(d.courses, 'section')} to ${plural(d.students, 'student')} this term.`
            : 'Welcome back to UniAssist.'
        }
      />

      <ThoughtOfTheDay date={day} />

      {error && <Notice tone="error">{error}</Notice>}
      {!d && !error && <Loading what="your day" />}

      {d && (
        <section className="block" aria-labelledby="today-h">
          <h2 id="today-h">Today</h2>
          <p className="lead">{todayLine(d, states)}</p>
          {d.today.length === 0 ? (
            <Empty>Nothing on your timetable.</Empty>
          ) : (
            <ol className="timeline">
              {d.today.map((c, i) => (
                <li key={`${c.offering_id}-${c.start_time}`} className={`timeline-row slot-${states[i]}`}>
                  <span className="timeline-time">
                    {c.start_time}
                    <small>to {c.end_time}</small>
                  </span>
                  <span className="timeline-what">
                    <strong>{c.name}</strong>
                    <span className="muted small">
                      {c.course}, {sectionLabel(c)}
                      {c.room ? `, room ${c.room}` : ''}
                    </span>
                  </span>
                  <span className="timeline-end">
                    <span className={`slot-tag ${states[i]}`}>{SLOT_TAG[states[i]]}</span>
                    {c.attendance_marked ? (
                      <Link className="btn" to={`/calendar/${d.date}?offering=${c.offering_id}`}>
                        Attendance recorded
                      </Link>
                    ) : (
                      <Link className="btn primary" to={`/calendar/${d.date}?offering=${c.offering_id}`}>
                        Take attendance
                      </Link>
                    )}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  )
}
