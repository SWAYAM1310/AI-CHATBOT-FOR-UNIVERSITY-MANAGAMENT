import { useState, type KeyboardEvent } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../../api'
import { plural } from '../format'
import { Empty, Loading, Notice } from '../ui'
import { describeError, useLoad } from '../useLoad'
import type { CourseContext } from './CourseLayout'

/** Why a row cannot be saved, or null. A blank score is fine for someone who never had one. */
function problem(score: string, absent: boolean, max: number | null, hadEntry: boolean): string | null {
  if (absent) return null
  if (score.trim() === '') return hadEntry ? 'Enter a score or mark absent' : null
  const n = Number(score)
  if (!Number.isFinite(n)) return 'Not a number'
  if (n < 0) return 'Cannot be below 0'
  if (max !== null && n > max) return `Cannot be above ${max}`
  if (!Number.isInteger(n * 2)) return 'Use whole or half marks, like 7 or 7.5'
  return null
}

export function Marks() {
  const { offering, students } = useOutletContext<CourseContext>()
  const id = offering.offering_id

  const list = useLoad(() => api.assessments(id), `assessments-${id}`)
  const [chosen, setChosen] = useState<number | null>(null)
  const items = list.data?.assessments ?? []
  // open on the first assessment that is not fully entered: that is the one being worked on
  const fallback = items.find((a) => a.graded < students.length) ?? items[items.length - 1]
  const assessmentId = chosen ?? fallback?.assessment_id ?? null

  const sheet = useLoad(() => api.marksSheet(assessmentId as number), assessmentId === null ? null : `marks-${assessmentId}`)
  const [scores, setScores] = useState<Record<string, string>>({})
  const [absent, setAbsent] = useState<Set<string>>(new Set())
  const [seeded, setSeeded] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ tone: 'error' | 'success'; text: string } | null>(null)

  const seedKey = sheet.data && !sheet.loading ? `${assessmentId}|${sheet.version}` : null
  if (sheet.data && seedKey !== null && seedKey !== seeded) {
    setSeeded(seedKey)
    setScores(Object.fromEntries(sheet.data.students.map((s) => [s.roll_no, s.score === null ? '' : String(s.score)])))
    setAbsent(new Set(sheet.data.students.filter((s) => s.is_absent).map((s) => s.roll_no)))
  }

  const max = sheet.data?.assessment.max_marks ?? null
  const rows = (sheet.data?.students ?? []).map((s) => {
    const text = scores[s.roll_no] ?? ''
    const isAbsent = absent.has(s.roll_no)
    return { ...s, text, isAbsent, error: problem(text, isAbsent, max, s.score !== null || s.is_absent) }
  })

  // what a save would send: only rows that differ from what is stored
  const marks: Record<string, number> = {}
  const absentees: string[] = []
  for (const r of rows) {
    if (r.error) continue
    if (r.isAbsent) {
      if (!r.is_absent) absentees.push(r.roll_no)
    } else if (r.text.trim() !== '' && (r.is_absent || r.score !== Number(r.text))) {
      marks[r.roll_no] = Number(r.text)
    }
  }
  const changes = Object.keys(marks).length + absentees.length
  const invalid = rows.filter((r) => r.error).length

  const entered = rows.filter((r) => !r.isAbsent && r.text.trim() !== '' && !r.error)
  const average = entered.length ? entered.reduce((sum, r) => sum + Number(r.text), 0) / entered.length : null

  function setScore(roll: string, text: string) {
    setNote(null)
    setScores((prev) => ({ ...prev, [roll]: text }))
  }

  function toggleAbsent(roll: string, original: number | null) {
    setNote(null)
    const wasAbsent = absent.has(roll)
    setAbsent((prev) => {
      const next = new Set(prev)
      if (wasAbsent) next.delete(roll)
      else next.add(roll)
      return next
    })
    // un-marking an absentee brings back the score they had, if any
    if (wasAbsent) setScores((s) => ({ ...s, [roll]: s[roll] || (original === null ? '' : String(original)) }))
  }

  // Enter moves down the column, the way a mark sheet is filled in
  function onEnter(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter') return
    e.preventDefault()
    const next = e.currentTarget.closest('tr')?.nextElementSibling?.querySelector<HTMLInputElement>('input[type="number"]:not(:disabled)')
    next?.focus()
    next?.select()
  }

  async function save() {
    if (assessmentId === null) return
    setBusy(true)
    setNote(null)
    try {
      const out = await api.saveMarks(assessmentId, { marks, absent_roll_nos: absentees })
      setNote({ tone: 'success', text: out.message })
      sheet.reload()
      list.reload()
    } catch (err) {
      setNote({ tone: 'error', text: describeError(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      {list.error && <Notice tone="error">{list.error}</Notice>}
      {!list.data && !list.error && <Loading what="assessments" />}
      {list.data && items.length === 0 && <Empty>No assessments are set up for this course yet.</Empty>}

      {items.length > 0 && assessmentId !== null && (
        <>
          <div className="toolbar">
            <label className="field-inline">
              <span>Assessment</span>
              <select
                value={assessmentId}
                onChange={(e) => {
                  setChosen(Number(e.target.value))
                  setNote(null)
                }}
              >
                {items.map((a) => (
                  <option key={a.assessment_id} value={a.assessment_id}>
                    {a.title || a.type}, out of {a.max_marks ?? '?'} ({a.graded} of {students.length} entered)
                  </option>
                ))}
              </select>
            </label>
          </div>

          {sheet.error && <Notice tone="error">{sheet.error}</Notice>}
          {!sheet.data && !sheet.error && <Loading what="the mark sheet" />}

          {sheet.data && (
            <>
              {sheet.data.assessment.auto_graded && (
                <Notice tone="info">
                  Nobody entered these marks by the due date, so they were filled in automatically: each student got a
                  score within their own range of marks this semester. Change any score and save to replace it.
                </Notice>
              )}
              <div className="table-wrap">
                <table className="data marks">
                  <thead>
                    <tr>
                      <th>Roll no.</th>
                      <th>Name</th>
                      <th className="num">Score{max !== null ? ` (out of ${max})` : ''}</th>
                      <th>Absent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.roll_no} className={r.isAbsent ? 'absent' : undefined}>
                        <td className="mono">{r.roll_no}</td>
                        <td>{r.full_name}</td>
                        <td className="num">
                          <input
                            type="number"
                            inputMode="decimal"
                            step="0.5"
                            min={0}
                            max={max ?? undefined}
                            value={r.isAbsent ? '' : r.text}
                            disabled={r.isAbsent || busy}
                            aria-label={`Score for ${r.full_name}`}
                            aria-invalid={r.error ? true : undefined}
                            onChange={(e) => setScore(r.roll_no, e.target.value)}
                            onKeyDown={onEnter}
                          />
                          {r.error && <span className="cell-error">{r.error}</span>}
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            checked={r.isAbsent}
                            disabled={busy}
                            aria-label={`${r.full_name} was absent`}
                            onChange={() => toggleAbsent(r.roll_no, r.score)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="savebar">
                <span>
                  <strong>{entered.length}</strong> of {plural(rows.length, 'student')} scored
                  {absent.size > 0 && <span className="muted small">, {absent.size} absent</span>}
                  {average !== null && <span className="muted small">, average {average.toFixed(1)}</span>}
                </span>
                <span className="savebar-actions">
                  {note && <span className={`inline-${note.tone}`}>{note.text}</span>}
                  {invalid > 0 && <span className="inline-error">Fix {plural(invalid, 'row')} to save</span>}
                  <button type="button" className="primary" onClick={save} disabled={busy || invalid > 0 || changes === 0}>
                    {busy ? 'Saving…' : changes === 0 ? 'Save marks' : `Save ${plural(changes, 'change')}`}
                  </button>
                </span>
              </div>
            </>
          )}
        </>
      )}
    </section>
  )
}
