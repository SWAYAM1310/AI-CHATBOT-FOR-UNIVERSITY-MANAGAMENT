import { useState } from 'react'
import { api } from '../../api'
import type { PendingLeave } from '../../types'
import { usePortal } from '../context'
import { daysBetween, formatDate, plural } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { describeError, useLoad } from '../useLoad'

type Decision = 'approve' | 'reject'

function LeaveRow({ r, onDone }: { r: PendingLeave; onDone: (message: string) => void }) {
  // a decision emails the student, so it takes a second click to confirm
  const [asking, setAsking] = useState<Decision | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const days = daysBetween(r.from_date, r.to_date) + 1

  const decide = async (decision: Decision) => {
    setBusy(true)
    setError(undefined)
    try {
      onDone((await api.decideLeave(r.leave_request_id, decision)).message)
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  return (
    <li className="leave-row">
      <span className="leave-what">
        <span>
          <strong>{r.full_name}</strong> <span className="mono muted small">{r.roll_no}</span>
        </span>
        <span>
          {formatDate(r.from_date)}
          {days > 1 ? ` to ${formatDate(r.to_date)}` : ''} <span className="muted">({plural(days, 'day')})</span>
        </span>
        {r.reason && <span className="muted">{r.reason}</span>}
        {r.applied_on && <span className="muted small">Applied {formatDate(r.applied_on)}</span>}
        {error && <span className="inline-error">{error}</span>}
      </span>
      <span className="leave-actions">
        {asking ? (
          <>
            <span className="small">
              {asking === 'approve' ? 'Approve' : 'Reject'} and email {r.full_name.split(' ')[0]}?
            </span>
            <button type="button" className="btn primary small-btn" disabled={busy} onClick={() => decide(asking)}>
              {busy ? 'Saving…' : `Yes, ${asking}`}
            </button>
            <button type="button" className="btn small-btn" disabled={busy} onClick={() => setAsking(null)}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn primary small-btn" onClick={() => setAsking('approve')}>
              Approve
            </button>
            <button type="button" className="btn small-btn" onClick={() => setAsking('reject')}>
              Reject
            </button>
          </>
        )}
      </span>
    </li>
  )
}

export function LeaveRequests() {
  const { me } = usePortal()
  const isHod = Boolean(me?.is_hod)
  const { data, error, reload } = useLoad(() => api.leaveRequests(), isHod ? 'leave-requests' : null, true)
  const [done, setDone] = useState<string>()

  return (
    <div className="page">
      <PageHeader
        title="Leave requests"
        lede="Student leave requests in your department waiting for your decision. The student is emailed either way."
      />
      {done && <Notice tone="success">{done}</Notice>}
      {!isHod ? (
        <Empty>Leave requests go to the head of department, so there is nothing here for you to decide.</Empty>
      ) : (
        <>
          {error && <Notice tone="error">{error}</Notice>}
          {!data && !error && <Loading what="leave requests" />}
          {data && data.length === 0 && <Empty>Nothing is waiting for your decision.</Empty>}
          {data && data.length > 0 && (
            <>
              <p className="lead">{plural(data.length, 'request is', 'requests are')} waiting, the earliest leave first.</p>
              <ul className="plain-list">
                {data.map((r) => (
                  <LeaveRow
                    key={r.leave_request_id}
                    r={r}
                    onDone={(message) => {
                      setDone(message)
                      reload()
                    }}
                  />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}
