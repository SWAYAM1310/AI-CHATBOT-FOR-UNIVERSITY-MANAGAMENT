import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import { FEE_STATUSES, type FeeRecord, type FeeStatus } from '../../types'
import { formatDate, formatMoney, plural, todayISO } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { describeError, useLoad } from '../useLoad'

const SEARCH_DELAY_MS = 300

function PaymentDialog({ fee, onClose, onRecorded }: { fee: FeeRecord; onClose: () => void; onRecorded: (text: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [amount, setAmount] = useState(String(fee.outstanding))
  const [paidOn, setPaidOn] = useState(todayISO())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    ref.current?.showModal()
  }, [])

  const n = Number(amount)
  const problem =
    amount.trim() === '' || !Number.isFinite(n)
      ? 'Enter an amount'
      : n <= 0
        ? 'Must be more than zero'
        : n > fee.outstanding
          ? `Only ${formatMoney(fee.outstanding)} is outstanding`
          : null

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (problem) return
    setBusy(true)
    setError(null)
    try {
      const out = await api.recordPayment(fee.fee_id, { amount: n, paid_on: paidOn || undefined })
      const left = out.fee.outstanding
      onRecorded(
        `Recorded ${formatMoney(n)} from ${fee.full_name} (${fee.roll_no}). ` +
          (left > 0 ? `${formatMoney(left)} is still outstanding.` : 'The fee is now paid in full.'),
      )
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="dialog" aria-labelledby="pay-h" onClose={onClose}>
      <form onSubmit={submit}>
        <h2 id="pay-h">Record a payment</h2>
        <p className="muted small">
          {fee.full_name} <span className="mono">{fee.roll_no}</span>, {fee.term}. {formatMoney(fee.amount_paid)} of {formatMoney(fee.amount_due)} paid so far.
        </p>
        <div className="form-grid">
          <label className="field">
            <span>Amount received (₹)</span>
            <input
              type="number"
              inputMode="decimal"
              min={1}
              max={fee.outstanding}
              step="any"
              value={amount}
              autoFocus
              aria-invalid={problem ? true : undefined}
              onChange={(e) => {
                setAmount(e.target.value)
                setError(null)
              }}
            />
            {problem && amount !== '' && <span className="cell-error">{problem}</span>}
          </label>
          <label className="field">
            <span>Received on</span>
            <input type="date" value={paidOn} max={todayISO()} onChange={(e) => setPaidOn(e.target.value)} />
          </label>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions dialog-actions">
          <button type="button" onClick={() => ref.current?.close()} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy || problem !== null}>
            {busy ? 'Recording…' : 'Record payment'}
          </button>
        </div>
      </form>
    </dialog>
  )
}

export function Fees() {
  const [params, setParams] = useSearchParams()
  const dept = params.get('dept') ?? ''
  const status = (FEE_STATUSES as readonly string[]).includes(params.get('status') ?? '') ? (params.get('status') as FeeStatus) : ''
  const q = params.get('q') ?? ''
  const page = Math.max(1, Number(params.get('page')) || 1)

  const departments = useLoad(() => api.adminDashboard(), 'admin-dashboard')
  const key = JSON.stringify({ dept, status, q, page })
  const list = useLoad(() => api.fees({ dept, status, q, page }), key, true)

  const [search, setSearch] = useState(q)
  const [paying, setPaying] = useState<FeeRecord | null>(null)
  const [note, setNote] = useState<string | null>(null)

  /** Change filters; any change other than paging goes back to page 1. */
  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next, { replace: true })
    setNote(null)
  }

  // search as you type, once typing pauses
  useEffect(() => {
    if (search.trim() === q) return
    const id = window.setTimeout(() => {
      const next = new URLSearchParams(params)
      if (search.trim()) next.set('q', search.trim())
      else next.delete('q')
      next.delete('page')
      setParams(next, { replace: true })
    }, SEARCH_DELAY_MS)
    return () => window.clearTimeout(id)
  }, [search, q, params, setParams])

  const data = list.data
  const counts = data?.counts
  const all = counts ? FEE_STATUSES.reduce((sum, s) => sum + counts[s], 0) : 0
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const first = data && data.total ? (data.page - 1) * data.page_size + 1 : 0
  const last = data ? first + data.fees.length - 1 : 0

  return (
    <div className="page">
      <PageHeader title="Fees" lede={data ? `Fee records for the ${data.term} term. Record a payment and the student sees it at once.` : undefined} />

      <div className="toolbar">
        <label className="field-inline">
          <span>Department</span>
          <select value={dept} onChange={(e) => update({ dept: e.target.value })}>
            <option value="">All departments</option>
            {departments.data?.departments
              .filter((d) => d.students > 0 || d.dept === dept)
              .map((d) => (
                <option key={d.dept} value={d.dept}>
                  {d.name} ({d.dept})
                </option>
              ))}
          </select>
        </label>
        <label className="field-inline">
          <span>Search</span>
          <input type="search" placeholder="Roll number or name" value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
      </div>

      {counts && (
        <div className="chips" role="group" aria-label="Filter by status">
          <button type="button" className={status === '' ? 'chip active' : 'chip'} aria-pressed={status === ''} onClick={() => update({ status: '' })}>
            All <span className="chip-count">{all}</span>
          </button>
          {FEE_STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              className={status === s ? `chip active ${s}` : `chip ${s}`}
              aria-pressed={status === s}
              onClick={() => update({ status: status === s ? '' : s })}
            >
              {s[0].toUpperCase() + s.slice(1)} <span className="chip-count">{counts[s]}</span>
            </button>
          ))}
        </div>
      )}

      {note && <Notice tone="success">{note}</Notice>}
      {list.error && <Notice tone="error">{list.error}</Notice>}
      {!data && !list.error && <Loading what="fee records" />}

      {data && data.fees.length === 0 && <Empty>No fee records match these filters.</Empty>}
      {data && data.fees.length > 0 && (
        <>
          <div className="table-wrap stack-table" aria-busy={list.loading}>
            <table className="data fees">
              <thead>
                <tr>
                  <th>Roll no.</th>
                  <th>Name</th>
                  <th className="num">Due</th>
                  <th className="num">Paid</th>
                  <th className="num">Outstanding</th>
                  <th>Status</th>
                  <th>Due date</th>
                  <th>
                    <span className="sr-only">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.fees.map((f) => (
                  <tr key={f.fee_id}>
                    <td className="mono" data-label="Roll no.">
                      {f.roll_no}
                    </td>
                    <td className="lead-cell">
                      {f.full_name}
                      <span className="muted small block-line">
                        {f.dept_code}, semester {f.semester}
                      </span>
                    </td>
                    <td className="num phone-hide">{formatMoney(f.amount_due)}</td>
                    <td className="num" data-label="Paid">
                      {formatMoney(f.amount_paid)}
                    </td>
                    <td className={f.outstanding > 0 ? 'num strong' : 'num muted'} data-label="Outstanding">
                      {formatMoney(f.outstanding)}
                    </td>
                    <td data-label="Status">
                      <span className={`badge ${f.status}`}>{f.status}</span>
                    </td>
                    <td className="small" data-label="Due date">
                      <span>
                        {formatDate(f.due_date)}
                        {f.paid_on && <span className="muted block-line">paid {formatDate(f.paid_on)}</span>}
                      </span>
                    </td>
                    <td>
                      {f.outstanding > 0 && (
                        <button type="button" className="small-btn" onClick={() => setPaying(f)} aria-label={`Record a payment from ${f.full_name}`}>
                          Record payment
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <nav className="pager" aria-label="Pages">
            <span className="muted small">
              {first}–{last} of {plural(data.total, 'record')}
            </span>
            <span className="pager-buttons">
              <button type="button" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>
                Previous
              </button>
              <span className="small">
                Page {data.page} of {pages}
              </span>
              <button type="button" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })}>
                Next
              </button>
            </span>
          </nav>
        </>
      )}

      {paying && (
        <PaymentDialog
          fee={paying}
          onClose={() => setPaying(null)}
          onRecorded={(text) => {
            setPaying(null)
            setNote(text)
            list.reload()
          }}
        />
      )}
    </div>
  )
}
