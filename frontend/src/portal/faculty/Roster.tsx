import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { plural } from '../format'
import { Empty } from '../ui'
import type { CourseContext } from './CourseLayout'

const FLOOR = 75 // the attendance rule, in percent

export function Roster() {
  const { students } = useOutletContext<CourseContext>()
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const shown = q ? students.filter((s) => s.roll_no.toLowerCase().includes(q) || s.full_name.toLowerCase().includes(q)) : students

  return (
    <section>
      <div className="toolbar">
        <label className="field-inline">
          <span className="sr-only">Find a student</span>
          <input type="search" placeholder="Find by name or roll number" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <span className="muted small">{plural(students.length, 'student')} enrolled</span>
      </div>

      {shown.length === 0 ? (
        <Empty>{students.length === 0 ? 'No one is enrolled in this section.' : 'No student matches that search.'}</Empty>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Roll no.</th>
                <th>Name</th>
                <th>Department</th>
                <th className="num">Attendance</th>
                <th className="num">Missing work</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => {
                const low = s.attendance_percent !== null && s.attendance_percent < FLOOR
                return (
                  <tr key={s.roll_no}>
                    <td className="mono">{s.roll_no}</td>
                    <td>{s.full_name}</td>
                    <td>{s.dept_code}</td>
                    <td className={`num${low ? ' low' : ''}`}>
                      {s.attendance_percent === null ? <span className="muted">no classes yet</span> : `${s.attendance_percent}%`}
                      {s.total > 0 && <span className="muted small"> ({s.attended}/{s.total})</span>}
                    </td>
                    <td className={`num${s.missing_submissions ? ' low' : ''}`}>{s.missing_submissions || <span className="muted">none</span>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
