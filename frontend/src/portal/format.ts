import type { FacultyCourse } from '../types'

export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const LONG_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const LONG_MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

/** Monday-first weekday index (0 = Mon), matching Python's date.weekday(). */
export function weekdayOf(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return (new Date(y, m - 1, d).getDay() + 6) % 7
}

/** "2026-10" plus n months. */
export function shiftMonth(month: string, n: number): string {
  const [y, m] = month.split('-').map(Number)
  const t = new Date(y, m - 1 + n, 1)
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`
}

/** "October 2026" from "2026-10". */
export function monthTitle(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return `${LONG_MONTHS[m - 1]} ${y}`
}

/** "Monday", "5 October" from "2026-10-05": the two lines of a register page's heading. */
export function longDay(iso: string): { weekday: string; date: string } {
  const [, m, d] = iso.slice(0, 10).split('-').map(Number)
  return { weekday: LONG_DAYS[weekdayOf(iso)], date: `${d} ${LONG_MONTHS[m - 1]}` }
}

/** Today as YYYY-MM-DD in the browser's own timezone (toISOString would be UTC). */
export function todayISO(): string {
  return new Date().toLocaleDateString('en-CA')
}

/** "Tue 6 Oct" from "2026-10-06". */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return `${DAYS[(date.getDay() + 6) % 7]} ${d} ${MONTHS[m - 1]}`
}

/** "6 Oct 2026". */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return `${d} ${MONTHS[m - 1]} ${y}`
}

export function greeting(now = new Date()): string {
  const h = now.getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

/** "CP, semester 3, division 1" / "CE, semester 1, lab group B2". */
export function sectionLabel(c: Pick<FacultyCourse, 'dept_code' | 'semester' | 'division' | 'lab_group'>): string {
  const part = c.lab_group ? `lab group ${c.lab_group}` : c.division ? `division ${c.division}` : ''
  return [c.dept_code, `semester ${c.semester}`, part].filter(Boolean).join(', ')
}

/** The batch a class is taught to, short enough for a calendar cell: "Lab B2", "Div 1". */
export function batchLabel(c: Pick<FacultyCourse, 'division' | 'lab_group'>): string {
  return c.lab_group ? `Lab ${c.lab_group}` : c.division ? `Div ${c.division}` : ''
}

/** "Dr. Milan Vyas" is greeted as "Dr. Milan", not "Dr.". */
export function firstName(full: string | undefined): string {
  const [first = '', second = ''] = (full ?? '').trim().split(/\s+/)
  return first.endsWith('.') && second ? `${first} ${second}` : first
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

const RUPEES = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
export const formatMoney = (n: number | null | undefined) => RUPEES.format(n ?? 0)
