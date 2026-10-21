import type { Message } from '@/types'

export function getHumanMessageKindLabel(message: Message): string | null {
  const interaction = message.message_metadata?.interaction
  if (interaction === 'room_message') return 'room'
  if (interaction === 'agent_turn') return 'agent'
  return null
}

export function formatHumanAuthorLabel(
  message: Message,
  options: {
    currentUserId?: number
    userNameById?: Map<number, string>
  }
): string | null {
  const meta = message.message_metadata
  const display = typeof meta?.display_name === 'string' ? meta.display_name.trim() : ''
  if (display) return display
  const authorId = message.author_user_id
  if (authorId == null) return null
  if (options.currentUserId != null && authorId === options.currentUserId) return 'You'
  return options.userNameById?.get(authorId) ?? `User ${authorId}`
}
