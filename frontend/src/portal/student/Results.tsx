import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import type { ResultAssessment, ResultCourse, ResultsSemester } from '../../types'
import { formatDate, formatDay, plural } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { useLoad } from '../useLoad'

const PASS_PCT = 40 // the pass mark on a component and on a course (Examination Regulations 3.1)
// theory, then practical, then project work; anything else after, by date
const TYPE_ORDER = ['IA', 'Mid-Sem', 'End-Sem', 'Mid-Sem-Viva', 'Lab-File', 'Lab-Exam', 'Term-Work']

interface Row {
  course: ResultCourse
  a: ResultAssessment
}

interface Group {
  type: string
  title: string
  max: number | null // shared by every row, else null
  weight: number | null
  first: string // earliest due date, for ordering
  rows: Row[]
}

/** 9, 8.5, 46.25: no trailing zeros. */
const num = (n: number) => String(Number(n.toFixed(2)))

/** "2026-27 Odd" from "2026-27-ODD". */
function termLabel(term: string): string {
  const m = term.match(/^(\d{4}-\d{2})-(\w+)$/)
  return m ? `${m[1]} ${m[2][0]}${m[2].slice(1).toLowerCase()}` : term
}

const same = <T,>(xs: T[]): T | null => (xs.every((x) => x === xs[0]) ? xs[0] : null)

/** One group per exam type: theory (IA, Mid-Sem, End-Sem), then practical, then project work. */
function groupByType(courses: ResultCourse[]): Group[] {
  const byType = new Map<string, Row[]>()
  for (const course of courses) {
    for (const a of course.assessments) {
      byType.set(a.type, [...(byType.get(a.type) ?? []), { course, a }])
    }
  }
  const groups: Group[] = [...byType].map(([type, rows]) => ({
    type,
    title: rows[0].a.title ?? type,
    max: same(rows.map((r) => r.a.max_marks)),
    weight: same(rows.map((r) => r.a.weightage_pct)),
    first: rows.map((r) => r.a.due_date ?? '9999').sort()[0],
    rows,
  }))
  const rank = (t: string) => (TYPE_ORDER.includes(t) ? TYPE_ORDER.indexOf(t) : TYPE_ORDER.length)
  return groups.sort((x, y) => rank(x.type) - rank(y.type) || x.first.localeCompare(y.first) || x.type.localeCompare(y.type))
}

function Meter({ pct }: { pct: number }) {
  return (
    <span className="score-meter" aria-hidden="true">
      <span className={pct < PASS_PCT ? 'low' : undefined} style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }} />
    </span>
  )
}

function MarkCell({ a }: { a: ResultAssessment }) {
  if (a.is_absent) return <td className="num low" data-label="Marks">Absent</td>
  if (a.score === null || !a.entered) {
    const held = a.status === 'graded' || a.status === 'completed' || (a.due_date !== null && a.due_date < new Date().toLocaleDateString('en-CA'))
    return (
      <td className="num muted" data-label="Marks">
        {a.entered ? 'Not graded' : held ? 'Not entered yet' : a.due_date ? `On ${formatDay(a.due_date)}` : 'Not held yet'}
      </td>
    )
  }
  const pct = a.max_marks ? (a.score * 100) / a.max_marks : null
  // an End-Sem written out of 100 counts as 50 towards the course: say what this mark is worth
  const scaled = pct !== null && a.weightage_pct !== null && a.weightage_pct !== a.max_marks ? (pct * a.weightage_pct) / 100 : null
  return (
    <td className={`num${pct !== null && pct < PASS_PCT ? ' low' : ''}`} data-label="Marks">
      <span className="score">
        {pct !== null && <Meter pct={pct} />}
        <span className="score-text">
          {num(a.score)} / {a.max_marks !== null ? num(a.max_marks) : '?'}
        </span>
      </span>
      {scaled !== null && (
        <span className="score-scaled muted small">
          counts {num(scaled)} / {num(a.weightage_pct!)}
        </span>
      )}
    </td>
  )
}

function CourseCells({ c }: { c: ResultCourse }) {
  return (
    <>
      <td className="mono course-code">{c.course}</td>
      <td className="lead-cell">{c.name}</td>
    </>
  )
}

function ResultTable({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="table-wrap stack-table results-table">
      <table className="data">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Course code</th>
            <th scope="col">Course name</th>
            <th scope="col" className="num">Marks</th>
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

function TypeSection({ g }: { g: Group }) {
  const id = `type-${g.type}`
  const meta = [
    g.max !== null && `out of ${num(g.max)}`,
    g.weight !== null && (g.max === g.weight ? null : `counts as ${num(g.weight)}`),
  ]
    .filter(Boolean)
    .join(', ')
  return (
    <section className="block" aria-labelledby={id}>
      <h2 id={id} className="results-h">
        {g.title}
        {meta && <span className="muted small">{meta}</span>}
      </h2>
      <ResultTable caption={`${g.title} marks`}>
        {g.rows.map(({ course, a }) => (
          <tr key={course.course}>
            <CourseCells c={course} />
            <MarkCell a={a} />
          </tr>
        ))}
      </ResultTable>
    </section>
  )
}

function TotalSection({ courses }: { courses: ResultCourse[] }) {
  const done = courses.filter((c) => c.total !== null)
  const waiting = courses.length - done.length
  return (
    <section className="block results-total" aria-labelledby="type-total">
      <h2 id="type-total" className="results-h">
        Total
        <span className="muted small">out of 100</span>
      </h2>
      {done.length === 0 ? (
        <Empty>The total appears once every exam of {courses.length === 1 ? 'the course' : 'a course'} has its marks.</Empty>
      ) : (
        <>
          <ResultTable caption="Course totals out of 100">
            {done.map((c) => {
              const t = c.total!
              const pct = (t.score * 100) / t.out_of
              return (
                <tr key={c.course}>
                  <CourseCells c={c} />
                  <td className={`num${pct < PASS_PCT ? ' low' : ''}`} data-label="Marks">
                    <span className="score">
                      <Meter pct={pct} />
                      <span className="score-text">
                        {num(t.score)} / {num(t.out_of)}
                      </span>
                    </span>
                  </td>
                </tr>
              )
            })}
          </ResultTable>
          {waiting > 0 && (
            <p className="small muted results-note">
              {plural(waiting, 'more course is', 'more courses are')} still waiting on an exam.
            </p>
          )}
        </>
      )}
    </section>
  )
}

function semesterLede(s: ResultsSemester): string {
  const head = `Semester ${s.semester}, ${termLabel(s.term)} term${s.current ? ' (this term)' : ''}. ${plural(s.courses.length, 'course')}.`
  const r = s.result
  if (!r) return s.current ? `${head} Marks appear here as your instructors enter them.` : head
  const parts = [
    r.sgpa !== null && `SGPA ${r.sgpa}`,
    r.cgpa !== null && `CGPA ${r.cgpa}`,
    r.result_status,
    r.backlogs ? plural(r.backlogs, 'backlog') : null,
  ].filter(Boolean)
  return `${head} ${parts.join(', ')}${r.declared_on ? `, declared ${formatDate(r.declared_on)}` : ''}.`
}

export function Results() {
  const { data, error } = useLoad(() => api.studentResults(), 'student-results', true)
  const [params, setParams] = useSearchParams()

  const semesters = data?.semesters ?? []
  const sem = semesters.find((s) => String(s.semester) === params.get('sem')) ?? semesters.find((s) => s.current) ?? semesters[0]
  const course = sem?.courses.find((c) => c.course === params.get('course'))
  const shown = sem ? (course ? [course] : sem.courses) : []
  const groups = groupByType(shown)

  function pick(next: { sem?: string; course?: string }) {
    const p = new URLSearchParams(params)
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v)
      else p.delete(k)
    }
    setParams(p, { replace: true })
  }

  return (
    <div className="page">
      <PageHeader title="Results" lede={sem ? semesterLede(sem) : undefined} />
      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <Loading what="your results" />}
      {data && semesters.length === 0 && <Empty>You have no courses on record yet.</Empty>}

      {sem && (
        <>
          <div className="toolbar results-toolbar">
            <label className="field-inline">
              <span>Semester</span>
              <select
                value={sem.semester}
                onChange={(e) => {
                  const next = semesters.find((s) => String(s.semester) === e.target.value)
                  // keep the subject only if the new semester has it
                  pick({ sem: e.target.value, course: next?.courses.some((c) => c.course === course?.course) ? course?.course : '' })
                }}
              >
                {semesters.map((s) => (
                  <option key={s.semester} value={s.semester}>
                    Semester {s.semester} ({termLabel(s.term)}{s.current ? ', current' : ''})
                  </option>
                ))}
              </select>
            </label>
            <label className="field-inline">
              <span>Subject</span>
              <select value={course?.course ?? ''} onChange={(e) => pick({ course: e.target.value })}>
                <option value="">All subjects</option>
                {sem.courses.map((c) => (
                  <option key={c.course} value={c.course}>
                    {c.name} ({c.course})
                  </option>
                ))}
              </select>
            </label>
          </div>

          {groups.length === 0 ? (
            <Empty>No assessments have been set for {course ? course.name : 'this semester'} yet.</Empty>
          ) : (
            <>
              {groups.map((g) => (
                <TypeSection key={g.type} g={g} />
              ))}
              <TotalSection courses={shown} />
            </>
          )}
        </>
      )}
    </div>
  )
}
