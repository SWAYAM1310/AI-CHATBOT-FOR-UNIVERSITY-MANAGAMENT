// What an announcement is about. Notices carry no category field, so it is read from the
// title (then the body, if the title says nothing) with the rules below, checked in order:
// the first rule that matches wins. The order matters: "Guest lecture" is an event before
// "lecture" can make it a class change, and "placement drive" is a placement before
// "campus" can make it a campus notice.

export const CATEGORIES = ['exams', 'coursework', 'classes', 'fees', 'events', 'holidays', 'placements', 'campus', 'general'] as const
export type Category = (typeof CATEGORIES)[number]

export const CATEGORY_LABEL: Record<Category, string> = {
  exams: 'Exams',
  coursework: 'Coursework',
  classes: 'Class changes',
  fees: 'Fees',
  events: 'Events',
  holidays: 'Holidays',
  placements: 'Placements',
  campus: 'Campus',
  general: 'General',
}

const RULES: [Category, RegExp][] = [
  ['placements', /placement|internship|recruit|career|job fair|treds/i],
  ['fees', /\bfees?\b|payment|scholarship|refund|\bdues\b/i],
  ['holidays', /holiday|vacation|\bclosed\b|closure|\bbreak\b/i],
  ['exams', /\bexam|examination|viva|hall ticket|admit card|\bresults?\b/i],
  ['events', /guest lecture|seminar|workshop|sports|cultural|convocation|\bfest\b|hackathon|webinar|competition|ceremony|orientation/i],
  ['coursework', /\bia\b|assignment|submission|deadline|project|syllabus|lab file|term.?work/i],
  ['classes', /reschedul|cancel|postpone|extra .*session|doubt|lecture|\bclass(es)?\b|timetable/i],
  ['campus', /library|hostel|helpline|safety|ragging|transport|\bbus\b|canteen|wi-?fi|facilit|security|health|medical/i],
]

function match(text: string | null | undefined): Category | null {
  if (!text) return null
  for (const [category, rule] of RULES) if (rule.test(text)) return category
  return null
}

export function categorize(n: { title: string; body?: string | null }): Category {
  return match(n.title) ?? match(n.body) ?? 'general'
}

/** Chip options for the categories present in `items`, in the fixed order above. */
export function categoryOptions(items: { title: string; body?: string | null }[]) {
  const counts = new Map<Category, number>()
  for (const n of items) {
    const c = categorize(n)
    counts.set(c, (counts.get(c) ?? 0) + 1)
  }
  return CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABEL[c], count: counts.get(c) ?? 0, swatch: `cat-${c}` }))
}
