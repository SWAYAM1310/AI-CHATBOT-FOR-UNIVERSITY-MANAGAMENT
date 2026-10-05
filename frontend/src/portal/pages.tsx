// The one page every role shares that is not a page of its own: the assistant,
// which is the chat with the portal's session.
import { Chat } from '../Chat'
import { usePortal } from './context'

export function Assistant() {
  const { session } = usePortal()
  return <Chat session={session} />
}
