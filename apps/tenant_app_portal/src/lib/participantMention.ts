/** @-mention helpers for people and agents (not artifacts). */

const TRAILING_MENTION_PATTERN = /@([^\s]*)$/

export type ComposeMentionPayload = {
  type: 'user' | 'agent'
  id: number
  label: string
}

export function extractParticipantMentionQuery(input: string): string | null {
  const match = input.match(TRAILING_MENTION_PATTERN)
  return match ? match[1] : null
}

export function shouldOpenParticipantMentionPicker(input: string, isBusy: boolean): boolean {
  if (isBusy) return false
  return extractParticipantMentionQuery(input) !== null
}

export function stripTrailingParticipantMention(input: string): string {
  return input.replace(/@[^\s]*$/, '')
}

/** Merge picker mentions with @labels still present in the message body. */
export function mergeMentionsFromMessageText(
  text: string,
  picked: ComposeMentionPayload[],
  rosterAgents: { id: number; label: string }[],
  memberUsers: { id: number; label: string }[]
): ComposeMentionPayload[] {
  const merged = [...picked]
  const has = (type: ComposeMentionPayload['type'], id: number) =>
    merged.some((m) => m.type === type && m.id === id)

  for (const agent of rosterAgents) {
    if (!agent.label || !text.includes(`@${agent.label}`)) continue
    if (!has('agent', agent.id)) {
      merged.push({ type: 'agent', id: agent.id, label: agent.label })
    }
  }
  for (const user of memberUsers) {
    if (!user.label || !text.includes(`@${user.label}`)) continue
    if (!has('user', user.id)) {
      merged.push({ type: 'user', id: user.id, label: user.label })
    }
  }
  return merged
}
