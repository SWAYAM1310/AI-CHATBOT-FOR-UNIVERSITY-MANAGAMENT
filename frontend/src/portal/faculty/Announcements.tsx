import { AnnouncementFeed } from '../AnnouncementFeed'
import { ApprovalTrack } from '../ApprovalTrack'
import { formatDate } from '../format'
import { PageHeader } from '../PageHeader'
import { Loading, Notice } from '../ui'
import { useFacultyDashboard } from './dashboard'

export function FacultyAnnouncements() {
  const { data: d, error } = useFacultyDashboard()
  return (
    <div className="page">
      <PageHeader title="Announcements" lede="Notices from the university, your department and the courses you teach, newest first." />
      {error && <Notice tone="error">{error}</Notice>}
      {!d && !error && <Loading what="announcements" />}
      {d && d.my_submissions.length > 0 && (
        <section className="block" aria-labelledby="mine-h">
          <h2 id="mine-h">Sent by you</h2>
          <p className="muted small">Course notices reach your students once your head of department approves them. Post one from the Assistant.</p>
          <ul className="plain-list">
            {d.my_submissions.map((n) => (
              <li key={n.announcement_id} className="notice-row">
                <span className="ann-meta">
                  <span className="muted small">
                    {n.course ?? n.dept ?? 'University'}, sent {formatDate(n.submitted_at)}
                  </span>
                </span>
                <strong>{n.title}</strong>
                <ApprovalTrack approvals={n.approvals} state={n.status} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {d && (
        <section className="block" aria-labelledby={d.my_submissions.length > 0 ? 'feed-h' : undefined}>
          {d.my_submissions.length > 0 && <h2 id="feed-h">For you</h2>}
          <AnnouncementFeed items={d.announcements} />
        </section>
      )}
    </div>
  )
}
