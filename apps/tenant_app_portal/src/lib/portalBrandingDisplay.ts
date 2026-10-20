import type { TFunction } from 'i18next'
import type { PortalBranding } from '@/lib/portalBrandingApi'

export type ResolvedPortalBrand = {
  title: string
  subtitle: string | null
  pageTitle: string
}

export type PortalBrandDisplayOptions = {
  /** When true, avoid platform defaults until branding is known (no flash on refresh). */
  pending?: boolean
}

export function resolvePortalBrandDisplay(
  branding: PortalBranding | null | undefined,
  t: TFunction,
  options?: PortalBrandDisplayOptions
): ResolvedPortalBrand {
  if (options?.pending && branding === undefined) {
    return { title: '', subtitle: null, pageTitle: '' }
  }

  const title = branding?.app_title?.trim() || t('brand.title')
  const subtitleRaw = branding?.app_subtitle?.trim()
  const subtitle = subtitleRaw || t('brand.subtitle')
  const pageTitle = branding?.page_title?.trim() || t('brand.pageTitle')
  return { title, subtitle, pageTitle }
}
