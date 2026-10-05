// One class on one day, as a register: every enrolled student with a Present / Absent
// pair. Keyboard: P or A marks the focused student and moves down; arrow keys move.
import { useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { api } from '../../api'
import type { RosterStudent } from '../../types'
import { plural } from '../format'
import { Empty, Loading, Notice } from '../ui'
import { describeError, useLoad } from '../useLoad'

const PERIODS = ['1', '2', '3', '4']

function sameSet(a: Set<string>, b: string[]): boolean {
  return a.size === b.length && b.every((x) => a.has(x))
}

export function RegisterSheet({ offeringId, date, students, onSaved }: {
  offeringId: number
  date: string
  students: RosterStudent[]
  onSaved: () => void
}) {
  const [slot, setSlot] = useState('') // '' = the class has no period number
  const [absent, setAbsent] = useState<Set<string>>(new Set())
  const [seeded, setSeeded] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ tone: 'error' | 'success'; text: string } | null>(null)
  const listRef = useRef<HTMLOListElement>(null)

  const day = useLoad(() => api.attendanceDay(offeringId, date), `attendance-${offeringId}-${date}`)
  const sessions = day.data?.sessions ?? []
  // the session this sheet edits: the one in the chosen period, or the day's only one
  const target =
    slot === ''
      ? sessions.length === 1
        ? sessions[0]
        : sessions.find((s) => s.slot_no === null)
      : sessions.find((s) => String(s.slot_no) === slot)
  const ambiguous = slot === '' && sessions.length > 1 && !target

  // (re)fill the register whenever the class, the period or the saved data changes
  const seedKey = day.data && !day.loading ? `${offeringId}|${date}|${slot}|${target?.id ?? 'new'}|${day.version}` : null
  if (seedKey !== null && seedKey !== seeded) {
    setSeeded(seedKey)
    setAbsent(new Set(target?.absent_roll_nos ?? []))
  }

  const present = students.length - absent.size
  const unchanged = target ? sameSet(absent, target.absent_roll_nos) : false
  const locked = busy || ambiguous

  function mark(roll: string, isAbsent: boolean) {
    setNote(null)
    setAbsent((prev) => {
      if (prev.has(roll) === isAbsent) return prev
      const next = new Set(prev)
      if (isAbsent) next.add(roll)
      else next.delete(roll)
      return next
    })
  }

  function focusRow(index: number, which: 'p' | 'a') {
    const row = listRef.current?.children[index]
    row?.querySelector<HTMLButtonElement>(`.pa-${which}`)?.focus()
  }

  function onKeyDown(e: KeyboardEvent<HTMLOListElement>) {
    if (locked || e.altKey || e.ctrlKey || e.metaKey) return
    const li = (e.target as HTMLElement).closest('li')
    const index = li ? Array.prototype.indexOf.call(listRef.current?.children ?? [], li) : -1
    if (index < 0) return
    const roll = students[index].roll_no
    const key = e.key.toLowerCase()
    const which = (e.target as HTMLElement).classList.contains('pa-a') ? 'a' : 'p'
    if (key === 'p' || key === 'a') {
      e.preventDefault()
      mark(roll, key === 'a')
      focusRow(Math.min(index + 1, students.length - 1), key)
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      focusRow(Math.max(0, Math.min(students.length - 1, index + (e.key === 'ArrowDown' ? 1 : -1))), which)
    }
  }

  async function save() {
    setBusy(true)
    setNote(null)
    const body = {
      date,
      slot_no: target ? target.slot_no : slot === '' ? null : Number(slot),
      absent_roll_nos: [...absent].sort(),
    }
    try {
      const out = target ? await api.correctAttendance(offeringId, body) : await api.markAttendance(offeringId, body)
      day.reload()
      onSaved() // every student's percentage just moved
      setNote({ tone: 'success', text: out.message })
    } catch (err) {
      setNote({ tone: 'error', text: describeError(err) })
    } finally {
      setBusy(false)
    }
  }

  if (day.error) return <Notice tone="error">{day.error}</Notice>
  if (!day.data) return <Loading what="the register" />
  if (students.length === 0) return <Empty>No one is enrolled in this section.</Empty>

  const share = students.length ? present / students.length : 0
  return (
    <section className="register" aria-label="Register">
      <div className="register-tools">
        <label className="field-inline">
          <span>Period</span>
          <select value={slot} onChange={(e) => {
              setSlot(e.target.value)
              setNote(null)
            }}
            disabled={busy}
          >
            <option value="">Not specified</option>
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                Period {p}
                {sessions.some((s) => String(s.slot_no) === p) ? ' (recorded)' : ''}
              </option>
            ))}
          </select>
        </label>
        <p className="register-hint muted small">
          Press <kbd>P</kbd> or <kbd>A</kbd> to mark and move down.
        </p>
        <span className="toolbar-spacer" />
        <button type="button" onClick={() => setAbsent(new Set())} disabled={absent.size === 0 || locked}>
          Mark everyone present
        </button>
      </div>

      {target && (
        <Notice tone="info">
          This register is already recorded{target.slot_no ? ` for period ${target.slot_no}` : ''}. Saving corrects it.
        </Notice>
      )}
      {ambiguous && <Notice tone="info">This class met more than once today. Pick the period to see or correct it.</Notice>}

      <ol className="reg-list" ref={listRef} onKeyDown={onKeyDown} aria-label="Students">
        {students.map((s) => {
          const isAbsent = absent.has(s.roll_no)
          return (
            <li key={s.roll_no} className={`reg-row ${isAbsent ? 'is-absent' : 'is-present'}`}>
              <span className="reg-roll mono">{s.roll_no}</span>
              <span className="reg-name">{s.full_name}</span>
              <span className="reg-pct muted small">{s.attendance_percent === null ? '' : `${s.attendance_percent}% so far`}</span>
              <span className="pa" role="group" aria-label={s.full_name}>
                <button
                  type="button"
                  className="pa-p"
                  aria-pressed={!isAbsent}
                  aria-label={`${s.full_name} present`}
                  onClick={() => mark(s.roll_no, false)}
                  disabled={locked}
                >
                  P
                </button>
                <button
                  type="button"
                  className="pa-a"
                  aria-pressed={isAbsent}
                  aria-label={`${s.full_name} absent`}
                  onClick={() => mark(s.roll_no, true)}
                  disabled={locked}
                >
                  A
                </button>
              </span>
            </li>
          )
        })}
      </ol>

      <div className="savebar">
        <span className="reg-tally">
          <span>
            <strong>{present}</strong> present, <strong>{absent.size}</strong> absent
            <span className="muted small"> of {plural(students.length, 'student')}</span>
          </span>
          <span className="reg-ratio" style={{ '--share': share } as CSSProperties} aria-hidden="true" />
        </span>
        <span className="savebar-actions">
          {note && (
            <span className={`inline-${note.tone}`} role={note.tone === 'error' ? 'alert' : 'status'}>
              {note.text}
            </span>
          )}
          <button type="button" className="primary" onClick={save} disabled={locked || unchanged}>
            {busy ? 'Saving…' : target ? 'Save correction' : 'Record attendance'}
          </button>
        </span>
      </div>
    </section>
  )
}
