import { describe, expect, it } from 'vitest'
import {
  filterUnselectedMentionResults,
  mentionResourceChipId,
  reduceMentionPickerKeyDown,
} from '@/lib/chatMention'

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
