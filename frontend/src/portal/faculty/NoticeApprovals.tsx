import { useState } from 'react'
import { api } from '../../api'
import type { PendingNotice } from '../../types'
import { APPROVALS_CHANGED } from '../approvals'
import { categorize } from '../categories'
import { usePortal } from '../context'
import { CategoryTag } from '../Filters'
import { formatDate, plural } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { describeError, useLoad } from '../useLoad'

type Decision = 'approve' | 'reject'
const NOTE_MAX = 500

const ROLE_LABEL: Record<string, string> = { admin: 'Administration', faculty: 'Faculty', student: 'Student' }

/** Who the notice is addressed to, as the sender wrote it. */
function addressedTo(n: PendingNotice): string {
  if (n.scope === 'course') return `Students of ${n.course}`
  const who = n.audience === 'all' ? 'Students and faculty' : n.audience === 'faculty' ? 'Faculty' : 'Students'
  const where = n.dept ? `the ${n.dept} department` : 'the whole university'
  return `${who} of ${where}${n.semester ? `, semester ${n.semester}` : ''}`
}

/** Who this HOD's approval would release it to: only their own department's slice. */
function reachLine(n: PendingNotice): string {
  const parts = [n.reach_students && plural(n.reach_students, 'student'), n.reach_faculty && plural(n.reach_faculty, 'faculty member')].filter(Boolean)
  const people = parts.length ? parts.join(' and ') : 'nobody right now'
  if (n.scope === 'course') return `Approving shows it to ${people} enrolled in ${n.course}.`
  const mail = n.emails ? ', in the portal and by email' : ' in the portal'
  const slice = n.scope === 'university' ? ` Other departments' heads decide for their own people.` : ''
  return `Approving releases it to ${people} in ${n.your_department}${mail}.${slice}`
}

function PendingCard({ n, onDone }: { n: PendingNotice; onDone: (message: string) => void }) {
  // releasing a notice reaches (and may email) a whole department, so it takes a second click
  const [asking, setAsking] = useState<Decision | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  const decide = async (decision: Decision) => {
    setBusy(true)
    setError(undefined)
    try {
      onDone((await api.decideAnnouncement(n.announcement_id, decision, note)).message)
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  return (
    <li className="approval-card">
      <div className="approval-slip">
        <span className="ann-meta">
          <CategoryTag category={categorize(n)} />
          <span className="muted small">
            From {n.submitted_by.name ?? 'unknown'}
            {n.submitted_by.role ? ` (${ROLE_LABEL[n.submitted_by.role] ?? n.submitted_by.role})` : ''}, {formatDate(n.submitted_at)}
          </span>
        </span>
        <strong className="approval-title">{n.title}</strong>
        <span className="muted small">To: {addressedTo(n)}</span>
        {n.body && <p className="approval-body">{n.body}</p>}
        {n.emails && n.email_body && (
          <details className="approval-email">
            <summary>The email recipients will get</summary>
            <p className="small">
              <strong>{n.email_subject}</strong>
            </p>
            <pre className="email-text">{n.email_body}</pre>
          </details>
        )}
      </div>

      <div className="approval-decide">
        <p className="small">{reachLine(n)}</p>
        <label className="field">
          <span>Note for the sender (optional)</span>
          <textarea
            rows={2}
            value={note}
            maxLength={NOTE_MAX}
            placeholder={asking === 'reject' ? 'Say what needs to change' : 'e.g. Approved, please share in class too'}
            onChange={(e) => setNote(e.target.value)}
            disabled={busy}
          />
        </label>
        {error && <span className="inline-error">{error}</span>}
        <span className="leave-actions">
          {asking ? (
            <>
              <span className="small">{asking === 'approve' ? `Release it to ${n.your_department}?` : `Reject it for ${n.your_department}?`}</span>
              <button type="button" className={asking === 'approve' ? 'btn primary small-btn' : 'btn danger small-btn'} disabled={busy} onClick={() => decide(asking)}>
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
      </div>
    </li>
  )
}

export function NoticeApprovals() {
  const { me } = usePortal()
  const isHod = Boolean(me?.is_hod)
  const { data, error, reload } = useLoad(() => api.announcementApprovals(), isHod ? 'announcement-approvals' : null, true)
  const [done, setDone] = useState<string>()

  return (
    <div className="page">
      <PageHeader
        title="Notice approvals"
        lede="Every announcement for your department waits here first. Nobody sees it, and nobody is emailed, until you approve it."
      />
      {done && <Notice tone="success">{done}</Notice>}
      {!isHod ? (
        <Empty>Announcements are approved by the head of department, so there is nothing here for you to decide.</Empty>
      ) : (
        <>
          {error && <Notice tone="error">{error}</Notice>}
          {!data && !error && <Loading what="notices waiting for approval" />}
          {data && data.length === 0 && <Empty>No announcement is waiting for your approval.</Empty>}
          {data && data.length > 0 && (
            <>
              <p className="lead">{plural(data.length, 'notice is', 'notices are')} waiting, the oldest first.</p>
              <ul className="plain-list approval-list">
                {data.map((n) => (
                  <PendingCard
                    key={n.announcement_id}
                    n={n}
                    onDone={(message) => {
                      setDone(message)
                      reload()
                      window.dispatchEvent(new Event(APPROVALS_CHANGED))
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
