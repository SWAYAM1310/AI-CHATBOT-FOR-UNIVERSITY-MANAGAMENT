import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import type { Role } from '../types'
import { Avatar } from './Avatar'
import { usePortal } from './context'
import { BookIcon, ChatIcon, HomeIcon, MegaphoneIcon, MenuIcon, SignOutIcon, UserIcon, WalletIcon } from './icons'

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  end?: boolean
}

// What each role works with, most-used first. The assistant sits second to last:
// it is one tool among several now, not the whole product.
const NAV: Record<Role, NavItem[]> = {
  student: [
    { to: '/', label: 'Home', icon: <HomeIcon />, end: true },
    { to: '/assistant', label: 'Assistant', icon: <ChatIcon /> },
    { to: '/profile', label: 'Profile', icon: <UserIcon /> },
  ],
  faculty: [
    { to: '/', label: 'Home', icon: <HomeIcon />, end: true },
    { to: '/courses', label: 'Courses', icon: <BookIcon /> },
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

export function PortalLayout() {
  const { session, me, signOut } = usePortal()
  const { pathname } = useLocation()
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
          {NAV[session.role].map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end={item.end} className={({ isActive }) => `portal-link${isActive ? ' active' : ''}`}>
                {item.icon}
                <span>{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="portal-user">
          <NavLink to="/profile" className="portal-user-card" aria-label="Your profile">
            <Avatar userId={me?.user_id} name={me?.full_name} hasPhoto={me?.has_photo} />
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
