import { Navigate, useRoutes, type RouteObject } from 'react-router-dom'
import type { Role } from '../types'
import { AdminHome } from './admin/AdminHome'
import { CalendarPage, CalendarRegisterDay } from './calendar/RegisterDay'
import { Announcements } from './admin/Announcements'
import { Fees } from './admin/Fees'
import { FacultyAnnouncements } from './faculty/Announcements'
import { AtRisk } from './faculty/AtRisk'
import { CourseLayout } from './faculty/CourseLayout'
import { Courses } from './faculty/Courses'
import { FacultyHome } from './faculty/FacultyHome'
import { LeaveRequests } from './faculty/LeaveRequests'
import { Marks } from './faculty/Marks'
import { NoticeApprovals } from './faculty/NoticeApprovals'
import { Roster } from './faculty/Roster'
import { Assistant } from './pages'
import { PortalLayout } from './PortalLayout'
import { Profile } from './Profile'
import { StudentActivities } from './student/Activities'
import { StudentAnnouncements } from './student/Announcements'
import { StudentAttendance } from './student/Attendance'
import { StudentExams } from './student/Exams'
import { StudentFees } from './student/Fees'
import { Results } from './student/Results'
import { StudentHome } from './student/StudentHome'

// Only the pages a role can use exist for it; anything else falls back to Home,
// so a bookmarked /fees opened by a student lands somewhere sensible.
const BY_ROLE: Record<Role, RouteObject[]> = {
  student: [
    { index: true, element: <StudentHome /> },
    { path: 'attendance', element: <StudentAttendance /> },
    { path: 'announcements', element: <StudentAnnouncements /> },
    { path: 'exams', element: <StudentExams /> },
    { path: 'results', element: <Results /> },
    { path: 'activities', element: <StudentActivities /> },
    { path: 'fees', element: <StudentFees /> },
  ],
  faculty: [
    { index: true, element: <FacultyHome /> },
    { path: 'courses', element: <Courses /> },
    { path: 'calendar', element: <CalendarPage /> },
    { path: 'calendar/:date', element: <CalendarRegisterDay /> },
    { path: 'at-risk', element: <AtRisk /> },
    { path: 'leave', element: <LeaveRequests /> },
    { path: 'approvals', element: <NoticeApprovals /> },
    { path: 'announcements', element: <FacultyAnnouncements /> },
    {
      path: 'courses/:offeringId',
      element: <CourseLayout />,
      children: [
        { index: true, element: <Roster /> },
        { path: 'marks', element: <Marks /> },
      ],
    },
  ],
  admin: [
    { index: true, element: <AdminHome /> },
    { path: 'announcements', element: <Announcements /> },
    { path: 'fees', element: <Fees /> },
  ],
}

const SHARED: RouteObject[] = [
  { path: 'assistant', element: <Assistant /> },
  { path: 'profile', element: <Profile /> },
]

export function PortalRoutes({ role }: { role: Role }) {
  return useRoutes([
    {
      element: <PortalLayout />,
      children: [...BY_ROLE[role], ...SHARED, { path: '*', element: <Navigate to="/" replace /> }],
    },
  ])
}
