import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, api } from './api'
import { Message } from './Message'
import type { ChatOut, ConfirmCard, Me, MessageOut, Session, Turn } from './types'

let nextId = 1
const uid = () => `t${nextId++}`

function fromStored(m: MessageOut): Turn | null {
  if (m.role !== 'user' && m.role !== 'assistant') return null
  return { id: `m${m.id}`, role: m.role, text: m.content ?? '', citations: m.citations ?? [], cards: m.cards ?? [] }
}

export function Chat({ session, me, onSignOut }: { session: Session; me: Me | null; onSignOut: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [turns])

  function patch(id: string, change: Partial<Turn>) {
    setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, ...change } : t)))
  }

  async function send(text: string) {
    const message = text.trim()
    if (!message || busy) return
    setBusy(true)
    setDraft('')
    const userId = uid()
    const answerId = uid()
    setTurns((ts) => [
      ...ts,
      { id: userId, role: 'user', text: message, citations: [], cards: [] },
      { id: answerId, role: 'assistant', text: '', citations: [], cards: [], pending: true },
    ])
    try {
      const out: ChatOut = await api.chat(message, conversationId)
      setConversationId(out.conversation_id)
      patch(answerId, {
        text: out.text,
        citations: out.citations,
        cards: out.cards,
        pending: false,
        queuedSeconds: out.queued_seconds || undefined,
      })
    } catch (err) {
      patch(answerId, { pending: false, error: describe(err) })
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  async function confirm(turnId: string, card: ConfirmCard) {
    try {
      const out = await api.confirm(card.token, conversationId)
      patch(turnId, { outcome: { text: out.text, ok: true } })
    } catch (err) {
      patch(turnId, { outcome: { text: describe(err), ok: false } })
    }
  }

  function cancel(turnId: string) {
    patch(turnId, { outcome: { text: 'Cancelled — nothing was changed.', ok: true } })
  }

  async function openConversation(id: number) {
    const messages = await api.messages(id)
    setConversationId(id)
    setTurns(messages.map(fromStored).filter((t): t is Turn => t !== null))
  }
  void openConversation // used by the conversation rail (next part)

  function newConversation() {
    setConversationId(null)
    setTurns([])
    inputRef.current?.focus()
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    void send(draft)
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send(draft)
    }
  }

  const who = describeCaller(session, me)

  return (
    <div className="app">
      <header className="topbar">
        <span className="wordmark">UniAssist</span>
        <span className="caller">{who}</span>
        <span className="topbar-actions">
          <button type="button" className="linklike" onClick={newConversation}>
            New conversation
          </button>
          <button type="button" className="linklike" onClick={onSignOut}>
            Sign out
          </button>
        </span>
      </header>

      <main className="transcript" aria-live="polite">
        {turns.length === 0 ? (
          <div className="empty">
            <p>Ask a question about your own records or about the University's regulations.</p>
          </div>
        ) : (
          turns.map((t) => (
            <Message key={t.id} turn={t} onConfirm={(card) => confirm(t.id, card)} onCancel={() => cancel(t.id)} />
          ))
        )}
        <div ref={endRef} />
      </main>

      <form className="composer" onSubmit={submit}>
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          placeholder={busy ? 'Waiting for the answer…' : 'Ask UniAssist'}
          rows={1}
          disabled={busy}
          autoFocus
          aria-label="Your question"
        />
        <button type="submit" className="primary" disabled={busy || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}

function describeCaller(session: Session, me: Me | null): string {
  const role = session.role[0].toUpperCase() + session.role.slice(1)
  const p = me?.profile as Record<string, unknown> | null | undefined
  const name = p && typeof p.name === 'string' ? p.name : null
  const ref = session.subjectRef.split(':').pop()
  const hod = me?.is_hod ? ', HOD' : ''
  return name ? `${name} (${role}${hod})` : `${role}${hod} ${ref ?? ''}`.trim()
}

function describe(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 429) {
      const wait = err.retryAfter ? ` Try again in about ${err.retryAfter} seconds.` : ' Try again shortly.'
      return `The assistant is rate-limited right now.${wait}`
    }
    if (err.status === 401) return 'Your session has expired. Sign in again.'
    if (err.status === 503) return 'The language model is not configured on the server (no API key).'
    if (err.status === 410) return 'This confirmation has expired. Ask again to get a fresh one.'
    if (err.status === 409) return err.message
    return `${err.message} (${err.status})`
  }
  return 'The server could not be reached.'
}
