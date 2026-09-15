// One thin client over the backend. Every call carries the bearer token; a
// non-2xx response becomes an ApiError with the server's detail, so the UI
// can say what went wrong rather than "something went wrong".
import type { Card, ChatOut, ConfirmOut, ConversationOut, Me, MessageOut, Role } from './types'

export class ApiError extends Error {
  status: number
  retryAfter: number | null

  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message)
    this.status = status
    this.retryAfter = retryAfter
  }
}

let token: string | null = null

export function setToken(t: string | null) {
  token = t
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) }
  if (init.body) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(path, { ...init, headers })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body && typeof body.detail === 'string' ? body.detail : res.statusText
    const retry = res.headers.get('Retry-After')
    throw new ApiError(res.status, detail, retry ? Number(retry) : null)
  }
  return body as T
}

// --- streaming chat -----------------------------------------------------
// EventSource can't POST or carry the bearer header, so the SSE frames are
// parsed by hand off a plain fetch stream.

export interface StreamTool {
  name: string
  args: Record<string, unknown>
  ok: boolean
  error: string | null
}

export interface StreamHandlers {
  onStatus?: (stage: string) => void
  onTool?: (tool: StreamTool) => void
  onCards?: (cards: Card[]) => void
  onDelta?: (text: string) => void
  onQueued?: (seconds: number) => void
}

async function chatStream(
  message: string,
  conversationId: number | null,
  handlers: StreamHandlers,
): Promise<ChatOut> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, conversation_id: conversationId }),
  })
  if (!res.ok || !res.body) {
    // the stream never opened at all: same error shape as the blocking endpoint
    const body = await res.json().catch(() => null)
    const detail = body && typeof body.detail === 'string' ? body.detail : res.statusText
    const retry = res.headers.get('Retry-After')
    throw new ApiError(res.status, detail, retry ? Number(retry) : null)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let done: ChatOut | null = null

  while (true) {
    const { value, done: streamDone } = await reader.read()
    if (streamDone) break
    buf += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buf.indexOf('\n\n')) !== -1) {
      const frame = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      const out = handleFrame(frame, handlers)
      if (out) done = out
    }
  }
  if (!done) throw new ApiError(0, 'The stream ended without a reply.')
  return done
}

function handleFrame(frame: string, handlers: StreamHandlers): ChatOut | null {
  let event = 'message'
  let data = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  const payload = JSON.parse(data)
  switch (event) {
    case 'status':
      handlers.onStatus?.(payload.stage)
      return null
    case 'tool':
      handlers.onTool?.(payload as StreamTool)
      return null
    case 'cards':
      handlers.onCards?.(payload.cards as Card[])
      return null
    case 'delta':
      handlers.onDelta?.(payload.text as string)
      return null
    case 'queued':
      handlers.onQueued?.(payload.seconds as number)
      return null
    case 'done':
      return payload as ChatOut
    case 'error':
      throw new ApiError(payload.status, payload.detail, payload.retry_after ?? null)
    default:
      return null
  }
}

export const api = {
  login(email: string, password: string) {
    return request<{ access_token: string; role: Role; subject_ref: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },
  me() {
    return request<Me>('/api/me')
  },
  chat(message: string, conversationId: number | null) {
    return request<ChatOut>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId }),
    })
  },
  chatStream,
  confirm(confirmToken: string, conversationId: number | null) {
    return request<ConfirmOut>('/api/chat/confirm', {
      method: 'POST',
      body: JSON.stringify({ token: confirmToken, conversation_id: conversationId }),
    })
  },
  conversations() {
    return request<ConversationOut[]>('/api/chat')
  },
  messages(conversationId: number) {
    return request<MessageOut[]>(`/api/chat/${conversationId}`)
  },
  renameConversation(conversationId: number, title: string) {
    return request<ConversationOut>(`/api/chat/${conversationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    })
  },
  deleteConversation(conversationId: number) {
    return request<void>(`/api/chat/${conversationId}`, { method: 'DELETE' })
  },
}
