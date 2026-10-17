/** Shared inline sizing for auth-backed markdown images (charts, document parse images). */

import { cn } from '@/lib/utils'

const INLINE_BASE =
  'my-2 rounded-md border border-border bg-muted/20 object-contain cursor-zoom-in max-w-full w-full h-auto max-h-[min(32rem,65vh)]'

const PLACEHOLDER =
  'my-2 rounded-md border border-border bg-muted/20 object-contain w-full min-h-[10rem] max-h-[min(32rem,65vh)] max-w-full'

const EXPANDED =
  'mx-auto h-auto max-h-[min(88vh,calc(100vh-6rem))] max-w-full w-auto object-contain'

export function markdownImageInlineClassName(className?: string): string {
  return cn(INLINE_BASE, className)
}

export function markdownImagePlaceholderClassName(): string {
  return cn(PLACEHOLDER, 'animate-pulse cursor-default')
}

export function markdownImageExpandedClassName(): string {
  return EXPANDED
}
