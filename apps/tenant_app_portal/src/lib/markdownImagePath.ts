/** Resolve how markdown `img` sources should load in the tenant app portal. */

import { documentImageApiPath } from '@/lib/documentImagePath'

export type MarkdownImageMode = 'authenticated-document' | 'direct'

const STATIC_CHART_SVG_PATH =
  /^(?:\/api)?\/static\/charts\/[^/?#]+\.svg$/i

function pathnameOf(src: string): string {
  const trimmed = src.trim()
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return new URL(trimmed).pathname
  }
  return trimmed.split('?')[0]?.split('#')[0] ?? trimmed
}

export function isStaticChartSvgSrc(src: string | undefined): boolean {
  if (!src?.trim()) {
    return false
  }
  return STATIC_CHART_SVG_PATH.test(pathnameOf(src))
}

/** How this markdown image should be rendered, or null if unsupported. */
export function markdownImageMode(src: string | undefined): MarkdownImageMode | null {
  if (!src?.trim()) {
    return null
  }
  if (documentImageApiPath(src)) {
    return 'authenticated-document'
  }
  if (isStaticChartSvgSrc(src)) {
    return 'direct'
  }
  return null
}

/**
 * Same-origin URL for `<img src>` (Vite dev proxy uses `/api` → backend).
 * Absolute backend URLs for `/static/charts/` are rewritten to `/api/static/charts/`.
 */
export function directMarkdownImageSrc(src: string): string | null {
  if (markdownImageMode(src) !== 'direct') {
    return null
  }
  const path = pathnameOf(src)
  if (path.startsWith('/api/')) {
    return path
  }
  if (path.startsWith('/static/')) {
    return `/api${path}`
  }
  if (src.startsWith('http') && path.startsWith('/static/charts/')) {
    return `/api${path}`
  }
  return src.trim()
}
