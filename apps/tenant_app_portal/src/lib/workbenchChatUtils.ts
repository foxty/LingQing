import type { Message } from '@/types'

export function toTimestampMs(value?: string): number | null {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}

export function getLatestMessageTimestamp(messages: Message[]): number {
  let latest = 0
  for (const msg of messages) {
    const ts = toTimestampMs(msg.timestamp)
    if (ts && ts > latest) {
      latest = ts
    }
  }
  return latest
}

export function getLatestSessionWindow(messages: Message[]): { startMs: number; endMs: number } | null {
  if (messages.length === 0) return null

  let latestSessionId: string | null = null
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].session_id) {
      latestSessionId = messages[i].session_id || null
      break
    }
  }
  if (!latestSessionId) return null

  let startMs = Number.POSITIVE_INFINITY
  let endMs = Number.NEGATIVE_INFINITY

  for (const msg of messages) {
    if (msg.session_id !== latestSessionId) continue
    const ts = toTimestampMs(msg.timestamp)
    if (!ts) continue
    startMs = Math.min(startMs, ts)
    endMs = Math.max(endMs, ts)
  }

  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) {
    return null
  }

  return { startMs, endMs }
}
