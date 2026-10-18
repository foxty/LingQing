import { describe, expect, it } from 'vitest'
import {
  extractMentionSearchTerm,
  filterUnselectedMentionResults,
  mentionResourceChipId,
  reduceMentionPickerKeyDown,
  shouldOpenMentionPicker,
  stripTrailingMention,
} from '@/lib/chatMention'

describe('extractMentionSearchTerm', () => {
  it('returns empty string when input ends with bare @', () => {
    expect(extractMentionSearchTerm('hello @')).toBe('')
  })

  it('returns query after @ at end of input', () => {
    expect(extractMentionSearchTerm('please review @retail')).toBe('retail')
  })

  it('ignores @ that is not at the end token', () => {
    expect(extractMentionSearchTerm('@user hello')).toBeNull()
  })

  it('ignores @ in the middle of a line', () => {
    expect(extractMentionSearchTerm('a@b.com test')).toBeNull()
  })
})

describe('shouldOpenMentionPicker', () => {
  it('opens when trailing @ is present and composer is idle', () => {
    expect(shouldOpenMentionPicker('attach @rep', false)).toBe(true)
  })

  it('does not open while busy', () => {
    expect(shouldOpenMentionPicker('attach @rep', true)).toBe(false)
  })

  it('does not open without trailing mention', () => {
    expect(shouldOpenMentionPicker('hello world', false)).toBe(false)
  })
})

describe('stripTrailingMention', () => {
  it('removes trailing @query and keeps leading text', () => {
    expect(stripTrailingMention('draft @chart')).toBe('draft ')
  })

  it('clears input that is only a mention', () => {
    expect(stripTrailingMention('@only')).toBe('')
  })
})

describe('reduceMentionPickerKeyDown', () => {
  const base = { open: true, resultCount: 3, activeIndex: 0 }

  it('returns none when picker is closed', () => {
    expect(
      reduceMentionPickerKeyDown({ ...base, open: false, key: 'ArrowDown' })
    ).toEqual({ type: 'none' })
  })

  it('closes on Escape', () => {
    expect(reduceMentionPickerKeyDown({ ...base, key: 'Escape' })).toEqual({ type: 'close' })
  })

  it('wraps arrow navigation', () => {
    expect(reduceMentionPickerKeyDown({ ...base, activeIndex: 2, key: 'ArrowDown' })).toEqual({
      type: 'move',
      nextIndex: 0,
    })
    expect(reduceMentionPickerKeyDown({ ...base, activeIndex: 0, key: 'ArrowUp' })).toEqual({
      type: 'move',
      nextIndex: 2,
    })
  })

  it('selects active row on Enter', () => {
    expect(reduceMentionPickerKeyDown({ ...base, activeIndex: 1, key: 'Enter' })).toEqual({
      type: 'select',
      index: 1,
    })
  })

  it('ignores arrows when there are no results', () => {
    expect(
      reduceMentionPickerKeyDown({ ...base, resultCount: 0, key: 'ArrowDown' })
    ).toEqual({ type: 'none' })
  })
})

describe('mentionResourceChipId', () => {
  it('uses stable artifact prefix', () => {
    expect(mentionResourceChipId(42)).toBe('artifact-42')
  })
})

describe('filterUnselectedMentionResults', () => {
  it('drops artifacts already attached in the composer', () => {
    const items = [
      { artifact_id: 1, title: 'a' },
      { artifact_id: 2, title: 'b' },
    ]
    const selected = new Set([mentionResourceChipId(1)])
    expect(filterUnselectedMentionResults(items, selected)).toEqual([
      { artifact_id: 2, title: 'b' },
    ])
  })
})
