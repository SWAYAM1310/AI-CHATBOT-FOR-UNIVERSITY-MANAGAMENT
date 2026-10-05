import type { NavigateFunction } from 'react-router-dom'

/** The view-transition name that ties a calendar cell's date to the register page heading. */
export const dayTransitionName = (date: string) => `day-${date}`

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Navigate inside a View Transition, so an element carrying the same `view-transition-name`
 * on both pages morphs between them. BrowserRouter commits navigations in a React transition,
 * which flushSync cannot force, so the update callback waits until `ready` (a selector on the
 * destination page) is in the DOM. Browsers without the API, and reduced motion, just navigate.
 */
export function navigateWithTransition(navigate: NavigateFunction, to: string, ready: string): boolean {
  if (typeof document.startViewTransition !== 'function' || reducedMotion()) return false
  document.startViewTransition(async () => {
    navigate(to)
    const started = performance.now()
    // not requestAnimationFrame: rendering is paused while this callback runs, so it never fires
    while (!document.querySelector(ready) && performance.now() - started < 500) {
      await new Promise((r) => setTimeout(r, 16))
    }
  })
  return true
}
