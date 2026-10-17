/** Authenticated chart images (artifact resource id). */

export const CHART_RESOURCE_IMAGE_PATH =
  /^(?:\/api)?\/charts\/\d+\/image\.(?:svg|png)$/i

export function chartImageApiPath(src: string): string | null {
  const path = src.startsWith('http') ? new URL(src).pathname : src.split('?')[0]?.split('#')[0] ?? src
  if (!CHART_RESOURCE_IMAGE_PATH.test(path)) {
    return null
  }
  return path.replace(/^\/api/i, '')
}

export function isSecureChartImageSrc(src: string | undefined): boolean {
  if (!src?.trim()) {
    return false
  }
  const path = src.startsWith('http') ? new URL(src).pathname : src.split('?')[0]?.split('#')[0] ?? src
  return CHART_RESOURCE_IMAGE_PATH.test(path)
}
