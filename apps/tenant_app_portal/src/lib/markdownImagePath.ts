/** Resolve how markdown `img` sources should load in the tenant app portal. */

import { chartImageApiPath } from '@/lib/chartImagePath'
import { documentImageApiPath } from '@/lib/documentImagePath'

export type MarkdownImageMode = 'authenticated-document' | 'direct'

/** How this markdown image should be rendered, or null if unsupported. */
export function markdownImageMode(src: string | undefined): MarkdownImageMode | null {
  if (!src?.trim()) {
    return null
  }
  if (documentImageApiPath(src) || chartImageApiPath(src)) {
    return 'authenticated-document'
  }
  return null
}

/**
 * Whether the image should use the authenticated document/chart fetch path.
 * Returns null when the src is not a supported API-backed image.
 */
export function resolveMarkdownImageFetchPath(src: string | undefined): string | null {
  if (!src?.trim()) {
    return null
  }
  return documentImageApiPath(src) ?? chartImageApiPath(src)
}
