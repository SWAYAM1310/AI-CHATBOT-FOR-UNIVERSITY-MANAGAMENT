import { AnnouncementFeed } from '../AnnouncementFeed'
import { StudentPage } from './StudentPage'

export function StudentAnnouncements() {
  return (
    <StudentPage title="Announcements" lede={() => 'Notices from the university, your department and your courses, newest first.'}>
      {(d) => <AnnouncementFeed items={d.announcements} />}
    </StudentPage>
  )
}
