import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import type { AtRiskStudent } from '../../types'
import { plural } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { useLoad } from '../useLoad'

// the lines a student is flagged under (ATTENDANCE_RISK_PCT / MARKS_RISK_PCT in faculty_tools.py)
const ATTENDANCE_FLOOR = 75
const MARKS_FLOOR = 40

type Reason = 'attendance' | 'marks' | 'missing'

const REASONS: Reason[] = ['attendance', 'marks', 'missing']
const LABEL: Record<Reason, string> = { attendance: 'Low attendance', marks: 'Low marks', missing: 'Work missing' }
const FLAGGED: Record<Reason, (s: AtRiskStudent) => boolean> = {
  attendance: (s) => s.attendance_percent !== null && s.attendance_percent < ATTENDANCE_FLOOR,
  marks: (s) => s.marks_percent !== null && s.marks_percent < MARKS_FLOOR,
  missing: (s) => s.missing_submissions > 0,
}

const pct = (n: number | null) => (n === null ? '-' : `${n}%`)

export function AtRisk() {
  const [course, setCourse] = useState('')
  const [reason, setReason] = useState<Reason | ''>('')
  const courses = useLoad(() => api.facultyCourses(), 'faculty-courses')
  const { data: students, error } = useLoad(() => api.atRisk(course || undefined), `at-risk:${course}`, true)

  // one option per subject: a subject taught to two sections is one course here
  const subjects = [...new Map((courses.data ?? []).map((c) => [c.course, c.name])).entries()].sort((a, b) => a[1].localeCompare(b[1]))
  const count = (r: Reason) => (students ?? []).filter(FLAGGED[r]).length
  const shown = reason ? (students ?? []).filter(FLAGGED[reason]) : students ?? []

  return (
    <div className="page">
      <PageHeader
        title="Students at risk"
        lede={`Students in your courses below ${ATTENDANCE_FLOOR}% attendance, under ${MARKS_FLOOR}% on graded work, or with internal assessment work missing. Worst first.`}
      />

      <div className="toolbar">
        <label className="field-inline">
          <span>Course</span>
          <select value={course} onChange={(e) => setCourse(e.target.value)}>
            <option value="">All my courses</option>
            {subjects.map(([code, name]) => (
              <option key={code} value={code}>
                {name} ({code})
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <Notice tone="error">{error}</Notice>}
      {!students && !error && <Loading what="your students" />}

      {students && students.length === 0 && (
        <Empty>No one {course ? 'in this course' : 'in your courses'} is below the attendance or marks line, and no work is missing.</Empty>
      )}

      {students && students.length > 0 && (
        <>
          <p className="lead">
            {plural(students.length, 'student needs', 'students need')} a look:{' '}
            {REASONS.filter((r) => count(r) > 0)
              .map((r) => `${count(r)} with ${LABEL[r].toLowerCase()}`)
              .join(', ')}
            . A student can be on more than one count.
          </p>

          <div className="chips" role="group" aria-label="Filter by reason">
            <button type="button" className={reason === '' ? 'chip active' : 'chip'} aria-pressed={reason === ''} onClick={() => setReason('')}>
              All <span className="chip-count">{students.length}</span>
            </button>
            {REASONS.filter((r) => count(r) > 0).map((r) => (
              <button
                key={r}
                type="button"
                className={reason === r ? 'chip active' : 'chip'}
                aria-pressed={reason === r}
                onClick={() => setReason(reason === r ? '' : r)}
              >
                {LABEL[r]} <span className="chip-count">{count(r)}</span>
              </button>
            ))}
          </div>

          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">Student</th>
                  <th scope="col" className="num">Attendance</th>
                  <th scope="col" className="num">Marks</th>
                  <th scope="col" className="num">Work missing</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((s) => (
                  <tr key={s.roll_no}>
                    <td>
                      <strong>{s.full_name}</strong> <span className="mono muted small">{s.roll_no}</span>
                    </td>
                    <td className={`num${FLAGGED.attendance(s) ? ' low' : ''}`}>{pct(s.attendance_percent)}</td>
                    <td className={`num${FLAGGED.marks(s) ? ' low' : ''}`}>{pct(s.marks_percent)}</td>
                    <td className={`num${FLAGGED.missing(s) ? ' low' : ''}`}>{s.missing_submissions || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted">
            Figures are across {course ? 'this course' : 'every course you teach the student'}; marks count graded work only.{' '}
            <Link to="/assistant">Ask the assistant</Link> about any student for the detail behind a figure.
          </p>
        </>
      )}
    </div>
  )
}
