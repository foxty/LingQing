import { describe, expect, it } from 'vitest'
import { hasMarkdownTable, isNumericMarkdownCell } from '@/lib/markdownReading'

describe('markdownReading', () => {
  it('detects GFM tables', () => {
    const md = '| A | B |\n| --- | --- |\n| 1 | 2 |'
    expect(hasMarkdownTable(md)).toBe(true)
  })

  it('detects numeric cells', () => {
    expect(isNumericMarkdownCell('1,234.56')).toBe(true)
    expect(isNumericMarkdownCell('Country')).toBe(false)
  })
})
