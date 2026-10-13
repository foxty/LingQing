import { describe, expect, it } from 'vitest'
import {
  markdownImageInlineClassName,
  markdownImageKind,
} from '@/lib/markdownImagePresentation'

const DOC_IMAGE = `/api/documents/42/images/${'a'.repeat(64)}.png`
const CHART_SVG = '/api/static/charts/chart_1_TEST.svg'

describe('markdownImagePresentation', () => {
  it('maps src to chart vs document kind', () => {
    expect(markdownImageKind(DOC_IMAGE)).toBe('document')
    expect(markdownImageKind(CHART_SVG)).toBe('chart')
    expect(markdownImageKind('/unknown.png')).toBeNull()
  })

  it('applies viewport-aware classes by kind', () => {
    expect(markdownImageInlineClassName('chart')).toContain('70vh')
    expect(markdownImageInlineClassName('chart')).toContain('w-full')
    expect(markdownImageInlineClassName('document')).toContain('55vh')
    expect(markdownImageInlineClassName('document').split(/\s+/)).not.toContain('w-full')
  })
})
