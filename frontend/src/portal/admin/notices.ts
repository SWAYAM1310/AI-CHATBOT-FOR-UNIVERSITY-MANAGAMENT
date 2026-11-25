import type { AdminNotice, DeliveryCounts } from '../../types'
import { plural } from '../format'

/** "Students, CP department, semester 3" / "Everyone, whole university". */
export function noticeAudience(n: Pick<AdminNotice, 'audience' | 'dept' | 'semester'>): string {
  const roles = n.audience.split(',')
  const who = roles.includes('student') && roles.includes('faculty') ? 'Everyone' : roles.includes('faculty') ? 'Faculty' : 'Students'
  const where = n.dept ? `${n.dept} department` : 'whole university'
  return [who, where, n.semester ? `semester ${n.semester}` : ''].filter(Boolean).join(', ')
}

/** Where a notice's emails stand, knowing they only go out as each head of department approves. */
export function noticeProgress(n: Pick<AdminNotice, 'delivery' | 'emailing' | 'status'>): string {
  if (n.status === 'rejected') return 'Not sent: every head of department rejected it'
  if (n.delivery.total === 0) {
    if (!n.emailing) return 'In-app only, no emails'
    return n.status === 'pending' ? 'Emails go out as each head of department approves' : 'No emails were needed'
  }
  const line = deliverySummary(n.delivery)
  return n.status === 'partial' && n.emailing ? `${line}; more as the other heads approve` : line
}

/** One line on where a notice's emails stand. Older notices (seeded, or published with email off) have none. */
export function deliverySummary(d: DeliveryCounts): string {
  if (d.total === 0) return 'In-app only, no emails'
  const parts = [`${d.sent} of ${plural(d.total, 'email')} sent`]
  if (d.queued) parts.push(`${d.queued} sending`)
  if (d.held) parts.push(`${d.held} held (demo cap)`)
  if (d.failed) parts.push(`${d.failed} failed`)
  if (d.suppressed) parts.push(`${d.suppressed} suppressed`)
  return parts.join(', ')
}
