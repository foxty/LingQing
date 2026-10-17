import { describe, expect, it } from 'vitest'
import { isSecureChartImageSrc } from '@/lib/chartImagePath'
import { documentImageApiPath } from '@/lib/documentImagePath'
import {
  markdownImageMode,
  resolveMarkdownImageFetchPath,
} from '@/lib/markdownImagePath'

const DOC_IMAGE = `/api/documents/42/images/${'a'.repeat(64)}.png`
const CHART_SVG = '/api/charts/42/image.svg'

describe('markdownImagePath', () => {
  it('classifies document and chart images as authenticated', () => {
    expect(markdownImageMode(DOC_IMAGE)).toBe('authenticated-document')
    expect(markdownImageMode(CHART_SVG)).toBe('authenticated-document')
    expect(markdownImageMode('/charts/99/image.png')).toBe('authenticated-document')
  })

  it('returns null for unsupported src', () => {
    expect(markdownImageMode('/unknown.png')).toBeNull()
    expect(markdownImageMode('')).toBeNull()
  })

  it('resolves fetch path for document and chart', () => {
    expect(resolveMarkdownImageFetchPath(DOC_IMAGE)).toBe(documentImageApiPath(DOC_IMAGE))
    expect(resolveMarkdownImageFetchPath(CHART_SVG)).toBe('/charts/42/image.svg')
  })

  it('detects secure chart resource paths', () => {
    expect(isSecureChartImageSrc('/api/charts/1/image.svg')).toBe(true)
    expect(isSecureChartImageSrc('/charts/1/image.png')).toBe(true)
    expect(isSecureChartImageSrc('/api/static/charts/chart_1.svg')).toBe(false)
    expect(isSecureChartImageSrc(DOC_IMAGE)).toBe(false)
  })

  describe('regression: artifact chart markdown images', () => {
    const LEGACY_STATIC = '/api/static/charts/chart_1791888562_TEST.svg'

    it('does not treat legacy static chart urls as supported', () => {
      expect(documentImageApiPath(LEGACY_STATIC)).toBeNull()
      expect(markdownImageMode(LEGACY_STATIC)).toBeNull()
      expect(resolveMarkdownImageFetchPath(LEGACY_STATIC)).toBeNull()
    })

    it('treats /charts/{id}/image.* as authenticated fetch', () => {
      expect(documentImageApiPath(CHART_SVG)).toBeNull()
      expect(markdownImageMode(CHART_SVG)).toBe('authenticated-document')
      expect(resolveMarkdownImageFetchPath(CHART_SVG)).toBe('/charts/42/image.svg')
    })
  })
})
