import { FilterChips } from '../Filters'
import { useParamFilter } from '../filtering'
import { formatDate, plural } from '../format'
import { Empty } from '../ui'
import { courseNames } from './dashboard'
import { StudentPage } from './StudentPage'

// what most needs doing first
const STATUSES = ['missing', 'late', 'submitted'] as const
type Status = (typeof STATUSES)[number]
const rank = (s: string) => (STATUSES.includes(s as Status) ? STATUSES.indexOf(s as Status) : STATUSES.length)

export function StudentActivities() {
  const [status, setStatus] = useParamFilter<Status>('status', STATUSES)
  return (
    <StudentPage title="Curricular activities" lede={() => 'Your assignments and projects this term, and whether each one is handed in.'}>
      {(d) => {
        const work = d.assignments
        if (work.length === 0) return <Empty>No assignments or projects have been set for you this term.</Empty>
        const nameOf = courseNames(d)
        const count = (s: string) => work.filter((a) => a.status === s).length
        const missing = work.filter((a) => a.status === 'missing')
        const shown = (status ? work.filter((a) => a.status === status) : work)
          .slice()
          .sort((x, y) => rank(x.status) - rank(y.status) || (x.due_date ?? '').localeCompare(y.due_date ?? ''))
        return (
          <>
            <p className="lead">
              {count('submitted') + count('late')} of {work.length} handed in
              {count('late') > 0 ? `, ${count('late')} of them late` : ''}
              {missing.length > 0 ? `. ${plural(missing.length, 'is', 'are')} still missing.` : '. Nothing is missing.'}
            </p>

            {missing.length > 0 && (
              <section className="block" aria-labelledby="miss-h">
                <h2 id="miss-h">Needs your attention</h2>
                <ul className="attention">
                  {missing.map((a) => (
                    <li key={`${a.course}-${a.title}`} className="warn">
                      <strong>{nameOf(a.course) ?? a.course}</strong>: {a.title ?? 'assignment'} not submitted
                      {a.due_date ? `, was due ${formatDate(a.due_date)}` : ''}. Speak to your course faculty.
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="block" aria-labelledby="work-h">
              <h2 id="work-h">All work</h2>
              <FilterChips
                label="Filter by status"
                options={STATUSES.map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1), count: count(s), tone: s === 'missing' ? 'overdue' : undefined }))}
                value={status}
                onChange={setStatus}
                total={work.length}
              />
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Course</th>
                      <th scope="col">Work</th>
                      <th scope="col">Due</th>
                      <th scope="col">Status</th>
                      <th scope="col">Handed in</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((a) => (
                      <tr key={`${a.course}-${a.title}`}>
                        <td>
                          <strong>{nameOf(a.course) ?? a.course}</strong> <span className="mono muted small">{a.course}</span>
                        </td>
                        <td>{a.title ?? 'Assignment'}</td>
                        <td>{a.due_date ? formatDate(a.due_date) : '-'}</td>
                        <td>
                          <span className={`badge ${a.status}`}>{a.status}</span>
                        </td>
                        <td className="muted">{a.submitted_at ? formatDate(a.submitted_at) : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )
      }}
    </StudentPage>
  )
}
