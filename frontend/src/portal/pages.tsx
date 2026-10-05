// Placeholder pages for the routes the portal shell defines. Each one is
// replaced by its real page in the next step; until then it says what is
// coming and offers the one thing that already works, the assistant.
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Chat } from '../Chat'
import { usePortal } from './context'
import { PageHeader } from './PageHeader'

function Stub({ title, lede, children }: { title: string; lede: string; children?: ReactNode }) {
  return (
    <div className="page">
      <PageHeader title={title} lede={lede} />
      <section className="stub">
        {children}
        <p>
          <Link to="/assistant">Ask the assistant</Link> in the meantime.
        </p>
      </section>
    </div>
  )
}

// "Dr. Milan Vyas" is greeted as "Dr. Milan", not "Dr."
function firstName(full: string | undefined): string {
  const [first = '', second = ''] = (full ?? '').trim().split(/\s+/)
  return first.endsWith('.') && second ? `${first} ${second}` : first
}

export function Home() {
  const { me } = usePortal()
  const name = firstName(me?.full_name)
  return (
    <Stub
      title={name ? `Hello, ${name}` : 'Home'}
      lede="Your dashboard is being built. It will show your records and what needs attention today."
    />
  )
}

export function Courses() {
  return <Stub title="Courses" lede="The sections you teach, with their rosters, attendance and marks." />
}

export function Course() {
  return <Stub title="Course" lede="Take attendance and enter marks for this section." />
}

export function Announcements() {
  return <Stub title="Announcements" lede="Publish a notice and email it to students and faculty." />
}

export function Fees() {
  return <Stub title="Fees" lede="See who has paid and record payments." />
}

export function Profile() {
  return <Stub title="Profile" lede="Your details, contact information, password and photo." />
}

export function Assistant() {
  const { session } = usePortal()
  return <Chat session={session} />
}
