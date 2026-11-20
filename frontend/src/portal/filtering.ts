// Filter state shared by the list pages. A page's chosen filters live in the URL, so a
// refresh, the back button or a copied link keeps them. The controls are in Filters.tsx.
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * A filter kept in the URL query (`?name=value`). A value outside `allowed` reads as "all",
 * so an old or hand-edited link never leaves the page showing nothing.
 */
export function useParamFilter<T extends string>(name: string, allowed?: readonly T[]): [T | '', (value: T | '') => void] {
  const [params, setParams] = useSearchParams()
  const raw = params.get(name) ?? ''
  const value = (allowed && !allowed.includes(raw as T) ? '' : raw) as T | ''
  const set = useCallback(
    (next: T | '') =>
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev)
          if (next) out.set(name, next)
          else out.delete(name)
          return out
        },
        { replace: true },
      ),
    [name, setParams],
  )
  return [value, set]
}

/**
 * Drops several URL filters in one navigation. Calling each filter's setter in turn would not:
 * every setter starts from the URL of the last render, so the second would put back the first.
 */
export function useClearParams(names: readonly string[]): () => void {
  const [, setParams] = useSearchParams()
  return () =>
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        for (const n of names) out.delete(n)
        return out
      },
      { replace: true },
    )
}

/** True when every word of `query` appears in one of `fields` (case-insensitive). */
export function matchesQuery(query: string, ...fields: (string | null | undefined)[]): boolean {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return true
  const text = fields.filter(Boolean).join(' ').toLowerCase()
  return words.every((w) => text.includes(w))
}
