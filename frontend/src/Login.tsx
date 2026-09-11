import { useState, type FormEvent } from 'react'
import { ApiError, api } from './api'
import type { Session } from './types'

// The synthetic dataset gives every account the same password; the three
// sample sign-ins below are the demo personas (one per role).
const SAMPLES: { label: string; email: string }[] = [
  { label: 'Student 25BCP017', email: '25bcp017@sot.pdpu.ac.in' },
  { label: 'Faculty (HOD, CP)', email: 'milan.vyas@sot.pdpu.ac.in' },
  { label: 'Admin', email: 'tanvi.joshi@sot.pdpu.ac.in' },
]

export function Login({ onSignedIn }: { onSignedIn: (s: Session) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const out = await api.login(email.trim(), password)
      onSignedIn({ token: out.access_token, role: out.role, subjectRef: out.subject_ref })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setError('That email and password do not match an account.')
      else if (err instanceof ApiError) setError(`Sign-in failed (${err.status}): ${err.message}`)
      else setError('The server could not be reached. Is the backend running on port 8000?')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <section className="login-card">
        <h1 className="wordmark">UniAssist</h1>
        <p className="login-lede">
          Ask about your attendance, marks, fees and timetable, or about the University's regulations.
          Answers cite the regulation they come from.
        </p>
        <form onSubmit={submit} className="login-form">
          <label>
            Email
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <div className="login-samples">
          <p>Demo accounts (password <code>uniassist</code>):</p>
          <ul>
            {SAMPLES.map((s) => (
              <li key={s.email}>
                <button
                  type="button"
                  className="linklike"
                  onClick={() => {
                    setEmail(s.email)
                    setPassword('uniassist')
                  }}
                >
                  {s.label}
                </button>
                <span className="muted"> {s.email}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  )
}
