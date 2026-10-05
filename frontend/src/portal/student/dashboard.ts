// Every student page reads the one dashboard payload (backend/app/api/student.py), so
// Home, Attendance, Exams and the rest always agree with each other and with the assistant.
import { api } from '../../api'
import type { StudentDashboard } from '../../types'
import { useLoad } from '../useLoad'

const REFRESH_MS = 30_000 // a faculty member's attendance entry shows up here within half a minute

export function useStudentDashboard() {
  return useLoad(() => api.studentDashboard(), 'student-dashboard', true, REFRESH_MS)
}

/** "Discrete Mathematics" for "24MA202T", from the courses the student is enrolled in. */
export function courseNames(d: StudentDashboard): (code: string) => string | undefined {
  const names = new Map(d.attendance.courses.map((c) => [c.course, c.name]))
  return (code) => names.get(code)
}
