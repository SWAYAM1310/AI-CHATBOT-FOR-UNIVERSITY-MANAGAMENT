import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import type { RosterStudent } from '../../types'
import { FilterChips, FilterSummary } from '../Filters'
import { matchesQuery, useClearParams, useParamFilter } from '../filtering'
import { plural } from '../format'
import { Empty } from '../ui'
import type { CourseContext } from './CourseLayout'

const FLOOR = 75 // the attendance rule, in percent

const FLAGS = ['short', 'missing', 'clear'] as const
type Flag = (typeof FLAGS)[number]
const isShort = (s: RosterStudent) => s.attendance_percent !== null && s.attendance_percent < FLOOR
const FLAGGED: Record<Flag, (s: RosterStudent) => boolean> = {
  short: isShort,
  missing: (s) => s.missing_submissions > 0,
  clear: (s) => !isShort(s) && s.missing_submissions === 0,
}
const FLAG_LABEL: Record<Flag, string> = { short: `Below ${FLOOR}%`, missing: 'Work missing', clear: 'All clear' }

export function Roster() {
  const { students } = useOutletContext<CourseContext>()
  const [query, setQuery] = useState('')
  const [flag, setFlag] = useParamFilter<Flag>('show', FLAGS)
  const [dept, setDept] = useParamFilter<string>('dept')
  const clearParams = useClearParams(['show', 'dept'])
  // a common first-year course can seat several departments in one section
  const depts = [...new Set(students.map((s) => s.dept_code))].sort()
  const searched = students.filter((s) => matchesQuery(query, s.roll_no, s.full_name) && (!dept || s.dept_code === dept))
  const shown = flag ? searched.filter(FLAGGED[flag]) : searched

  return (
    <section>
      <div className="toolbar">
        <label className="field-inline">
          <span className="sr-only">Find a student</span>
          <input type="search" placeholder="Find by name or roll number" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        {depts.length > 1 && (
          <label className="field-inline">
            <span className="sr-only">Department</span>
            <select value={dept} onChange={(e) => setDept(e.target.value)}>
              <option value="">All departments</option>
              {depts.map((d) => (
                <option key={d} value={d}>
                  {d} ({students.filter((s) => s.dept_code === d).length})
                </option>
              ))}
            </select>
          </label>
        )}
        <span className="muted small">{plural(students.length, 'student')} enrolled</span>
      </div>
      {students.length > 0 && (
        <FilterChips
          label="Filter by what needs a look"
          options={FLAGS.map((f) => ({ value: f, label: FLAG_LABEL[f], count: searched.filter(FLAGGED[f]).length, tone: f === 'clear' ? undefined : 'overdue' }))}
          value={flag}
          onChange={setFlag}
          total={searched.length}
        />
      )}
      <FilterSummary
        shown={shown.length}
        total={students.length}
        noun={['student', 'students']}
        active={Boolean(flag || dept || query.trim())}
        onClear={() => {
          clearParams()
          setQuery('')
        }}
      />

      {shown.length === 0 ? (
        <Empty>{students.length === 0 ? 'No one is enrolled in this section.' : 'No student matches these filters.'}</Empty>
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
