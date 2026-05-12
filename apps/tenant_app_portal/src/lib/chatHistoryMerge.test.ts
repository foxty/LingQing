import { describe, expect, it } from 'vitest'
import type { Message, SessionMetrics } from '@/types'
import {
  emptyHistoryPage,
  mergeLatestPageIntoCachedHistory,
  reduceHistory,
} from '@/lib/chatHistoryMerge'

function sessionMessage(sessionId: string, role: Message['role'] = 'ai'): Message {
  return {
    role,
    content: `message-${sessionId}`,
    session_id: sessionId,
  }
}

const sampleMetrics: SessionMetrics = {
  session_id: 'sess-2',
  total_tokens: { input_tokens: 1, output_tokens: 2, total_tokens: 3 },
  duration_ms: 10,
  llm_call_count: 1,
  tool_call_count: 0,
  start_time: '2026-01-01T00:00:00.000Z',
  end_time: '2026-01-01T00:00:01.000Z',
}

describe('mergeLatestPageIntoCachedHistory', () => {
  it('returns latest page when cache is empty', () => {
    const latest = [sessionMessage('sess-2'), sessionMessage('sess-3')]
    expect(mergeLatestPageIntoCachedHistory([], latest)).toEqual(latest)
  })

  it('preserves older prefix when refetch only returns the latest window', () => {
    const cached = [
      sessionMessage('sess-1'),
      sessionMessage('sess-2'),
      sessionMessage('sess-3'),
      sessionMessage('sess-4'),
    ]
    const latest = [sessionMessage('sess-3'), sessionMessage('sess-4')]

    expect(mergeLatestPageIntoCachedHistory(cached, latest)).toEqual(cached)
  })
})

describe('reduceHistory', () => {
  it('prepends older pages without dropping the current tail', () => {
    const initial = reduceHistory(emptyHistoryPage, {
      type: 'set_initial',
      page: {
        messages: [sessionMessage('sess-3'), sessionMessage('sess-4')],
        nextBeforeSessionId: 'sess-3',
        hasMore: true,
      },
    })

    const prepended = reduceHistory(initial, {
      type: 'prepend',
      page: {
        messages: [sessionMessage('sess-1'), sessionMessage('sess-2')],
        nextBeforeSessionId: 'sess-1',
        hasMore: false,
      },
    })

    expect(prepended.messages.map((msg) => msg.session_id)).toEqual([
      'sess-1',
      'sess-2',
      'sess-3',
      'sess-4',
    ])
    expect(prepended.hasMore).toBe(false)
  })

  it('refresh_tail keeps prepended history when the latest page is shorter', () => {
    const withOlder = reduceHistory(
      {
        messages: [
          sessionMessage('sess-1'),
          sessionMessage('sess-2'),
          sessionMessage('sess-3'),
          sessionMessage('sess-4'),
        ],
        nextBeforeSessionId: 'sess-1',
        hasMore: false,
      },
      {
        type: 'refresh_tail',
        messages: [sessionMessage('sess-3'), sessionMessage('sess-4'), sessionMessage('sess-5')],
      }
    )

    expect(withOlder.messages.map((msg) => msg.session_id)).toEqual([
      'sess-1',
      'sess-2',
      'sess-3',
      'sess-4',
      'sess-5',
    ])
    expect(withOlder.hasMore).toBe(false)
  })

  it('patch_metrics only fills missing session metrics', () => {
    const patched = reduceHistory(
      {
        messages: [sessionMessage('sess-2'), { ...sessionMessage('sess-2'), metrics: sampleMetrics }],
        hasMore: false,
      },
      { type: 'patch_metrics', sessionId: 'sess-2', metrics: sampleMetrics }
    )

    expect(patched.messages[0].metrics).toEqual(sampleMetrics)
    expect(patched.messages[1].metrics).toEqual(sampleMetrics)
  })
})
