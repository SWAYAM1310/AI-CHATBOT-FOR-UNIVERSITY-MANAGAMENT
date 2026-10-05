import { Navigate, useRoutes, type RouteObject } from 'react-router-dom'
import type { Role } from '../types'
import { Announcements, Assistant, Course, Courses, Fees, Home, Profile } from './pages'
import { PortalLayout } from './PortalLayout'

// Only the pages a role can use exist for it; anything else falls back to Home,
// so a bookmarked /fees opened by a student lands somewhere sensible.
const BY_ROLE: Record<Role, RouteObject[]> = {
  student: [{ index: true, element: <Home /> }],
  faculty: [
    { index: true, element: <Home /> },
    { path: 'courses', element: <Courses /> },
    { path: 'courses/:offeringId/*', element: <Course /> },
  ],
  admin: [
    { index: true, element: <Home /> },
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
