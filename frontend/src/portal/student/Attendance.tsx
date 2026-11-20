import type { CourseAttendance } from '../../types'
import { FilterChips, FilterSummary } from '../Filters'
import { useClearParams, useParamFilter } from '../filtering'
import { plural } from '../format'
import { Empty } from '../ui'
import { StudentPage } from './StudentPage'

function AttendanceRow({ c, floor }: { c: CourseAttendance; floor: number }) {
  const note = c.total === 0 ? 'No classes held yet.' : c.below_threshold
    ? `Attend the next ${plural(c.recover ?? 0, 'class', 'classes')} in a row to reach ${floor}%.`
    : c.can_skip === 0
      ? `Right on the line: missing one class drops you below ${floor}%.`
      : `You can miss ${plural(c.can_skip ?? 0, 'more class', 'more classes')} and stay at ${floor}%.`
  return (
    <li className="bar-row">
      <span className="bar-name">
        <strong>{c.name}</strong>
        <span className="mono muted small">{c.course}</span>
      </span>
      <span className="bar-track" role="img" aria-label={`${c.percent}% attended; the minimum is ${floor}%`}>
        <span className={`bar-fill${c.below_threshold ? ' short' : ''}`} style={{ width: `${Math.min(c.percent, 100)}%` }} />
        <span className="bar-floor" style={{ left: `${floor}%` }} />
      </span>
      <span className={`bar-pct${c.below_threshold ? ' short' : ''}`}>{c.total === 0 ? '-' : `${c.percent}%`}</span>
      <span className="bar-note muted small">
        {c.attended} of {c.total} classes. {note}
      </span>
    </li>
  )
}

// where a course stands against the minimum
const STANDINGS = ['short', 'edge', 'safe', 'none'] as const
type Standing = (typeof STANDINGS)[number]
const STANDING_LABEL: Record<Standing, string> = { short: 'Below the minimum', edge: 'On the line', safe: 'Comfortable', none: 'No classes yet' }
const EDGE = 1 // at most this many classes to spare counts as on the line

function standing(c: CourseAttendance): Standing {
  if (c.total === 0) return 'none'
  if (c.below_threshold) return 'short'
  return (c.can_skip ?? 0) <= EDGE ? 'edge' : 'safe'
}

// course codes end in T for theory and P for practical (lab); anything else is project work
const KINDS = ['theory', 'lab', 'other'] as const
type Kind = (typeof KINDS)[number]
const KIND_LABEL: Record<Kind, string> = { theory: 'Theory', lab: 'Labs', other: 'Project work' }
const kindOf = (code: string): Kind => (code.endsWith('T') ? 'theory' : code.endsWith('P') ? 'lab' : 'other')

/** One bar per course, filtered by kind of class and by where the student stands. */
function CourseBars({ courses, floor }: { courses: CourseAttendance[]; floor: number }) {
  const [stand, setStand] = useParamFilter<Standing>('standing', STANDINGS)
  const [kind, setKind] = useParamFilter<Kind>('kind', KINDS)
  const clearParams = useClearParams(['standing', 'kind'])
  const ofKind = kind ? courses.filter((c) => kindOf(c.course) === kind) : courses
  const shown = stand ? ofKind.filter((c) => standing(c) === stand) : ofKind
  const kinds = KINDS.filter((k) => courses.some((c) => kindOf(c.course) === k))
  return (
    <>
      <div className="filter-row">
        {kinds.length > 1 && (
          <FilterChips
            label="Filter by kind of class"
            options={kinds.map((k) => ({ value: k, label: KIND_LABEL[k], count: courses.filter((c) => kindOf(c.course) === k).length }))}
            value={kind}
            onChange={setKind}
            total={courses.length}
          />
        )}
        <FilterChips
          label="Filter by where you stand"
          options={STANDINGS.map((st) => ({
            value: st,
            label: st === 'short' ? `Below ${floor}%` : STANDING_LABEL[st],
            count: ofKind.filter((c) => standing(c) === st).length,
            tone: st === 'short' ? 'overdue' : undefined,
          }))}
          value={stand}
          onChange={setStand}
          total={ofKind.length}
        />
      </div>
      <FilterSummary
        shown={shown.length}
        total={courses.length}
        noun={['course', 'courses']}
        active={Boolean(stand || kind)}
        onClear={clearParams}
      />
      {shown.length === 0 ? (
        <Empty>No course matches these filters.</Empty>
      ) : (
        <ul className="bars">
          {shown.map((c) => (
            <AttendanceRow key={c.course} c={c} floor={floor} />
          ))}
        </ul>
      )}
    </>
  )
}

export function StudentAttendance() {
  return (
    <StudentPage title="Attendance" lede={(d) => `Every course this term, against the ${d.attendance.threshold}% minimum.`}>
      {(d) => {
        const { threshold: floor, courses } = d.attendance
        const short = courses.filter((c) => c.below_threshold)
        if (courses.length === 0) return <Empty>You are not enrolled in any course this term.</Empty>
        return (
          <>
            {short.length > 0 && (
              <section className="block" aria-labelledby="short-h">
                <h2 id="short-h">Needs your attention</h2>
                <ul className="attention">
                  {short.map((c) => (
                    <li key={c.course} className="alert">
                      <strong>{c.name}</strong>: {c.percent}% attended, below the {floor}% you need. Attend the next{' '}
                      {plural(c.recover ?? 0, 'class', 'classes')} in a row to get back to {floor}%.
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="block" aria-labelledby="att-h">
              <h2 id="att-h">By course</h2>
              <p className="lead">
                {d.attendance.overall_percent === null
                  ? 'No classes have been held yet.'
                  : short.length === 0
                    ? `${d.attendance.overall_percent}% across all your courses, and none is below ${floor}%.`
                    : `${d.attendance.overall_percent}% across all your courses, but ${plural(short.length, 'course is', 'courses are')} below ${floor}%.`}
              </p>
              <CourseBars courses={courses} floor={floor} />
            </section>
          </>
        )
      }}
    </StudentPage>
  )
}
