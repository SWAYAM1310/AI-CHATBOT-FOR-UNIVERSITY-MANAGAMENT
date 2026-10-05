import type { ReactNode } from 'react'
import type { StudentDashboard } from '../../types'
import { PageHeader } from '../PageHeader'
import { Loading, Notice } from '../ui'
import { useStudentDashboard } from './dashboard'

/** A student page: its header, then `children` once the dashboard has loaded. */
export function StudentPage({
  title,
  lede,
  children,
}: {
  title: string
  lede?: (d: StudentDashboard) => ReactNode
  children: (d: StudentDashboard) => ReactNode
}) {
  const { data: d, error } = useStudentDashboard()
  return (
    <div className="page">
      <PageHeader title={title} lede={d && lede ? lede(d) : undefined} />
      {error && <Notice tone="error">{error}</Notice>}
      {!d && !error && <Loading what="your records" />}
      {d && children(d)}
    </div>
  )
}
