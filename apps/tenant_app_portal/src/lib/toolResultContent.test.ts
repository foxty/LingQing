import { describe, expect, it } from 'vitest'
import { toolResultMarkdownForDisplay } from '@/lib/toolResultContent'

describe('toolResultMarkdownForDisplay', () => {
  it('extracts markdown from legacy JSON tool payloads', () => {
    const md = '\n\n![Chart](/charts/1/image.svg)\n\n'
    const content = JSON.stringify({ markdown: md })
    expect(toolResultMarkdownForDisplay(content)).toBe(md)
  })

  it('returns plain markdown unchanged', () => {
    const md = '![Chart](/charts/2/image.svg)'
    expect(toolResultMarkdownForDisplay(md)).toBe(md)
  })
})
