import type { DeptApproval, NoticeState } from '../types'
import { approvalLine } from './approvals'
import { formatDate } from './format'

const MARK: Record<DeptApproval['status'], string> = { approved: '✓', pending: '…', rejected: '✕' }
const WORD: Record<DeptApproval['status'], string> = { approved: 'approved', pending: 'waiting', rejected: 'rejected' }

function title(a: DeptApproval): string {
  const head = a.hod ? ` (HOD ${a.hod})` : ''
  if (a.status === 'pending') return `${a.dept}${head}: waiting for approval`
  const when = a.decided_at ? ` on ${formatDate(a.decided_at)}` : ''
  return `${a.dept}: ${a.status}${a.decided_by ? ` by ${a.decided_by}` : ''}${when}${a.note ? `. “${a.note}”` : ''}`
}

/**
 * The sign-off line under a notice: one stamp per department, filled when its HOD
 * approves, struck through when they reject, dotted while it waits.
 */
export function ApprovalTrack({ approvals, state }: { approvals: DeptApproval[]; state: NoticeState }) {
  if (approvals.length === 0) return null
  const notes = approvals.filter((a) => a.note)
  return (
    <div className="approval-track">
      <ul className="approval-stamps" aria-label="Approval by department">
        {approvals.map((a) => (
          <li key={a.dept} className={`stamp ${a.status}`} title={title(a)}>
            <span aria-hidden="true">{MARK[a.status]}</span>
            {a.dept}
            <span className="sr-only">: {WORD[a.status]}</span>
          </li>
        ))}
      </ul>
      <span className={`small approval-line ${state}`}>{approvalLine(approvals, state)}</span>
      {notes.map((a) => (
        <span key={a.dept} className="small muted approval-note">
          {a.dept}
          {a.decided_by ? `, ${a.decided_by}` : ''}: “{a.note}”
        </span>
      ))}
    </div>
  )
}
