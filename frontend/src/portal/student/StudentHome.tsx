import type { ClassSlot, StudentDashboard } from '../../types'
import { usePortal } from '../context'
import { clockNow, firstName, fullDate, greeting, plural, todayISO } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { ThoughtOfTheDay } from '../Thought'
import { SLOT_TAG, slotStates, useClock, type SlotState } from '../today'
import { useStudentDashboard } from './dashboard'

const SUNDAY = 6

const where = (c: ClassSlot) => (c.room ? ` in room ${c.room}` : '')

/** The line that opens the day: what is on, what is happening now, or that the day is done. */
function todayLine(d: StudentDashboard, states: SlotState[]): string {
  const slots = d.today
  const n = slots.length
  if (n === 0) {
    return d.weekday === SUNDAY
      ? 'No classes today. Enjoy your Sunday and come back rested.'
      : 'No classes on your timetable today. A good day to revise or catch up on coursework.'
  }
  const now = states.indexOf('now')
  const done = states.filter((s) => s === 'done').length
  if (now >= 0) {
    const after = states.filter((s) => s === 'later').length
    return `You're in ${slots[now].name} right now, until ${slots[now].end_time}. ${after === 0 ? 'It is your last class today.' : `${plural(after, 'more class', 'more classes')} after this.`}`
  }
  if (done === n) return `That's all for today: ${n === 1 ? 'your class is' : `all ${n} of your classes are`} over. See you tomorrow.`
  const next = slots[states.indexOf('next')]
  if (done > 0 && next) {
    return `Next up is ${next.name} at ${next.start_time}${where(next)}. ${done} of ${n} done, ${n - done} to go.`
  }
  const first = slots[0]
  return `You have ${plural(n, 'class', 'classes')} today. The first, ${first.name}, starts at ${first.start_time}${where(first)}. Have a good day!`
}

export function StudentHome() {
  const { me } = usePortal()
  const { data: d, error } = useStudentDashboard()
  const clock = useClock()
  const name = firstName(me?.full_name ?? d?.student.full_name)
  const day = d?.date ?? todayISO()
  const states = d ? slotStates(d.today, d.date === todayISO(), clockNow(clock)) : []

  return (
    <div className="page">
      <PageHeader
        eyebrow={fullDate(day)}
        title={name ? `${greeting(clock)}, ${name}` : 'Welcome'}
        lede={
          d
            ? `Welcome back to UniAssist. ${d.student.dept_code}, semester ${d.student.semester}${d.student.division ? `, division ${d.student.division}` : ''}.`
            : 'Welcome back to UniAssist.'
        }
      />

      <ThoughtOfTheDay date={day} />

      {error && <Notice tone="error">{error}</Notice>}
      {!d && !error && <Loading what="your timetable" />}

      {d && (
        <section className="block" aria-labelledby="today-h">
          <h2 id="today-h">Today</h2>
          <p className="lead">{todayLine(d, states)}</p>
          {d.today.length === 0 ? (
            <Empty>Nothing on your timetable.</Empty>
          ) : (
            <ol className="timeline">
              {d.today.map((c, i) => (
                <li key={`${c.course}-${c.start_time}`} className={`timeline-row student slot-${states[i]}`}>
                  <span className="timeline-time">
                    {c.start_time}
                    <small>to {c.end_time}</small>
                  </span>
                  <span className="timeline-what">
                    <strong>{c.name}</strong>
                    <span className="muted small">
                      {c.course}
                      {c.session_type ? `, ${c.session_type.toLowerCase()}` : ''}
                      {c.room ? `, room ${c.room}` : ''}
                    </span>
                  </span>
                  <span className={`slot-tag ${states[i]}`}>{SLOT_TAG[states[i]]}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  )
}
