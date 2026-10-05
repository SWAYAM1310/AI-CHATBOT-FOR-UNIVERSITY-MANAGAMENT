import { useId, useRef, useState, type FormEvent } from 'react'
import { api } from '../api'
import type { ProfileOut, Role } from '../types'
import { Avatar } from './Avatar'
import { usePortal } from './context'
import { formatDate } from './format'
import { PageHeader } from './PageHeader'
import { Loading, Notice } from './ui'
import { describeError, useLoad } from './useLoad'

const MAX_PHOTO_BYTES = 2 * 1024 * 1024 // the server's limit; checked here so the person is told before waiting

// What each role sees, in reading order. Anything the server sends that is not listed is not shown.
const DETAILS: Record<Role, [key: string, label: string][]> = {
  student: [
    ['roll_no', 'Roll number'],
    ['university_email', 'University email'],
    ['department', 'Department'],
    ['hod', 'Head of department'],
    ['batch', 'Batch'],
    ['semester', 'Semester'],
    ['division', 'Division'],
    ['lab_group', 'Lab group'],
    ['cgpa', 'CGPA'],
    ['is_hosteller', 'Hosteller'],
    ['admission_date', 'Admission date'],
    ['date_of_birth', 'Date of birth'],
    ['gender', 'Gender'],
    ['guardian_name', 'Guardian'],
    ['guardian_phone', 'Guardian phone'],
    ['tenth_percentage', '10th percentage'],
    ['twelfth_percentage', '12th percentage'],
  ],
  faculty: [
    ['employee_id', 'Employee ID'],
    ['university_email', 'University email'],
    ['department', 'Department'],
    ['designation', 'Designation'],
    ['is_hod', 'Head of department'],
    ['date_of_joining', 'Joined'],
    ['qualification', 'Qualification'],
    ['specialization', 'Specialization'],
    ['date_of_birth', 'Date of birth'],
    ['gender', 'Gender'],
  ],
  admin: [
    ['employee_id', 'Employee ID'],
    ['university_email', 'University email'],
    ['designation', 'Designation'],
    ['date_of_joining', 'Joined'],
    ['date_of_birth', 'Date of birth'],
    ['gender', 'Gender'],
  ],
}

const EDITABLE_LABELS: Record<string, string> = {
  phone: 'Phone',
  personal_email: 'Personal email',
  address_city: 'City',
  address_state: 'State',
  office_room: 'Office room',
}

type Note = { tone: 'error' | 'success'; text: string } | null

function show(key: string, value: ProfileOut['profile'][string]) {
  if (value === null || value === '') return <span className="muted">Not provided</span>
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (key.includes('date') || key.endsWith('_on')) return formatDate(String(value))
  if (key.endsWith('percentage')) return `${value}%`
  return String(value)
}

function PhotoControls() {
  const { me, photoVersion, refreshMe } = usePortal()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<Note>(null)

  async function run(work: () => Promise<void>, done: string) {
    setBusy(true)
    setNote(null)
    try {
      await work()
      refreshMe()
      setNote({ tone: 'success', text: done })
    } catch (err) {
      setNote({ tone: 'error', text: describeError(err) })
    } finally {
      setBusy(false)
    }
  }

  function picked(file: File | undefined) {
    if (input.current) input.current.value = '' // choosing the same file again must still fire
    if (!file) return
    if (file.size > MAX_PHOTO_BYTES) {
      setNote({ tone: 'error', text: 'That photo is larger than 2 MB. Choose a smaller one.' })
      return
    }
    void run(() => api.uploadPhoto(file), 'Photo updated.')
  }

  return (
    <div className="photo-controls">
      <Avatar userId={me?.user_id} name={me?.full_name} hasPhoto={me?.has_photo} version={photoVersion} size={88} />
      <div>
        <p className="profile-name">{me?.full_name}</p>
        <div className="photo-buttons">
          <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => picked(e.target.files?.[0])} />
          <button type="button" onClick={() => input.current?.click()} disabled={busy}>
            {me?.has_photo ? 'Change photo' : 'Upload photo'}
          </button>
          {me?.has_photo && (
            <button type="button" onClick={() => void run(() => api.deletePhoto(), 'Photo removed.')} disabled={busy}>
              Remove photo
            </button>
          )}
        </div>
        <p className="small muted">A JPEG, PNG or WebP image up to 2 MB. It is cropped to a square.</p>
        {note && <p className={`inline-${note.tone} small`}>{note.text}</p>}
      </div>
    </div>
  )
}

function ContactForm({ data, reload, version }: { data: ProfileOut; reload: () => void; version: number }) {
  const [form, setForm] = useState<Record<string, string>>({})
  const [seeded, setSeeded] = useState(-1)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<Note>(null)

  if (seeded !== version) {
    setSeeded(version)
    setForm(Object.fromEntries(data.editable.map((k) => [k, String(data.profile[k] ?? '')])))
  }

  const changed = Object.fromEntries(data.editable.filter((k) => (form[k] ?? '') !== String(data.profile[k] ?? '')).map((k) => [k, form[k] ?? '']))
  const dirty = Object.keys(changed).length > 0

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setNote(null)
    try {
      await api.updateProfile(changed)
      reload()
      setNote({ tone: 'success', text: 'Contact details saved.' })
    } catch (err) {
      setNote({ tone: 'error', text: describeError(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={save} className="form">
      <div className="form-grid">
        {data.editable.map((k) => (
          <label key={k} className="field">
            <span>{EDITABLE_LABELS[k] ?? k}</span>
            <input
              value={form[k] ?? ''}
              type={k === 'personal_email' ? 'email' : k === 'phone' ? 'tel' : 'text'}
              autoComplete={k === 'personal_email' ? 'email' : k === 'phone' ? 'tel' : 'off'}
              onChange={(e) => {
                setNote(null)
                setForm((f) => ({ ...f, [k]: e.target.value }))
              }}
            />
          </label>
        ))}
      </div>
      <div className="form-actions">
        <button type="submit" className="primary" disabled={busy || !dirty}>
          {busy ? 'Saving…' : 'Save contact details'}
        </button>
        {note && <span className={`inline-${note.tone}`}>{note.text}</span>}
      </div>
    </form>
  )
}

/** A labelled password box. The hint is the field's description, not part of its name. */
function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  hint,
  problem,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  autoComplete: string
  hint?: string
  problem?: boolean
}) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="password"
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
        aria-invalid={problem || undefined}
        aria-describedby={hint ? `${id}-hint` : undefined}
      />
      {hint && (
        <small id={`${id}-hint`} className={problem ? 'inline-error' : 'muted'}>
          {hint}
        </small>
      )}
    </div>
  )
}

function PasswordForm() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<Note>(null)

  const tooShort = next.length > 0 && next.length < 8
  const mismatch = again.length > 0 && again !== next

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setNote(null)
    try {
      await api.changePassword(current, next)
      setCurrent('')
      setNext('')
      setAgain('')
      setNote({ tone: 'success', text: 'Password changed. Use it the next time you sign in.' })
    } catch (err) {
      setNote({ tone: 'error', text: describeError(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={save} className="form">
      <div className="form-grid">
        <PasswordField label="Current password" autoComplete="current-password" value={current} onChange={setCurrent} />
        <PasswordField
          label="New password"
          autoComplete="new-password"
          value={next}
          onChange={setNext}
          hint="At least 8 characters."
          problem={tooShort}
        />
        <PasswordField
          label="New password again"
          autoComplete="new-password"
          value={again}
          onChange={setAgain}
          hint={mismatch ? 'The two passwords do not match.' : undefined}
          problem={mismatch}
        />
      </div>
      <div className="form-actions">
        <button type="submit" className="primary" disabled={busy || !current || next.length < 8 || next !== again}>
          {busy ? 'Changing…' : 'Change password'}
        </button>
        {note && <span className={`inline-${note.tone}`}>{note.text}</span>}
      </div>
    </form>
  )
}

export function Profile() {
  const { session } = usePortal()
  const { data, error, reload, version } = useLoad(() => api.profile(), 'profile')

  return (
    <div className="page">
      <PageHeader title="Profile" lede="Your details on record. You can change your contact details, password and photo." />
      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <Loading what="your profile" />}

      <section className="block profile-head" aria-label="Photo">
        <PhotoControls />
      </section>

      {data && (
        <>
          <section className="block" aria-labelledby="contact-h">
            <h2 id="contact-h">Contact details</h2>
            <ContactForm data={data} reload={reload} version={version} />
          </section>

          <section className="block" aria-labelledby="details-h">
            <h2 id="details-h">Official details</h2>
            <p className="small muted">These come from the university's records. To correct one, contact the administration office.</p>
            <dl className="facts">
              {DETAILS[session.role]
                .filter(([key]) => key in data.profile)
                .map(([key, label]) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{show(key, data.profile[key])}</dd>
                  </div>
                ))}
            </dl>
          </section>
        </>
      )}

      <section className="block" aria-labelledby="pw-h">
        <h2 id="pw-h">Password</h2>
        <PasswordForm />
      </section>
    </div>
  )
}
