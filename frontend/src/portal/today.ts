// Today's classes against the wall clock, shared by the student and faculty Home pages.
import { useEffect, useState } from 'react'

export type SlotState = 'done' | 'now' | 'next' | 'later'

export const SLOT_TAG: Record<SlotState, string> = { done: 'Done', now: 'Now', next: 'Next', later: '' }

/** The current time, refreshed every half minute so "now" and "next" follow the clock. */
export function useClock(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

/**
 * Where each of today's classes (sorted by start) stands at `hhmm`. Classes can overlap,
 * so several may be on now; when none is, every class starting soonest is next.
 * All 'later' when the page is not showing today.
 */
export function slotStates(slots: { start_time: string; end_time: string }[], live: boolean, hhmm: string): SlotState[] {
  if (!live) return slots.map(() => 'later')
  const isNow = (c: { start_time: string; end_time: string }) => c.start_time <= hhmm && hhmm < c.end_time
  const anyNow = slots.some(isNow)
  const nextStart = anyNow ? undefined : slots.find((c) => c.start_time > hhmm)?.start_time
  return slots.map((c) => (isNow(c) ? 'now' : c.start_time === nextStart ? 'next' : c.end_time <= hhmm ? 'done' : 'later'))
}
