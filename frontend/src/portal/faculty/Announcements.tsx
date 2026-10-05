import { AnnouncementFeed } from '../AnnouncementFeed'
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
      {d && <AnnouncementFeed items={d.announcements} />}
    </div>
  )
}
