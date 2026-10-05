import { formatDate, formatMoney } from '../format'
import { Empty } from '../ui'
import { StudentPage } from './StudentPage'

export function StudentFees() {
  return (
    <StudentPage title="Fees" lede={() => 'What you owe and what you have paid, term by term.'}>
      {(d) => {
        const entries = d.fees.entries
        if (entries.length === 0) return <Empty>No fee records.</Empty>
        const owing = entries.filter((f) => f.status !== 'paid' && f.outstanding > 0)
        const paid = entries.reduce((sum, f) => sum + (f.amount_paid ?? 0), 0)
        return (
          <>
            <section className="block" aria-label="Totals">
              <dl className="kpis">
                <div>
                  <dt>Still to pay</dt>
                  <dd>{formatMoney(d.fees.outstanding)}</dd>
                </div>
                <div>
                  <dt>Paid so far</dt>
                  <dd>{formatMoney(paid)}</dd>
                </div>
              </dl>
            </section>

            {owing.length > 0 && (
              <section className="block" aria-labelledby="owe-h">
                <h2 id="owe-h">Needs your attention</h2>
                <ul className="attention">
                  {owing.map((f) => {
                    const late = f.status === 'overdue' || (f.due_date !== null && f.due_date < d.date)
                    return (
                      <li key={f.term} className={late ? 'alert' : 'warn'}>
                        <strong>Fee for {f.term}</strong>: {formatMoney(f.outstanding)} still to pay
                        {f.due_date ? `, ${late ? 'was due' : 'due'} ${formatDate(f.due_date)}` : ''}.
                      </li>
                    )
                  })}
                </ul>
              </section>
            )}

            <section className="block" aria-labelledby="terms-h">
              <h2 id="terms-h">By term</h2>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Term</th>
                      <th scope="col" className="num">Due</th>
                      <th scope="col" className="num">Paid</th>
                      <th scope="col">Status</th>
                      <th scope="col">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((f) => (
                      <tr key={f.term}>
                        <td className="strong">{f.term}</td>
                        <td className="num">{formatMoney(f.amount_due)}</td>
                        <td className="num">{formatMoney(f.amount_paid)}</td>
                        <td>
                          <span className={`badge ${f.status}`}>{f.status}</span>
                        </td>
                        <td className="muted">
                          {f.status === 'paid' ? (f.paid_on ? `Paid ${formatDate(f.paid_on)}` : '-') : f.due_date ? `Due ${formatDate(f.due_date)}` : '-'}
                        </td>
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
