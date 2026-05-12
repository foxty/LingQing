import { describe, expect, it } from 'vitest'
import type { Message } from '@/types'
import { buildMessageRenderItems } from '@/lib/chatTurns'

function human(content: string, timestamp: string): Message {
  return { role: 'human', content, timestamp }
}

function ai(content: string, sessionId: string, timestamp: string): Message {
  return { role: 'ai', content, session_id: sessionId, timestamp }
}

describe('buildMessageRenderItems', () => {
  it('keeps existing render keys stable when older messages are prepended', () => {
    const recent = [
      human('recent question', '2026-01-02T10:00:00.000Z'),
      ai('recent answer', 'sess-recent', '2026-01-02T10:01:00.000Z'),
    ]
    const withOlder = [
      human('older question', '2026-01-01T10:00:00.000Z'),
      ai('older answer', 'sess-older', '2026-01-01T10:01:00.000Z'),
      ...recent,
    ]

    const initialKeys = buildMessageRenderItems(recent).map((item) => item.key)
    const mergedKeys = buildMessageRenderItems(withOlder).map((item) => item.key)

    expect(mergedKeys.slice(-initialKeys.length)).toEqual(initialKeys)
  })
})
