/** Shared inline sizing for markdown-backed images (by asset kind, not chat vs report). */

import { documentImageApiPath } from '@/lib/documentImagePath'
import { isStaticChartSvgSrc } from '@/lib/markdownImagePath'
import { cn } from '@/lib/utils'

export type MarkdownImageKind = 'chart' | 'document'

export function markdownImageKind(src: string | undefined): MarkdownImageKind | null {
  if (!src?.trim()) {
    return null
  }
  if (documentImageApiPath(src)) {
    return 'document'
  }
  if (isStaticChartSvgSrc(src)) {
    return 'chart'
  }
  return null
}

const INLINE_BASE = 'my-2 rounded-md border border-border bg-muted/20 object-contain cursor-zoom-in'

const INLINE_BY_KIND: Record<MarkdownImageKind, string> = {
  chart: 'w-full max-w-full h-auto max-h-[min(36rem,70vh)]',
  document: 'max-w-full h-auto max-h-[min(28rem,55vh)]',
}

const PLACEHOLDER_BY_KIND: Record<MarkdownImageKind, string> = {
  chart: 'w-full min-h-[12rem] max-h-[min(36rem,70vh)]',
  document: 'w-full min-h-[8rem] max-h-[min(28rem,55vh)] max-w-full',
}

export function markdownImageInlineClassName(kind: MarkdownImageKind, className?: string): string {
  return cn(INLINE_BASE, INLINE_BY_KIND[kind], className)
}

export function markdownImagePlaceholderClassName(kind: MarkdownImageKind): string {
  return cn(INLINE_BASE, PLACEHOLDER_BY_KIND[kind], 'animate-pulse cursor-default')
}

const EXPANDED_SHARED = 'h-auto max-h-[min(88vh,calc(100vh-6rem))] object-contain'

/** Lightbox: charts scale to dialog width; photos keep natural width up to the cap. */
export function markdownImageExpandedClassName(kind: MarkdownImageKind): string {
  if (kind === 'chart') {
    return cn(EXPANDED_SHARED, 'w-full min-w-0')
  }
  return cn(EXPANDED_SHARED, 'max-w-full w-auto')
}
