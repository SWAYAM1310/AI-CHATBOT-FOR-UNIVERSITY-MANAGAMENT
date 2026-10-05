import type { CourseAttendance } from '../../types'
import { plural } from '../format'
import { Empty } from '../ui'
import { StudentPage } from './StudentPage'

function AttendanceRow({ c, floor }: { c: CourseAttendance; floor: number }) {
  const note = c.total === 0 ? 'No classes held yet.' : c.below_threshold
    ? `Attend the next ${plural(c.recover ?? 0, 'class', 'classes')} in a row to reach ${floor}%.`
    : c.can_skip === 0
      ? `Right on the line: missing one class drops you below ${floor}%.`
      : `You can miss ${plural(c.can_skip ?? 0, 'more class', 'more classes')} and stay at ${floor}%.`
  return (
    <li className="bar-row">
      <span className="bar-name">
        <strong>{c.name}</strong>
        <span className="mono muted small">{c.course}</span>
      </span>
      <span className="bar-track" role="img" aria-label={`${c.percent}% attended; the minimum is ${floor}%`}>
        <span className={`bar-fill${c.below_threshold ? ' short' : ''}`} style={{ width: `${Math.min(c.percent, 100)}%` }} />
        <span className="bar-floor" style={{ left: `${floor}%` }} />
      </span>
      <span className={`bar-pct${c.below_threshold ? ' short' : ''}`}>{c.total === 0 ? '-' : `${c.percent}%`}</span>
      <span className="bar-note muted small">
        {c.attended} of {c.total} classes. {note}
      </span>
    </li>
  )
}

export function StudentAttendance() {
  return (
    <StudentPage title="Attendance" lede={(d) => `Every course this term, against the ${d.attendance.threshold}% minimum.`}>
      {(d) => {
        const { threshold: floor, courses } = d.attendance
        const short = courses.filter((c) => c.below_threshold)
        if (courses.length === 0) return <Empty>You are not enrolled in any course this term.</Empty>
        return (
          <>
            {short.length > 0 && (
              <section className="block" aria-labelledby="short-h">
                <h2 id="short-h">Needs your attention</h2>
                <ul className="attention">
                  {short.map((c) => (
                    <li key={c.course} className="alert">
                      <strong>{c.name}</strong>: {c.percent}% attended, below the {floor}% you need. Attend the next{' '}
                      {plural(c.recover ?? 0, 'class', 'classes')} in a row to get back to {floor}%.
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="block" aria-labelledby="att-h">
              <h2 id="att-h">By course</h2>
              <p className="lead">
                {d.attendance.overall_percent === null
                  ? 'No classes have been held yet.'
                  : short.length === 0
                    ? `${d.attendance.overall_percent}% across all your courses, and none is below ${floor}%.`
                    : `${d.attendance.overall_percent}% across all your courses, but ${plural(short.length, 'course is', 'courses are')} below ${floor}%.`}
              </p>
              <ul className="bars">
                {courses.map((c) => (
                  <AttendanceRow key={c.course} c={c} floor={floor} />
                ))}
              </ul>
            </section>
          </>
        )
      }}
    </StudentPage>
  )
}
