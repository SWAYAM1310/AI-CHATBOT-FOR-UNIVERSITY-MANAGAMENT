import { Link } from 'react-router-dom'
import type { ExamRow } from '../../types'
import { daysBetween, formatDay, plural } from '../format'
import { Empty } from '../ui'
import { StudentPage } from './StudentPage'

const when = (days: number) => (days === 0 ? 'today' : days === 1 ? 'tomorrow' : `in ${plural(days, 'day')}`)

function ExamTable({ exams, caption }: { exams: ExamRow[]; caption: string }) {
  return (
    <div className="table-wrap">
      <table className="data">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Course</th>
            <th scope="col">Exam</th>
            <th scope="col">Time</th>
            <th scope="col">Room</th>
          </tr>
        </thead>
        <tbody>
          {exams.map((e) => (
            <tr key={`${e.exam_type}-${e.course}`}>
              <td className="strong">{formatDay(e.date)}</td>
              <td>
                {e.name} <span className="mono muted small">{e.course}</span>
              </td>
              <td>{e.exam_type}</td>
              <td>{e.start_time ? `${e.start_time} to ${e.end_time ?? ''}` : '-'}</td>
              <td>{e.room ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StudentExams() {
  return (
    <StudentPage title="Exams" lede={() => 'Your exam timetable for this term.'}>
      {(d) => {
        if (d.exams.length === 0) return <Empty>No exams are scheduled for you this term.</Empty>
        const upcoming = d.exams.filter((e) => e.date >= d.date)
        const past = d.exams.filter((e) => e.date < d.date).reverse()
        const next = upcoming[0]
        return (
          <>
            <section className="block" aria-labelledby="next-h">
              <h2 id="next-h">Upcoming</h2>
              {next ? (
                <>
                  <p className="lead">
                    Your next exam is <strong>{next.name}</strong> ({next.exam_type}) on {formatDay(next.date)}
                    {next.start_time ? ` at ${next.start_time}` : ''}
                    {next.room ? ` in room ${next.room}` : ''}, {when(daysBetween(d.date, next.date))}.
                    {upcoming.length > 1 ? ` ${plural(upcoming.length - 1, 'more exam')} after that.` : ' It is your last one this term.'}
                  </p>
                  <ExamTable exams={upcoming} caption="Upcoming exams" />
                </>
              ) : (
                <Empty>No more exams this term.</Empty>
              )}
            </section>

            {past.length > 0 && (
              <section className="block" aria-labelledby="past-h">
                <h2 id="past-h">Already written</h2>
                <ExamTable exams={past} caption="Exams already written" />
                <p className="small muted">
                  Marks for these are on the <Link to="/results">Results</Link> page once your faculty enter them.
                </p>
              </section>
            )}
          </>
        )
      }}
    </StudentPage>
  )
}
