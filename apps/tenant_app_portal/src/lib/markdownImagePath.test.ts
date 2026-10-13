import { describe, expect, it } from 'vitest'
import { documentImageApiPath } from '@/lib/documentImagePath'
import {
  directMarkdownImageSrc,
  isStaticChartSvgSrc,
  markdownImageMode,
} from '@/lib/markdownImagePath'

const DOC_IMAGE = `/api/documents/42/images/${'a'.repeat(64)}.png`

/** Production-shaped chart URL from agent markdown (regression: was ignored by document-only img). */
const CHAT_CHART_SVG =
  '/api/static/charts/chart_1791888562_TEST_1__Bar__single_series__f7e1aac7.svg'

describe('markdownImagePath', () => {
  it('detects static chart svg paths', () => {
    expect(isStaticChartSvgSrc('/api/static/charts/chart_1_TEST.svg')).toBe(true)
    expect(isStaticChartSvgSrc('/static/charts/chart_1.svg')).toBe(true)
    expect(isStaticChartSvgSrc('http://localhost:8000/static/charts/chart_1.svg')).toBe(true)
    expect(isStaticChartSvgSrc('/documents/1/images/abc.png')).toBe(false)
  })

  it('classifies document vs chart images', () => {
    expect(markdownImageMode(DOC_IMAGE)).toBe('authenticated-document')
    expect(markdownImageMode('/api/static/charts/chart_1791888562_TEST.svg')).toBe('direct')
  })

  it('rewrites chart urls for vite proxy', () => {
    expect(directMarkdownImageSrc('/api/static/charts/chart_1.svg')).toBe('/api/static/charts/chart_1.svg')
    expect(directMarkdownImageSrc('/static/charts/chart_1.svg')).toBe('/api/static/charts/chart_1.svg')
    expect(directMarkdownImageSrc('http://localhost:8000/static/charts/chart_1.svg')).toBe(
      '/api/static/charts/chart_1.svg',
    )
  })

  describe('regression: chat chart markdown images', () => {
    it('treats agent chart svg as direct, not authenticated document', () => {
      expect(documentImageApiPath(CHAT_CHART_SVG)).toBeNull()
      expect(markdownImageMode(CHAT_CHART_SVG)).toBe('direct')
      expect(directMarkdownImageSrc(CHAT_CHART_SVG)).toBe(CHAT_CHART_SVG)
    })

    it('does not classify chart svg as unsupported (old AuthDocumentImage returned null)', () => {
      expect(markdownImageMode(CHAT_CHART_SVG)).not.toBeNull()
      expect(markdownImageMode(CHAT_CHART_SVG)).not.toBe('authenticated-document')
    })
  })
})
