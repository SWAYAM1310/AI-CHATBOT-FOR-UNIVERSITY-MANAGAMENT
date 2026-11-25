import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../api'
import type { Role } from '../types'
import { Avatar } from './Avatar'
import { usePortal } from './context'
import { APPROVALS_CHANGED } from './approvals'
import { ActivitiesIcon, AlertIcon, AttendanceIcon, BookIcon, CalendarIcon, ExamIcon, ChatIcon, HomeIcon, LeaveIcon, MegaphoneIcon, MenuIcon, ResultsIcon, SignOutIcon, StampIcon, UserIcon, WalletIcon } from './icons'
import { useLoad } from './useLoad'

// the badge re-reads now and then, so a notice the admin just sent shows up without a reload
const BADGE_POLL_MS = 60_000

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  end?: boolean
  /** Only a head of department sees it. */
  hodOnly?: boolean
  /** Shows how many things are waiting there. */
  badge?: 'approvals'
}

// What each role works with, most-used first. The assistant sits second to last:
// it is one tool among several now, not the whole product.
const NAV: Record<Role, NavItem[]> = {
  student: [
    { to: '/', label: 'Home', icon: <HomeIcon />, end: true },
    { to: '/attendance', label: 'Attendance', icon: <AttendanceIcon /> },
    { to: '/announcements', label: 'Announcements', icon: <MegaphoneIcon /> },
    { to: '/exams', label: 'Exams', icon: <ExamIcon /> },
    { to: '/results', label: 'Results', icon: <ResultsIcon /> },
    { to: '/activities', label: 'Curricular activities', icon: <ActivitiesIcon /> },
    { to: '/fees', label: 'Fees', icon: <WalletIcon /> },
    { to: '/assistant', label: 'Assistant', icon: <ChatIcon /> },
    { to: '/profile', label: 'Profile', icon: <UserIcon /> },
  ],
  faculty: [
    { to: '/', label: 'Home', icon: <HomeIcon />, end: true },
    { to: '/courses', label: 'Courses', icon: <BookIcon /> },
    { to: '/calendar', label: 'Calendar', icon: <CalendarIcon /> },
    { to: '/at-risk', label: 'Students at risk', icon: <AlertIcon /> },
    { to: '/leave', label: 'Leave requests', icon: <LeaveIcon />, hodOnly: true },
    { to: '/approvals', label: 'Notice approvals', icon: <StampIcon />, hodOnly: true, badge: 'approvals' },
    { to: '/announcements', label: 'Announcements', icon: <MegaphoneIcon /> },
    { to: '/assistant', label: 'Assistant', icon: <ChatIcon /> },
    { to: '/profile', label: 'Profile', icon: <UserIcon /> },
  ],
  admin: [
    { to: '/', label: 'Home', icon: <HomeIcon />, end: true },
    { to: '/announcements', label: 'Announcements', icon: <MegaphoneIcon /> },
    { to: '/fees', label: 'Fees', icon: <WalletIcon /> },
    { to: '/assistant', label: 'Assistant', icon: <ChatIcon /> },
    { to: '/profile', label: 'Profile', icon: <UserIcon /> },
  ],
}

function roleLabel(role: Role, isHod: boolean | undefined): string {
  if (role === 'faculty') return isHod ? 'Head of department' : 'Faculty'
  return role === 'admin' ? 'Administrator' : 'Student'
}

/** How many notices wait for this head of department; null for everyone else. */
function useApprovalsWaiting(isHod: boolean): number | null {
  const { data, reload } = useLoad(() => api.announcementApprovals(), isHod ? 'approvals-badge' : null, true, BADGE_POLL_MS)
  useEffect(() => {
    window.addEventListener(APPROVALS_CHANGED, reload)
    return () => window.removeEventListener(APPROVALS_CHANGED, reload)
  }, [reload])
  return isHod && data ? data.length : null
}

export function PortalLayout() {
  const { session, me, photoVersion, signOut } = usePortal()
  const { pathname } = useLocation()
  const approvalsWaiting = useApprovalsWaiting(session.role === 'faculty' && Boolean(me?.is_hod))
  const badges: Record<NonNullable<NavItem['badge']>, number | null> = { approvals: approvalsWaiting }
  // the phone drawer is open for the page it was opened on; going somewhere closes it
  const [openOn, setOpenOn] = useState<string | null>(null)
  const open = openOn === pathname
  const setOpen = (on: boolean) => setOpenOn(on ? pathname : null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpenOn(null)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div className="portal">
      <header className="portal-topbar">
        <button type="button" className="icon-btn" onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open}>
          <MenuIcon />
        </button>
        <span className="wordmark">UniAssist</span>
      </header>

      {open && <div className="portal-scrim" onClick={() => setOpen(false)} />}

      <nav className={`portal-nav${open ? ' open' : ''}`} aria-label="Main">
        <div className="portal-brand">
          <img src="/Pandit_Deendayal_Energy_University_logo.png" alt="" />
          <span className="wordmark">UniAssist</span>
        </div>

        <ul className="portal-links">
          {NAV[session.role].filter((item) => !item.hodOnly || me?.is_hod).map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end={item.end} className={({ isActive }) => `portal-link${isActive ? ' active' : ''}`}>
                {item.icon}
                <span>{item.label}</span>
                {item.badge && Boolean(badges[item.badge]) && (
                  <span className="nav-count" aria-label={`${badges[item.badge]} waiting`}>
                    {badges[item.badge]}
                  </span>
                )}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="portal-user">
          <NavLink to="/profile" className="portal-user-card" aria-label="Your profile">
            <Avatar userId={me?.user_id} name={me?.full_name} hasPhoto={me?.has_photo} version={photoVersion} />
            <span className="portal-user-text">
              <span className="portal-user-name">{me?.full_name ?? 'Signing in…'}</span>
              <span className="portal-user-role">{roleLabel(session.role, me?.is_hod)}</span>
            </span>
          </NavLink>
          <button type="button" className="portal-signout" onClick={signOut}>
            <SignOutIcon />
            Sign out
          </button>
        </div>
      </nav>

      <main className="portal-main">
        <Outlet />
      </main>
    </div>
  )
}
