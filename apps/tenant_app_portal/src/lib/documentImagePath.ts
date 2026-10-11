/** Parsed document images served by GET /documents/:id/images/:filename (auth required). */

export const DOCUMENT_IMAGE_PATH =
  /^(?:\/api)?\/documents\/\d+\/images\/[a-f0-9]{64}\.(?:png|jpe?g|gif|webp|tiff?|bmp)$/i

export function documentImageApiPath(src: string): string | null {
  const path = src.startsWith('http') ? new URL(src).pathname : src
  if (!DOCUMENT_IMAGE_PATH.test(path)) {
    return null
  }
  return path.replace(/^\/api/i, '')
}

export function isDocumentImageSrc(src: string | undefined): boolean {
  if (!src) {
    return false
  }
  return documentImageApiPath(src) !== null
}
