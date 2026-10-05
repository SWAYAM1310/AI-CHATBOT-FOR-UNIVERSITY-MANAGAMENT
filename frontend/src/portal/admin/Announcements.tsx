import { useState, type FormEvent } from 'react'
import { api } from '../../api'
import type { AdminNotice, NoticeAudience, NoticeDraft, NoticePreview } from '../../types'
import { formatDate, plural } from '../format'
import { PageHeader } from '../PageHeader'
import { Empty, Loading, Notice } from '../ui'
import { describeError, useLoad } from '../useLoad'
import { deliverySummary, noticeAudience } from './notices'

// sending happens in a background task after Publish returns, so the list is re-read until it settles
const SENDING_POLL_MS = 3000
const TITLE_MAX = 120
const BODY_MAX = 2000

const AUDIENCES: { value: NoticeAudience; label: string }[] = [
  { value: 'all', label: 'Everyone' },
  { value: 'student', label: 'Students' },
  { value: 'faculty', label: 'Faculty' },
]

interface Form {
  title: string
  body: string
  audience: NoticeAudience
  dept: string
  semester: string
}

const EMPTY: Form = { title: '', body: '', audience: 'all', dept: '', semester: '' }

function toDraft(f: Form): NoticeDraft {
  return {
    title: f.title.trim(),
    body: f.body.trim(),
    audience: f.audience,
    dept: f.dept || undefined,
    semester: f.semester ? Number(f.semester) : undefined,
  }
}

function Deliveries({ id, sending }: { id: number; sending: boolean }) {
  const { data, error } = useLoad(() => api.deliveries(id), `deliveries-${id}`, false, sending ? SENDING_POLL_MS : 0)
  if (error) return <Notice tone="error">{error}</Notice>
  if (!data) return <Loading what="deliveries" />
  if (data.emails.length === 0) return <Empty>No emails were sent for this notice.</Empty>
  return (
    <div className="table-wrap deliveries stack-table">
      <table className="data">
        <thead>
          <tr>
            <th>Recipient</th>
            <th>Status</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {data.emails.map((e) => (
            <tr key={e.intended_to}>
              <td className="mono small">{e.intended_to}</td>
              <td data-label="Status">
                <span className={`badge ${e.status}`}>{e.status}</span>
              </td>
              <td className="small muted" data-label="Detail">{e.error ?? (e.to !== e.intended_to ? `redirected to ${e.to}` : e.sent_at ? `sent ${formatDate(e.sent_at)}` : '')}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.delivery.total > data.emails.length && (
        <p className="small muted">
          Showing the first {data.emails.length} of {data.delivery.total}.
        </p>
      )}
    </div>
  )
}

function NoticeRow({ n }: { n: AdminNotice }) {
  const [open, setOpen] = useState(false)
  const d = n.delivery
  const sending = d.queued > 0
  return (
    <li className="notice-row">
      <div className="notice-head">
        <span>
          <strong>{n.title}</strong> <span className="muted small">{formatDate(n.posted_at)}</span>
          <span className="muted small block-line">{noticeAudience(n)}</span>
        </span>
        {d.total > 0 && (
          <button type="button" className="small-btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? 'Hide recipients' : 'Recipients'}
          </button>
        )}
      </div>
      {n.body && <span className="muted small clamp">{n.body}</span>}
      {d.total > 0 && (
        <div className="delivery" role="img" aria-label={deliverySummary(d)}>
          <span className="delivery-sent" style={{ flexGrow: d.sent }} />
          <span className="delivery-queued" style={{ flexGrow: d.queued }} />
          <span className="delivery-held" style={{ flexGrow: d.held + d.suppressed }} />
          <span className="delivery-failed" style={{ flexGrow: d.failed }} />
        </div>
      )}
      <span className={d.failed ? 'small low-note' : 'small'} aria-live={sending ? 'polite' : undefined}>
        {deliverySummary(d)}
      </span>
      {open && <Deliveries id={n.announcement_id} sending={sending} />}
    </li>
  )
}

export function Announcements() {
  const departments = useLoad(() => api.adminDashboard(), 'admin-dashboard')
  const [poll, setPoll] = useState(0)
  const notices = useLoad(() => api.notices(), 'admin-notices', true, poll)
  const wantPoll = notices.data?.some((n) => n.delivery.queued > 0) ? SENDING_POLL_MS : 0
  if (wantPoll !== poll) setPoll(wantPoll)

  const [form, setForm] = useState<Form>(EMPTY)
  const [preview, setPreview] = useState<NoticePreview | null>(null)
  const [subject, setSubject] = useState('')
  const [emailBody, setEmailBody] = useState('')
  const [busy, setBusy] = useState<'preview' | 'publish' | null>(null)
  const [note, setNote] = useState<{ tone: 'error' | 'success'; text: string } | null>(null)

  // any change to the notice makes the preview stale: who it reaches and the drafted email both depend on it
  function edit(changes: Partial<Form>) {
    setForm((f) => ({ ...f, ...changes }))
    setPreview(null)
    setNote(null)
  }

  const ready = form.title.trim() !== '' && form.body.trim() !== ''

  async function runPreview(e: FormEvent) {
    e.preventDefault()
    if (!ready) return
    setBusy('preview')
    setNote(null)
    try {
      const out = await api.previewNotice(toDraft(form))
      setPreview(out)
      setSubject(out.email?.subject ?? '')
      setEmailBody(out.email?.body ?? '')
    } catch (err) {
      setNote({ tone: 'error', text: describeError(err) })
    } finally {
      setBusy(null)
    }
  }

  async function publish() {
    if (!preview) return
    setBusy('publish')
    setNote(null)
    try {
      // the reviewed email is sent as shown; without it the server would draft a fresh one
      const draft = preview.emailing ? { ...toDraft(form), email_subject: subject.trim(), email_body: emailBody.trim() } : toDraft(form)
      const out = await api.publishNotice(draft)
      let text = `Published "${draft.title}" to ${plural(out.recipients, 'recipient')}.`
      if (out.emails_queued) text += ` Emailing ${out.emails_queued}.`
      if (out.emails_held) text += ` ${out.emails_held} held by the demo cap.`
      setNote({ tone: 'success', text })
      setForm(EMPTY)
      setPreview(null)
      notices.reload()
    } catch (err) {
      setNote({ tone: 'error', text: describeError(err) })
    } finally {
      setBusy(null)
    }
  }

  const p = preview?.preview
  const emailIncomplete = preview?.emailing && (subject.trim() === '' || emailBody.trim() === '')

  return (
    <div className="page">
      <PageHeader title="Announcements" lede="Publish a notice to the portal and email it to everyone it is for. You see exactly who it reaches before it goes out." />

      <section className="block" aria-labelledby="new-h">
        <h2 id="new-h">New announcement</h2>
        <form className="form" onSubmit={runPreview}>
          <label className="field">
            <span>Title</span>
            <input value={form.title} maxLength={TITLE_MAX} onChange={(e) => edit({ title: e.target.value })} disabled={busy !== null} required />
          </label>
          <label className="field field-gap">
            <span>Message</span>
            <textarea rows={5} value={form.body} maxLength={BODY_MAX} onChange={(e) => edit({ body: e.target.value })} disabled={busy !== null} required />
            <span className="muted small counter">
              {form.body.length} / {BODY_MAX}
            </span>
          </label>

          <div className="form-grid field-gap">
            <fieldset className="field segmented">
              <legend>Who is it for</legend>
              <div>
                {AUDIENCES.map((a) => (
                  <label key={a.value} className={form.audience === a.value ? 'chip active' : 'chip'}>
                    <input
                      type="radio"
                      name="audience"
                      className="sr-only"
                      value={a.value}
                      checked={form.audience === a.value}
                      onChange={() => edit({ audience: a.value })}
                      disabled={busy !== null}
                    />
                    {a.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="field">
              <span>Department</span>
              <select value={form.dept} onChange={(e) => edit({ dept: e.target.value })} disabled={busy !== null}>
                <option value="">Whole university</option>
                {departments.data?.departments.map((d) => (
                  <option key={d.dept} value={d.dept}>
                    {d.name} ({d.dept})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Semester</span>
              <select value={form.semester} onChange={(e) => edit({ semester: e.target.value })} disabled={busy !== null}>
                <option value="">Every semester</option>
                {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
                  <option key={s} value={s}>
                    Semester {s}
                  </option>
                ))}
              </select>
              {form.semester && form.audience !== 'student' && <span className="muted small">Faculty: those teaching a semester {form.semester} course this term.</span>}
            </label>
          </div>

          {!preview && (
            <div className="form-actions">
              <button type="submit" className="primary" disabled={!ready || busy !== null}>
                {busy === 'preview' ? 'Preparing preview…' : 'Preview'}
              </button>
              <span className="muted small">Nothing is published or sent until you press Publish.</span>
            </div>
          )}
        </form>

        {preview && p && (
          <section className="preview" aria-labelledby="preview-h">
            <h3 id="preview-h">Before you publish</h3>
            <p className="preview-reach">
              Reaches <strong>{plural(p.recipients_students + p.recipients_faculty, 'person', 'people')}</strong>:{' '}
              {[p.recipients_students && plural(p.recipients_students, 'student'), p.recipients_faculty && plural(p.recipients_faculty, 'faculty member')]
                .filter(Boolean)
                .join(' and ')}
              .
            </p>
            {preview.emailing && p.emails_held > 0 && (
              <p className="attention-line">
                Demo cap is on: only {plural(p.emails_to_send, 'email')} will really be sent; the other {p.emails_held} are recorded as held. Everyone still sees the
                notice in the portal.
              </p>
            )}
            {preview.emailing ? (
              <div className="form">
                <p className="muted small">This email goes to every recipient. You can edit it before publishing.</p>
                <label className="field">
                  <span>Email subject</span>
                  <input value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} disabled={busy !== null} />
                </label>
                <label className="field field-gap">
                  <span>Email body</span>
                  <textarea rows={10} value={emailBody} maxLength={5000} onChange={(e) => setEmailBody(e.target.value)} disabled={busy !== null} />
                </label>
              </div>
            ) : (
              <p className="muted">Email is switched off on this server, so the notice appears in the portal only.</p>
            )}
            <div className="form-actions">
              <button type="button" className="primary" onClick={publish} disabled={busy !== null || emailIncomplete === true}>
                {busy === 'publish' ? 'Publishing…' : 'Publish'}
              </button>
              <button type="button" onClick={() => setPreview(null)} disabled={busy !== null}>
                Back to editing
              </button>
              {emailIncomplete && <span className="inline-error">The email needs a subject and a body.</span>}
            </div>
          </section>
        )}
        {note && <Notice tone={note.tone}>{note.text}</Notice>}
      </section>

      <section className="block" aria-labelledby="past-h">
        <h2 id="past-h">Published</h2>
        {notices.error && <Notice tone="error">{notices.error}</Notice>}
        {!notices.data && !notices.error && <Loading what="announcements" />}
        {notices.data && notices.data.length === 0 && <Empty>Nothing has been announced yet.</Empty>}
        {notices.data && notices.data.length > 0 && (
          <ul className="plain-list">
            {notices.data.map((n) => (
              <NoticeRow key={n.announcement_id} n={n} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
