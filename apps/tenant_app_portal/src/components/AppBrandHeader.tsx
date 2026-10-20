import { Bot } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import PortalLogoImage from '@/components/PortalLogoImage'
import { resolvePortalBrandDisplay } from '@/lib/portalBrandingDisplay'
import type { PortalBranding } from '@/lib/portalBrandingApi'
import { cn } from '@/lib/utils'

type AppBrandHeaderProps = {
  branding?: PortalBranding | null
  tenantName?: string | null
  /** True while branding is still loading and no cached snapshot is available. */
  pending?: boolean
  /** Show tenant name on the second line (app shell header). */
  showTenantMeta?: boolean
  /** Login card: logo + title only (no subtitle / tenant meta). */
  forLogin?: boolean
  compact?: boolean
  centered?: boolean
  className?: string
}

export default function AppBrandHeader({
  branding,
  tenantName,
  pending = false,
  showTenantMeta = true,
  forLogin = false,
  compact = false,
  centered = false,
  className,
}: AppBrandHeaderProps) {
  const { t } = useTranslation()
  const { title, subtitle } = resolvePortalBrandDisplay(branding, t, {
    pending,
    omitDefaultSubtitle: forLogin,
  })
  const showSkeleton = pending && branding === undefined
  const hasLogo = Boolean(branding?.logo_url?.trim())

  let metaLine: string | null = null
  if (!forLogin) {
    const metaParts: string[] = []
    if (subtitle) {
      metaParts.push(subtitle)
    }
    if (showTenantMeta && tenantName?.trim()) {
      metaParts.push(tenantName.trim())
    }
    metaLine = metaParts.length ? metaParts.join(' · ') : null
  }

  const logoBoxClass = forLogin
    ? 'h-14 max-w-[min(100%,14rem)] sm:h-16'
    : compact
      ? 'h-8 w-8 rounded-md'
      : 'h-9 w-9 rounded-md'

  const logoFrameClass = forLogin
    ? 'overflow-visible bg-transparent'
    : 'overflow-hidden border bg-card'

  const fallbackIconClass = forLogin
    ? 'h-8 w-8 sm:h-9 sm:w-9'
    : compact
      ? 'h-5 w-5'
      : 'h-6 w-6'

  const titleClass = forLogin
    ? 'text-xl font-semibold sm:text-2xl'
    : compact
      ? 'text-sm font-semibold'
      : 'text-base font-semibold'

  const metaClass = forLogin ? 'text-sm text-muted-foreground' : 'text-xs text-muted-foreground'

  const textWrapClass = forLogin
    ? 'max-w-full px-1'
    : centered
      ? 'max-w-[16rem] sm:max-w-xs'
      : undefined

  return (
    <div
      className={cn(
        'flex min-w-0 items-center',
        forLogin ? 'gap-3 sm:gap-4' : 'gap-2.5',
        centered && 'flex-col text-center',
        forLogin && centered && 'py-1',
        className
      )}
    >
      <div
        className={cn(
          'flex shrink-0 items-center justify-center',
          logoFrameClass,
          logoBoxClass,
          forLogin && !hasLogo && !showSkeleton && 'h-14 w-14 sm:h-16 sm:w-16'
        )}
        aria-hidden={hasLogo ? undefined : true}
      >
        {showSkeleton ? (
          <div
            className={cn(
              'animate-pulse bg-muted',
              forLogin ? 'h-12 w-32 rounded-md sm:h-14 sm:w-36' : 'h-full w-full rounded'
            )}
          />
        ) : hasLogo ? (
          <PortalLogoImage
            logoUrl={branding?.logo_url}
            className={cn(
              'object-contain',
              forLogin ? 'h-14 w-auto max-w-[min(100%,14rem)] sm:h-16' : 'h-full w-full p-1'
            )}
          />
        ) : (
          <Bot className={cn('text-muted-foreground', fallbackIconClass)} />
        )}
      </div>
      <div className={cn('min-w-0 leading-tight', centered && 'max-w-full')}>
        {showSkeleton ? (
          <div className={cn('space-y-1', centered && 'flex flex-col items-center')}>
            <div
              className={cn(
                'animate-pulse rounded bg-muted',
                forLogin ? 'h-6 w-40 sm:h-7 sm:w-48' : 'h-3.5 w-28'
              )}
            />
            {!forLogin ? (
              <div className="h-3 w-36 animate-pulse rounded bg-muted" />
            ) : null}
          </div>
        ) : (
          <>
            <p
              className={cn(
                titleClass,
                forLogin ? 'text-balance break-words' : 'truncate',
                textWrapClass
              )}
            >
              {title}
            </p>
            {metaLine ? (
              <p className={cn(metaClass, forLogin ? 'mt-1 text-balance' : 'truncate', textWrapClass)}>
                {metaLine}
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
