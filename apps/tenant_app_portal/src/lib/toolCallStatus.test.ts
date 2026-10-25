import { describe, expect, it } from 'vitest'
import {
  getToolCallDisplayStatus,
  isToolResultFailed,
  isToolResultSkipped,
  resolvePersistedToolOutcome,
} from '@/lib/toolCallStatus'
import type { Message } from '@/types'

function toolMsg(status?: string, content = 'ok'): Message {
  return {
    role: 'tool',
    content,
    additional_kwargs: status ? { tool_result_status: status } : {},
  }
}

describe('resolvePersistedToolOutcome', () => {
  it('defaults to success when status is absent', () => {
    expect(resolvePersistedToolOutcome({ role: 'tool', content: 'x' })).toBe('success')
  })

  it('maps partial to success', () => {
    expect(resolvePersistedToolOutcome(toolMsg('partial'))).toBe('success')
  })

  it('maps error and skipped', () => {
    expect(resolvePersistedToolOutcome(toolMsg('error'))).toBe('error')
    expect(resolvePersistedToolOutcome(toolMsg('skipped'))).toBe('skipped')
  })
})

describe('isToolResultFailed / isToolResultSkipped', () => {
  it('uses only persisted tool_result_status', () => {
    const legacyFailureText: Message = {
      role: 'tool',
      content: "Tool call failed for 'run_sql': timeout",
    }
    expect(isToolResultFailed(legacyFailureText)).toBe(false)

    const withErrorMeta: Message = {
      role: 'tool',
      content: 'ok',
      additional_kwargs: {
        tool_error: { code: 'X', message: 'bad' },
        tool_result_status: 'error',
      },
    }
    expect(isToolResultFailed(withErrorMeta)).toBe(true)
    expect(isToolResultSkipped(toolMsg('skipped'))).toBe(true)
  })
})

describe('getToolCallDisplayStatus', () => {
  it('returns error when persisted status is error', () => {
    expect(getToolCallDisplayStatus({ status: 'completed', resultMessage: toolMsg('error') })).toBe(
      'error'
    )
  })

  it('returns completed for success default', () => {
    expect(getToolCallDisplayStatus({ status: 'completed', resultMessage: toolMsg('success') })).toBe(
      'completed'
    )
    expect(getToolCallDisplayStatus({ status: 'completed', resultMessage: { role: 'tool', content: 'x' } })).toBe(
      'completed'
    )
  })

  it('prefers running over result message', () => {
    expect(
      getToolCallDisplayStatus({ status: 'running', resultMessage: toolMsg('error') })
    ).toBe('running')
  })
})
