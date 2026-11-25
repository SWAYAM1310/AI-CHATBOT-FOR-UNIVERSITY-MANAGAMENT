// Shared by the approval stamps, the admin pages and the HOD's queue.
import type { DeptApproval, NoticeState } from '../types'

/** The sidebar badge listens for this so its count drops the moment a decision lands. */
export const APPROVALS_CHANGED = 'uniassist:approvals-changed'

/** "Live in 3 of 7 departments" / "Waiting for the CP head of department". */
export function approvalLine(approvals: DeptApproval[], state: NoticeState): string {
  const n = approvals.length
  const live = approvals.filter((a) => a.status === 'approved').length
  const waiting = approvals.filter((a) => a.status === 'pending')
  if (n === 0) return ''
  if (n === 1) {
    const a = approvals[0]
    const who = a.hod ?? `the ${a.dept} head of department`
    if (a.status === 'pending') return `Waiting for ${who} to approve`
    const by = a.decided_by ?? who
    return a.status === 'approved' ? `Approved by ${by}` : `Rejected by ${by}`
  }
  if (state === 'pending') return `Waiting for ${n} heads of department`
  if (state === 'approved') return `Live in all ${n} departments`
  if (state === 'rejected') return `Rejected in all ${n} departments`
  return `Live in ${live} of ${n} departments` + (waiting.length ? `, ${waiting.length} still to decide` : '')
}
