import { describe, expect, it } from 'vitest'
import {
  applyToolEnd,
  applyToolStart,
  shouldNavigateAfterStreamStart,
  shouldResetStreamOnThreadChange,
  shouldShowStreamingTurn,
} from '@/lib/chatStream'
import { buildStreamingTurn } from '@/lib/chatTurns'

describe('chatStream tool state', () => {
  it('starts a running tool and completes the matching running entry', () => {
    const started = applyToolStart([], 'stream-tool-0', 'search')
    expect(started).toHaveLength(1)
    expect(started[0]).toMatchObject({ id: 'stream-tool-0', name: 'search', status: 'running' })

    const ended = applyToolEnd(started, 'search', 'stream-tool-1')
    expect(ended).toHaveLength(1)
    expect(ended[0].status).toBe('completed')
    expect(ended[0].endedAt).toBeTruthy()
  })
})

describe('shouldResetStreamOnThreadChange', () => {
  it('preserves stream when route threadId catches up to in-flight stream', () => {
    expect(shouldResetStreamOnThreadChange('thread-1', 'thread-1', true)).toBe(false)
  })

  it('resets when switching to a different thread while streaming', () => {
    expect(shouldResetStreamOnThreadChange('thread-2', 'thread-1', true)).toBe(true)
  })

  it('resets when not streaming even if thread ids match', () => {
    expect(shouldResetStreamOnThreadChange('thread-1', 'thread-1', false)).toBe(true)
  })

  it('resets when threadId becomes null', () => {
    expect(shouldResetStreamOnThreadChange(null, 'thread-1', true)).toBe(true)
  })
})

describe('shouldShowStreamingTurn', () => {
  it('shows turn while SSE is active', () => {
    expect(shouldShowStreamingTurn(true, false)).toBe(true)
  })

  it('shows turn when session poll reports running without SSE', () => {
    expect(shouldShowStreamingTurn(false, true)).toBe(true)
  })

  it('hides turn when idle', () => {
    expect(shouldShowStreamingTurn(false, false)).toBe(false)
  })
})

describe('shouldNavigateAfterStreamStart', () => {
  it('navigates only for first-message thread creation', () => {
    expect(shouldNavigateAfterStreamStart('thread-new')).toBe(true)
    expect(shouldNavigateAfterStreamStart(null)).toBe(false)
  })
})

describe('buildStreamingTurn thinking placeholder', () => {
  it('uses thinking placeholder when busy but no streamed content yet', () => {
    const turn = buildStreamingTurn({ content: '', toolCalls: [] })
    expect(turn?.finalMessage.content).toBe('workbench.thinking')
  })
})
