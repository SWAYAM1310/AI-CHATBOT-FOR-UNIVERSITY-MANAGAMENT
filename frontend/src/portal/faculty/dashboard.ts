// Home and Announcements both read the faculty dashboard payload (backend/app/api/faculty.py).
import { api } from '../../api'
import { useLoad } from '../useLoad'

export function useFacultyDashboard() {
  return useLoad(() => api.facultyDashboard(), 'faculty-dashboard', true)
}
