import { Link } from 'react-router-dom'
import { api } from '../../api'
import type { FacultyCourse } from '../../types'
import { plural, sectionLabel } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { useLoad } from '../useLoad'

/** One course can be taught to several departments' divisions: group the sections under it. */
function groupByCourse(courses: FacultyCourse[]): [string, FacultyCourse[]][] {
  const groups = new Map<string, FacultyCourse[]>()
  for (const c of courses) groups.set(c.course, [...(groups.get(c.course) ?? []), c])
  return [...groups.entries()]
}

export function Courses() {
  const { data, error } = useLoad(() => api.facultyCourses(), 'faculty-courses')

  return (
    <div className="page">
      <PageHeader title="Courses" lede="The sections you teach this term. Open one for its roster or to enter marks." />
      <p className="muted">
        Attendance is taken from the <Link to="/calendar">Calendar</Link>: open the day a class met.
      </p>
      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <Loading what="your courses" />}
      {data && data.length === 0 && <Empty>You are not teaching any course this term.</Empty>}

      {data &&
        groupByCourse(data).map(([code, sections]) => (
          <section key={code} className="block" aria-label={sections[0].name}>
            <h2>
              {sections[0].name} <span className="mono muted small">{code}</span>
            </h2>
            <ul className="section-list">
              {sections.map((s) => (
                <li key={s.offering_id} className="section-row">
                  <span className="section-what">
                    <strong>{sectionLabel(s)}</strong>
                    <span className="muted small">
                      {s.session_type ?? 'Class'}, {plural(s.enrolled ?? 0, 'student')}
                    </span>
                  </span>
                  <span className="section-actions">
                    <Link className="btn" to={`/courses/${s.offering_id}`}>
                      Roster
                    </Link>
                    <Link className="btn" to={`/courses/${s.offering_id}/marks`}>
                      Marks
                    </Link>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
    </div>
  )
}
