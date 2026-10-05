import { Link } from 'react-router-dom'
import { api } from '../../api'
import { formatDate, formatDay, firstName, greeting, plural, sectionLabel } from '../format'
import { usePortal } from '../context'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { useLoad } from '../useLoad'

const WEEKEND_DAY = 6 // Sunday: the timetable runs Monday to Saturday

export function FacultyHome() {
  const { me } = usePortal()
  const { data, error } = useLoad(() => api.facultyDashboard(), 'faculty-dashboard', true)
  const name = firstName(me?.full_name ?? data?.faculty.full_name)

  return (
    <div className="page">
      <PageHeader
        title={name ? `${greeting()}, ${name}` : 'Home'}
        lede={data ? `${formatDay(data.date)}. You teach ${plural(data.courses, 'section')} to ${plural(data.students, 'student')} this term.` : undefined}
      />
      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <Loading what="your day" />}

      {data && (
        <>
          <section className="block" aria-labelledby="today-h">
            <h2 id="today-h">Today</h2>
            {data.today.length === 0 ? (
              <Empty>{data.weekday === WEEKEND_DAY ? 'No classes on Sunday.' : 'You have no classes scheduled today.'}</Empty>
            ) : (
              <ol className="timeline">
                {data.today.map((c) => (
                  <li key={`${c.offering_id}-${c.start_time}`} className="timeline-row">
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
                    {c.attendance_marked ? (
                      <Link className="btn" to={`/courses/${c.offering_id}/attendance/${data.date}`}>
                        Attendance recorded
                      </Link>
                    ) : (
                      <Link className="btn primary" to={`/courses/${c.offering_id}/attendance/${data.date}`}>
                        Take attendance
                      </Link>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>

          <div className="columns">
            <section className="block" aria-labelledby="risk-h">
              <h2 id="risk-h">Students who need attention</h2>
              {data.at_risk.count === 0 ? (
                <Empty>No one is below the attendance or marks floor in your courses.</Empty>
              ) : (
                <>
                  <ul className="plain-list">
                    {data.at_risk.students.map((s) => (
                      <li key={s.roll_no}>
                        <span>
                          <strong>{s.full_name}</strong> <span className="mono muted small">{s.roll_no}</span>
                        </span>
                        <span className="muted small">{s.reasons}</span>
                      </li>
                    ))}
                  </ul>
                  {data.at_risk.count > data.at_risk.students.length && (
                    <p className="small muted">
                      {data.at_risk.count - data.at_risk.students.length} more. <Link to="/assistant">Ask the assistant for the full list.</Link>
                    </p>
                  )}
                </>
              )}
            </section>

            {data.faculty.is_hod && (
              <section className="block" aria-labelledby="leave-h">
                <h2 id="leave-h">Leave requests waiting for you</h2>
                {data.pending_leave.count === 0 ? (
                  <Empty>Nothing is waiting for your decision.</Empty>
                ) : (
                  <>
                    <ul className="plain-list">
                      {data.pending_leave.requests.map((r) => (
                        <li key={r.leave_request_id}>
                          <span>
                            <strong>{r.full_name}</strong> <span className="mono muted small">{r.roll_no}</span>
                          </span>
                          <span className="muted small">
                            {formatDate(r.from_date)} to {formatDate(r.to_date)}
                            {r.reason ? `: ${r.reason}` : ''}
                          </span>
                        </li>
                      ))}
                    </ul>
                    <p className="small muted">
                      <Link to="/assistant">Approve or reject in the assistant.</Link>
                    </p>
                  </>
                )}
              </section>
            )}
          </div>

          <section className="block" aria-labelledby="news-h">
            <h2 id="news-h">Announcements</h2>
            {data.announcements.length === 0 ? (
              <Empty>No announcements for you right now.</Empty>
            ) : (
              <ul className="plain-list news">
                {data.announcements.map((a, i) => (
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
        </>
      )}
    </div>
  )
}
