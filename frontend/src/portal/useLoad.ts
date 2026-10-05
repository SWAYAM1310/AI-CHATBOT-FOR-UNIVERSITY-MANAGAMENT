import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api'

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'Your session has expired. Sign in again.'
    return err.message
  }
  return 'The server could not be reached.'
}

interface Result<T> {
  key: string
  tick: number
  data?: T
  error?: string
  status?: number
}

export interface Loaded<T> {
  /** The data for the current `key`. Kept across a reload so the screen does not flash empty. */
  data: T | undefined
  error: string | undefined
  /** HTTP status of a failed load, e.g. 404 for "not yours". */
  status: number | undefined
  loading: boolean
  /** Bumps each time a (re)load lands, so a form can re-seed from fresh data. */
  version: number
  reload: () => void
}

/**
 * Load something when `key` changes, and again on `reload()`, when the tab regains focus
 * (so a dashboard shows what a colleague entered while it sat in the background) and,
 * if `everyMs` is given, on that interval while the tab is visible.
 * Pass `null` as the key to skip loading.
 */
export function useLoad<T>(load: () => Promise<T>, key: string | null, refreshOnFocus = false, everyMs = 0): Loaded<T> {
  const [result, setResult] = useState<Result<T>>()
  const [tick, setTick] = useState(0)
  const loadRef = useRef(load)
  useEffect(() => {
    loadRef.current = load
  })

  useEffect(() => {
    if (key === null) return
    let cancelled = false
    loadRef
      .current()
      .then((data) => {
        if (!cancelled) setResult({ key, tick, data })
      })
      .catch((err) => {
        if (!cancelled) setResult({ key, tick, error: describeError(err), status: err instanceof ApiError ? err.status : undefined })
      })
    return () => {
      cancelled = true
    }
  }, [key, tick])

  useEffect(() => {
    if (!refreshOnFocus) return
    const onFocus = () => setTick((t) => t + 1)
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [refreshOnFocus])

  useEffect(() => {
    if (!everyMs) return
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') setTick((t) => t + 1)
    }, everyMs)
    return () => window.clearInterval(id)
  }, [everyMs])

  const current = key !== null && result?.key === key ? result : undefined
  return {
    data: current?.data,
    error: current?.error,
    status: current?.status,
    loading: key !== null && (current === undefined || current.tick !== tick),
    version: current?.tick ?? -1,
    reload: useCallback(() => setTick((t) => t + 1), []),
  }
}
