import { Link, NavLink, Outlet, useParams } from 'react-router-dom'
import { api } from '../../api'
import type { FacultyCourse, RosterStudent } from '../../types'
import { sectionLabel } from '../format'
import { PageHeader } from '../PageHeader'
import { Loading, Notice } from '../ui'
import { useLoad } from '../useLoad'

/** What the tabs under a course share: who is enrolled, and a way to refresh it after a save. */
export interface CourseContext {
  offering: FacultyCourse
  students: RosterStudent[]
  reload: () => void
}

export function CourseLayout() {
  const { offeringId } = useParams()
  const id = Number(offeringId)
  const valid = Number.isInteger(id) && id > 0
  const { data, error, status, reload } = useLoad(() => api.roster(id), valid ? `roster-${id}` : null)

  if (!valid || status === 404) {
    return (
      <div className="page">
        <PageHeader title="Course not found" />
        <Notice tone="info">This is not one of the sections you teach.</Notice>
        <p>
          <Link to="/courses">Back to your courses</Link>
        </p>
      </div>
    )
  }

  const base = `/courses/${id}`
  const context: CourseContext | undefined = data && { offering: data.offering, students: data.students, reload }

  return (
    <div className="page">
      <PageHeader
        title={data?.offering.name ?? 'Course'}
        lede={data ? `${data.offering.course}, ${sectionLabel(data.offering)}` : undefined}
        actions={
          <Link className="btn" to="/courses">
            All courses
          </Link>
        }
      />
      <nav className="tabs" aria-label="Course sections">
        <NavLink to={base} end>
          Roster
        </NavLink>
        <NavLink to={`${base}/marks`}>Marks</NavLink>
      </nav>
      {error && <Notice tone="error">{error}</Notice>}
      {!context && !error && <Loading what="the course" />}
      {context && <Outlet context={context} />}
    </div>
  )
}
