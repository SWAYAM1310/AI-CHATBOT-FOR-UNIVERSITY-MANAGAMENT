import { Link } from 'react-router-dom'
import { api } from '../../api'
import type { DepartmentRow } from '../../types'
import { usePortal } from '../context'
import { firstName, formatDate, formatMoney, greeting, plural } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { useLoad } from '../useLoad'
import { deliverySummary, noticeAudience } from './notices'

const ATTENDANCE_FLOOR = 75

/** A bar out of 100 with an optional rule drawn on it, the same mark the student page uses. */
function Meter({ percent, floor, label }: { percent: number | null; floor?: number; label: string }) {
  if (percent === null) return <span className="muted small">No data</span>
  const short = floor !== undefined && percent < floor
  return (
    <span className="meter">
      <span className="bar-track" role="img" aria-label={`${label}: ${percent}%`}>
        <span className={short ? 'bar-fill short' : 'bar-fill'} style={{ width: `${Math.min(percent, 100)}%` }} />
        {floor !== undefined && <span className="bar-floor" style={{ left: `${floor}%` }} />}
      </span>
      <span className={short ? 'bar-pct short' : 'bar-pct'}>{percent}%</span>
    </span>
  )
}

function DepartmentTable({ rows }: { rows: DepartmentRow[] }) {
  return (
    <div className="table-wrap stack-table">
      <table className="data depts">
        <thead>
          <tr>
            <th>Department</th>
            <th className="num">Students</th>
            <th className="num">Faculty</th>
            <th>Average attendance</th>
            <th>Fees collected</th>
            <th className="num">Outstanding</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.dept}>
              <td>
                <strong>{d.name}</strong> <span className="mono muted small">{d.dept}</span>
                {d.hod && <span className="muted small block-line">HOD {d.hod}</span>}
              </td>
              <td className="num" data-label="Students">
                {d.students}
              </td>
              <td className="num" data-label="Faculty">
                {d.faculty}
              </td>
              {d.students === 0 ? (
                <td colSpan={3} className="muted small">
                  No students enrolled; teaches other departments' courses.
                </td>
              ) : (
                <>
                  <td data-label="Average attendance">
                    <span className="meter-cell">
                      <Meter percent={d.avg_attendance_percent} floor={ATTENDANCE_FLOOR} label={`${d.name} average attendance`} />
                      {d.below_attendance > 0 && <span className="small low-note block-line">{d.below_attendance} below {ATTENDANCE_FLOOR}%</span>}
                    </span>
                  </td>
                  <td data-label="Fees collected">
                    <span className="meter-cell">
                      <Meter percent={d.fee_collection_percent} label={`${d.name} fees collected`} />
                    </span>
                  </td>
                  <td className="num" data-label="Outstanding">
                    {d.fee_outstanding ? (
                      <Link to={`/fees?dept=${d.dept}`}>{formatMoney(d.fee_outstanding)}</Link>
                    ) : (
                      formatMoney(d.fee_outstanding)
                    )}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AdminHome() {
  const { me } = usePortal()
  const { data, error } = useLoad(() => api.adminDashboard(), 'admin-dashboard', true)
  const name = firstName(me?.full_name ?? data?.admin.full_name)
  const k = data?.kpis

  return (
    <div className="page">
      <PageHeader
        title={name ? `${greeting()}, ${name}` : 'Home'}
        lede={data ? `${data.admin.designation ?? 'Administrator'}. The ${data.term} term across ${plural(data.kpis.departments, 'department')}.` : undefined}
        actions={
          <>
            <Link className="btn" to="/fees">
              Record a payment
            </Link>
            <Link className="btn primary" to="/announcements">
              New announcement
            </Link>
          </>
        }
      />
      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <Loading what="the university overview" />}

      {data && k && (
        <>
          <section className="block" aria-labelledby="kpi-h">
            <h2 id="kpi-h" className="sr-only">
              At a glance
            </h2>
            <dl className="kpis">
              <div>
                <dt>Students</dt>
                <dd>{k.students}</dd>
                <span className="muted small">taught by {plural(k.faculty, 'faculty member')}</span>
              </div>
              <div>
                <dt>Average attendance</dt>
                <dd>{k.avg_attendance_percent === null ? 'n/a' : `${k.avg_attendance_percent}%`}</dd>
                <span className={k.below_attendance ? 'small low-note' : 'muted small'}>
                  {k.below_attendance ? `${plural(k.below_attendance, 'student')} below ${ATTENDANCE_FLOOR}%` : `No one below ${ATTENDANCE_FLOOR}%`}
                </span>
              </div>
              <div>
                <dt>Fees collected</dt>
                <dd>{k.fee_collection_percent === null ? 'n/a' : `${k.fee_collection_percent}%`}</dd>
                <span className="muted small">
                  {formatMoney(k.fees_collected)} of {formatMoney(k.fees_billed)}
                </span>
              </div>
              <div>
                <dt>Outstanding</dt>
                <dd>{formatMoney(k.fees_outstanding)}</dd>
                <Link className="small" to="/fees?status=overdue">
                  See overdue fees
                </Link>
              </div>
            </dl>
            {k.fees_billed > 0 && (
              <div className="ledger" role="img" aria-label={`Fees: ${formatMoney(k.fees_collected)} collected, ${formatMoney(k.fees_outstanding)} outstanding`}>
                <span className="ledger-paid" style={{ flexGrow: k.fees_collected }} />
                <span className="ledger-due" style={{ flexGrow: k.fees_outstanding }} />
              </div>
            )}
          </section>

          <section className="block" aria-labelledby="dept-h">
            <h2 id="dept-h">Departments</h2>
            <DepartmentTable rows={data.departments} />
            <p className="small muted">The line on each attendance bar is the {ATTENDANCE_FLOOR}% rule.</p>
          </section>

          <section className="block" aria-labelledby="news-h">
            <h2 id="news-h">Recent announcements</h2>
            {data.recent_announcements.length === 0 ? (
              <Empty>Nothing has been announced yet.</Empty>
            ) : (
              <ul className="plain-list news">
                {data.recent_announcements.map((a) => (
                  <li key={a.announcement_id}>
                    <span>
                      <strong>{a.title}</strong> <span className="muted small">{formatDate(a.posted_at)}</span>
                    </span>
                    <span className="muted small">
                      {noticeAudience(a)}. {deliverySummary(a.delivery)}.
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="small">
              <Link to="/announcements">All announcements and delivery details</Link>
            </p>
          </section>
        </>
      )}
    </div>
  )
}
