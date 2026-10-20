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
  /** When true, leave subtitle null unless tenant configured app_subtitle (login chrome). */
  omitDefaultSubtitle?: boolean
}

/** Strip HTML tags from admin-entered branding text for safe plain display. */
export function plainTextBrandingField(value: string | null | undefined): string | null {
  if (!value?.trim()) {
    return null
  }
  const stripped = value.replace(/<[^>]*>/g, '').trim()
  return stripped || null
}

export function resolvePortalBrandDisplay(
  branding: PortalBranding | null | undefined,
  t: TFunction,
  options?: PortalBrandDisplayOptions
): ResolvedPortalBrand {
  if (options?.pending && branding === undefined) {
    return { title: '', subtitle: null, pageTitle: '' }
  }

  const title = plainTextBrandingField(branding?.app_title) || t('brand.title')
  const subtitleRaw = plainTextBrandingField(branding?.app_subtitle)
  const subtitle = subtitleRaw || (options?.omitDefaultSubtitle ? null : t('brand.subtitle'))
  const pageTitle = plainTextBrandingField(branding?.page_title) || t('brand.pageTitle')
  return { title, subtitle, pageTitle }
}
