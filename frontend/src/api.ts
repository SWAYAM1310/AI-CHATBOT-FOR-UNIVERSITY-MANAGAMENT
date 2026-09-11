// One thin client over the backend. Every call carries the bearer token; a
// non-2xx response becomes an ApiError with the server's detail, so the UI
// can say what went wrong rather than "something went wrong".
import type { ChatOut, ConfirmOut, ConversationOut, Me, MessageOut, Role } from './types'

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
}
