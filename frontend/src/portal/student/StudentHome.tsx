import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import type { CourseAttendance, StudentDashboard } from '../../types'
import { usePortal } from '../context'
import { firstName, formatDate, formatDay, formatMoney, greeting, plural } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { useLoad } from '../useLoad'

const REFRESH_MS = 30_000 // a faculty member's attendance entry shows up here within half a minute
const SUNDAY = 6

interface Attention {
  tone: 'warn' | 'alert'
  text: ReactNode
}

/** What a student should look at first: the places they are short of a rule or owe something. */
function attention(d: StudentDashboard): Attention[] {
  const out: Attention[] = []
  const floor = d.attendance.threshold
  for (const c of d.attendance.courses.filter((c) => c.below_threshold)) {
    out.push({
      tone: 'alert',
      text: (
        <>
          <strong>{c.name}</strong>: {c.percent}% attended, below the {floor}% you need. Attend the next {plural(c.recover ?? 0, 'class', 'classes')} in a row to get back to {floor}%.
        </>
      ),
    })
  }
  for (const f of d.fees.entries.filter((f) => f.status !== 'paid' && f.outstanding > 0)) {
    const late = f.status === 'overdue' || (f.due_date !== null && f.due_date < d.date)
    out.push({
      tone: late ? 'alert' : 'warn',
      text: (
        <>
          <strong>Fee for {f.term}</strong>: {formatMoney(f.outstanding)} still to pay{f.due_date ? `, ${late ? 'was due' : 'due'} ${formatDate(f.due_date)}` : ''}.
        </>
      ),
    })
  }
  const missing = d.assignments.filter((a) => a.status === 'missing')
  if (missing.length > 0) {
    out.push({
      tone: 'warn',
      text: (
        <>
          <strong>{plural(missing.length, 'assignment')} not submitted</strong>: {missing.map((a) => `${a.title ?? 'Assignment'} (${a.course})`).join(', ')}.
        </>
      ),
    })
  }
  return out
}

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

export function StudentHome() {
  const { me } = usePortal()
  const { data: d, error } = useLoad(() => api.studentDashboard(), 'student-dashboard', true, REFRESH_MS)
  const name = firstName(me?.full_name ?? d?.student.full_name)
  const todo = d ? attention(d) : []

  const upcoming = d?.exams.filter((e) => e.date >= d.date) ?? []
  const open = d?.assignments.filter((a) => a.status !== 'submitted') ?? []

  return (
    <div className="page">
      <PageHeader
        title={name ? `${greeting()}, ${name}` : 'Home'}
        lede={d ? `${formatDay(d.date)}. ${d.student.dept_code}, semester ${d.student.semester}${d.student.cgpa !== null ? `, CGPA ${d.student.cgpa}` : ''}.` : undefined}
      />
      {error && <Notice tone="error">{error}</Notice>}
      {!d && !error && <Loading what="your records" />}

      {d && (
        <>
          <section className="block" aria-labelledby="att-h">
            <h2 id="att-h">Attendance</h2>
            {d.attendance.courses.length === 0 ? (
              <Empty>You are not enrolled in any course this term.</Empty>
            ) : (
              <>
                <p className="lead">
                  {d.attendance.overall_percent === null
                    ? 'No classes have been held yet.'
                    : d.attendance.short_courses === 0
                      ? `${d.attendance.overall_percent}% across all your courses, and none is below ${d.attendance.threshold}%.`
                      : `${d.attendance.overall_percent}% across all your courses, but ${plural(d.attendance.short_courses, 'course is', 'courses are')} below ${d.attendance.threshold}%.`}
                </p>
                <ul className="bars">
                  {d.attendance.courses.map((c) => (
                    <AttendanceRow key={c.course} c={c} floor={d.attendance.threshold} />
                  ))}
                </ul>
              </>
            )}
          </section>

          <section className="block" aria-labelledby="todo-h">
            <h2 id="todo-h">Needs your attention</h2>
            {todo.length === 0 ? (
              <Empty>Nothing right now. Your attendance, fees and assignments are all in order.</Empty>
            ) : (
              <ul className="attention">
                {todo.map((t, i) => (
                  <li key={i} className={t.tone}>
                    {t.text}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="block" aria-labelledby="today-h">
            <h2 id="today-h">Today</h2>
            {d.today.length === 0 ? (
              <Empty>{d.weekday === SUNDAY ? 'No classes on Sunday.' : 'No classes are scheduled for you today.'}</Empty>
            ) : (
              <ol className="timeline">
                {d.today.map((c) => (
                  <li key={`${c.course}-${c.start_time}`} className="timeline-row student">
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
                  </li>
                ))}
              </ol>
            )}
          </section>

          <div className="columns">
            <section className="block" aria-labelledby="fees-h">
              <h2 id="fees-h">Fees</h2>
              {d.fees.entries.length === 0 ? (
                <Empty>No fee records.</Empty>
              ) : (
                <ul className="plain-list">
                  {d.fees.entries.map((f) => (
                    <li key={f.term} className="fee-row">
                      <span>
                        <strong>{f.term}</strong>
                        <span className="muted small">
                          {' '}
                          {formatMoney(f.amount_paid)} of {formatMoney(f.amount_due)} paid
                          {f.status !== 'paid' && f.due_date ? `, due ${formatDate(f.due_date)}` : f.paid_on ? `, on ${formatDate(f.paid_on)}` : ''}
                        </span>
                      </span>
                      <span className={`badge ${f.status}`}>{f.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="block" aria-labelledby="exam-h">
              <h2 id="exam-h">Upcoming exams</h2>
              {upcoming.length === 0 ? (
                <Empty>No exams are scheduled.</Empty>
              ) : (
                <ul className="plain-list">
                  {upcoming.slice(0, 6).map((e, i) => (
                    <li key={i}>
                      <span>
                        <strong>{e.name}</strong> <span className="muted small">{e.exam_type}</span>
                      </span>
                      <span className="muted small">
                        {formatDay(e.date)}
                        {e.start_time ? `, ${e.start_time} to ${e.end_time ?? ''}` : ''}
                        {e.room ? `, room ${e.room}` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <div className="columns">
            <section className="block" aria-labelledby="work-h">
              <h2 id="work-h">Assignments</h2>
              {open.length === 0 ? (
                <Empty>Every assignment is submitted.</Empty>
              ) : (
                <ul className="plain-list">
                  {open.slice(0, 6).map((a, i) => (
                    <li key={i}>
                      <span>
                        <strong>{a.title ?? 'Assignment'}</strong> <span className="mono muted small">{a.course}</span>
                      </span>
                      <span className="small">
                        <span className={`badge ${a.status}`}>{a.status}</span>
                        <span className="muted"> due {formatDate(a.due_date)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="block" aria-labelledby="news-h">
              <h2 id="news-h">Announcements</h2>
              {d.announcements.length === 0 ? (
                <Empty>No announcements for you right now.</Empty>
              ) : (
                <ul className="plain-list news">
                  {d.announcements.slice(0, 5).map((a, i) => (
                    <li key={i}>
                      <span>
                        <strong>{a.title}</strong> <span className="muted small">{formatDate(a.posted_at)}</span>
                      </span>
                      {a.body && <span className="muted small clamp">{a.body}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <p className="small muted">
            Your marks and IA are on the <Link to="/results">Results</Link> page. Not sure what a number means? <Link to="/assistant">Ask the assistant.</Link>
          </p>
        </>
      )}
    </div>
  )
}
