import { describe, expect, it } from 'vitest'
import { formatToolResultPanelDisplay } from '@/lib/toolResultContent'

describe('formatToolResultPanelDisplay', () => {
  it('extracts markdown wrapper', () => {
    const r = formatToolResultPanelDisplay(JSON.stringify({ markdown: '# Title\n\nBody' }))
    expect(r.kind).toBe('markdown')
    if (r.kind === 'markdown') expect(r.markdown).toContain('# Title')
  })

  it('pretty-prints JSON payloads without markdown', () => {
    const r = formatToolResultPanelDisplay(JSON.stringify({ query: 'x', total: 1 }))
    expect(r.kind).toBe('json')
    if (r.kind === 'json') {
      expect(r.json).toContain('"query"')
      expect(r.json).toContain('\n')
    }
  })
})
