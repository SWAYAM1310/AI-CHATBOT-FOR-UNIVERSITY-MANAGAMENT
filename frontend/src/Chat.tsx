import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, api } from './api'
import type { StreamHandlers } from './api'
import { Message } from './Message'
import { Rail, SUGGESTIONS } from './Rail'
import type { ChatOut, ConfirmCard, ConversationOut, Me, MessageOut, Session, Turn } from './types'

let nextId = 1
const uid = () => `t${nextId++}`

function fromStored(m: MessageOut): Turn | null {
  if (m.role !== 'user' && m.role !== 'assistant') return null
  const trace =
    m.role === 'assistant' && m.tool_runs?.length
      ? { path: 'stored', intent: '', tool_runs: m.tool_runs, usage: { tokens_in: m.tokens_in ?? 0, tokens_out: m.tokens_out ?? 0 } }
      : undefined
  return { id: `m${m.id}`, role: m.role, text: m.content ?? '', citations: m.citations ?? [], cards: m.cards ?? [], trace }
}

export function Chat({ session, me, onSignOut }: { session: Session; me: Me | null; onSignOut: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [conversations, setConversations] = useState<ConversationOut[]>([])
  const [railOpen, setRailOpen] = useState<boolean>(initialRailOpen)
  const [showTrace, setShowTrace] = useState<boolean>(() => readFlag(TRACE_KEY))
  const endRef = useRef<HTMLDivElement>(null)
  const transcriptRef = useRef<HTMLElement>(null)
  const nearBottomRef = useRef(true) // updated by onScroll; read before each auto-scroll
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    // don't yank a reader back down mid-stream if they scrolled up to reread something
    if (nearBottomRef.current) endRef.current?.scrollIntoView({ block: 'end' })
  }, [turns])

  const NEAR_BOTTOM_PX = 80

  function onTranscriptScroll() {
    const el = transcriptRef.current
    if (!el) return
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX
  }

  const refreshConversations = useCallback(() => {
    api
      .conversations()
      .then(setConversations)
      .catch(() => undefined) // the rail is a convenience; a failed list is not an error worth a banner
  }, [])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  // Resume the last-open conversation after a reload — otherwise a refresh
  // loses the transcript even though the session itself survives it.
  useEffect(() => {
    const stored = loadActiveConversation(session.subjectRef)
    if (stored != null) void openConversation(stored)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    saveActiveConversation(session.subjectRef, conversationId)
  }, [session.subjectRef, conversationId])

  useEffect(() => {
    writeFlag(RAIL_KEY, railOpen)
  }, [railOpen])

  function patch(id: string, change: Partial<Turn> | ((t: Turn) => Partial<Turn>)) {
    setTurns((ts) =>
      ts.map((t) => (t.id === id ? { ...t, ...(typeof change === 'function' ? change(t) : change) } : t)),
    )
  }

  async function send(text: string) {
    const message = text.trim()
    if (!message || busy) return
    setBusy(true)
    setDraft('')
    nearBottomRef.current = true // your own question always scrolls into view
    const userId = uid()
    const answerId = uid()
    setTurns((ts) => [
      ...ts,
      { id: userId, role: 'user', text: message, citations: [], cards: [] },
      { id: answerId, role: 'assistant', text: '', citations: [], cards: [], pending: true, liveTools: [] },
    ])

    // Deltas arrive many-per-second; batching them into one paint per frame
    // keeps the UI smooth instead of re-rendering the transcript on every token.
    let textBuf = ''
    let rafId = 0
    const flush = () => {
      rafId = 0
      patch(answerId, { text: textBuf, pending: false, streaming: true })
    }
    const queueFlush = () => {
      if (!rafId) rafId = requestAnimationFrame(flush)
    }

    try {
      const out: ChatOut = await chatStreamWithOneRetry(
        message,
        conversationId,
        {
          onStatus: (stage) => patch(answerId, { stage }),
          onTool: (tool) => patch(answerId, (t) => ({ liveTools: [...(t.liveTools ?? []), tool] })),
          onCards: (cards) => patch(answerId, (t) => ({ cards: [...t.cards, ...cards] })),
          onDelta: (chunk) => {
            textBuf += chunk
            queueFlush()
          },
        },
        (seconds) => patch(answerId, { queuedSeconds: seconds }),
      )
      if (rafId) {
        cancelAnimationFrame(rafId)
        rafId = 0
      }
      if (out.conversation_id !== conversationId) {
        setConversationId(out.conversation_id)
        refreshConversations() // a new conversation was opened by this turn
      }
      patch(answerId, {
        text: out.text,
        citations: out.citations,
        cards: out.cards,
        pending: false,
        streaming: false,
        stage: undefined,
        liveTools: undefined,
        queuedSeconds: out.queued_seconds || undefined,
        trace: out.trace,
      })
    } catch (err) {
      if (rafId) cancelAnimationFrame(rafId)
      patch(answerId, { pending: false, streaming: false, error: describe(err) })
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
    if (busy) return
    try {
      const messages = await api.messages(id)
      setConversationId(id)
      setTurns(messages.map(fromStored).filter((t): t is Turn => t !== null))
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // gone (deleted elsewhere, or a stale resume-on-reload pointer): quietly start fresh
        saveActiveConversation(session.subjectRef, null)
        setConversationId(null)
        setTurns([])
        return
      }
      setTurns([{ id: uid(), role: 'assistant', text: '', citations: [], cards: [], error: describe(err) }])
    }
  }

  function newConversation() {
    setConversationId(null)
    setTurns([])
    inputRef.current?.focus()
  }

  async function renameConversation(id: number, title: string) {
    try {
      const updated = await api.renameConversation(id, title)
      setConversations((cs) => cs.map((c) => (c.id === id ? updated : c)))
    } catch {
      refreshConversations() // out of sync with the server: reload the truth
    }
  }

  async function deleteConversation(id: number) {
    try {
      await api.deleteConversation(id)
      setConversations((cs) => cs.filter((c) => c.id !== id))
      if (id === conversationId) newConversation()
    } catch {
      refreshConversations()
    }
  }

  function ask(text: string) {
    setRailOpen(false)
    void send(text)
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

  const activeTitle =
    conversationId != null ? conversations.find((c) => c.id === conversationId)?.title || 'Untitled' : 'New conversation'

  function toggleTrace() {
    setShowTrace((v) => {
      const next = !v
      writeFlag(TRACE_KEY, next)
      return next
    })
  }

  return (
    <div className="app">
      <Rail
        conversations={conversations}
        activeId={conversationId}
        onOpen={openConversation}
        onNew={newConversation}
        onRename={renameConversation}
        onDelete={deleteConversation}
        open={railOpen}
        onClose={() => setRailOpen(false)}
      />
      {railOpen && <div className="scrim" onClick={() => setRailOpen(false)} />}

      <div className="main-col">
        <header className="chat-header">
          {!railOpen && (
            <button type="button" className="icon-btn" onClick={() => setRailOpen(true)} aria-label="Open sidebar" title="Open sidebar">
              <PanelIcon />
            </button>
          )}
          <div className="chat-header-title">
            <p className="chat-title">{activeTitle}</p>
          </div>
          <div className="chat-header-actions">
            <button type="button" className="linklike" onClick={toggleTrace}>
              {showTrace ? 'Hide trace' : 'Show trace'}
            </button>
            <button type="button" className="linklike" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </header>

        <div className="chat-body">
          <main className="transcript" aria-live="polite" ref={transcriptRef} onScroll={onTranscriptScroll}>
            {turns.length === 0 ? (
              <div className="empty">
                <p>Ask about your own records or about the University's regulations.</p>
                <ul className="empty-suggestions">
                  {SUGGESTIONS[session.role].map((q) => (
                    <li key={q}>
                      <button type="button" onClick={() => ask(q)}>
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              turns.map((t) => (
                <Message
                  key={t.id}
                  turn={t}
                  showTrace={showTrace}
                  onConfirm={(card) => confirm(t.id, card)}
                  onCancel={() => cancel(t.id)}
                />
              ))
            )}
            <div ref={endRef} />
          </main>
        </div>

        <form className="composer" onSubmit={submit}>
          <div className="composer-pill">
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              placeholder={busy ? 'Waiting for the answer…' : 'Ask about your attendance, fees, or the regulations…'}
              rows={1}
              disabled={busy}
              autoFocus
              aria-label="Your question"
            />
            <button type="submit" className="primary composer-send" disabled={busy || !draft.trim()}>
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function PanelIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <line x1="9.5" y1="4" x2="9.5" y2="20" />
    </svg>
  )
}

function initialRailOpen(): boolean {
  try {
    if (window.innerWidth <= 800) return false
    const raw = localStorage.getItem(RAIL_KEY)
    return raw === null ? true : raw === '1'
  } catch {
    return true
  }
}

const TRACE_KEY = 'uniassist.trace'
const RAIL_KEY = 'uniassist.railOpen'
const MAX_AUTO_WAIT = 20 // seconds: longer than this and the person should decide

function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

function writeFlag(key: string, on: boolean) {
  try {
    localStorage.setItem(key, on ? '1' : '0')
  } catch {
    // storage unavailable: the toggle lasts for this tab only
  }
}

const ACTIVE_CONVERSATION_PREFIX = 'uniassist.activeConversation.'

function loadActiveConversation(subjectRef: string): number | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CONVERSATION_PREFIX + subjectRef)
    return raw ? Number(raw) : null
  } catch {
    return null
  }
}

function saveActiveConversation(subjectRef: string, id: number | null) {
  try {
    const key = ACTIVE_CONVERSATION_PREFIX + subjectRef
    if (id != null) localStorage.setItem(key, String(id))
    else localStorage.removeItem(key)
  } catch {
    // storage unavailable: the resumed conversation lasts for this tab only
  }
}

// A busy-provider 503 with a short Retry-After is a queue, not a failure: wait
// it out once, showing the wait, then send again. Anything longer surfaces as
// an error. Only retried if the first attempt never got as far as a delta —
// once the model has started answering, a retry would duplicate its start.
async function chatStreamWithOneRetry(
  message: string,
  conversationId: number | null,
  handlers: StreamHandlers,
  onQueued: (seconds: number) => void,
): Promise<ChatOut> {
  let deltaArrived = false
  const guarded: StreamHandlers = {
    ...handlers,
    onDelta: (chunk) => {
      deltaArrived = true
      handlers.onDelta?.(chunk)
    },
  }
  try {
    return await api.chatStream(message, conversationId, guarded)
  } catch (err) {
    if (
      !deltaArrived &&
      err instanceof ApiError &&
      err.status === 503 &&
      err.retryAfter &&
      err.retryAfter <= MAX_AUTO_WAIT
    ) {
      onQueued(err.retryAfter)
      await new Promise((r) => setTimeout(r, err.retryAfter! * 1000))
      const out = await api.chatStream(message, conversationId, handlers)
      return { ...out, queued_seconds: out.queued_seconds + err.retryAfter }
    }
    throw err
  }
}

function describe(err: unknown): string {
  if (err instanceof ApiError) {
    // the server maps both "busy, retry" and "no API key" to 503; a Retry-After
    // header is how it tells the two apart (§ backend/app/api/chat.py)
    if (err.status === 503 && err.retryAfter) {
      return `The assistant is rate-limited right now. Try again in about ${err.retryAfter} seconds.`
    }
    if (err.status === 401) return 'Your session has expired. Sign in again.'
    if (err.status === 503) return 'The language model is not configured on the server (no API key).'
    if (err.status === 410) return 'This confirmation has expired. Ask again to get a fresh one.'
    if (err.status === 409) return err.message
    return `${err.message} (${err.status})`
  }
  return 'The server could not be reached.'
}
