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
  /** Show tenant name on the second line (off on login where copy repeats it). */
  showTenantMeta?: boolean
  compact?: boolean
  className?: string
}

export default function AppBrandHeader({
  branding,
  tenantName,
  pending = false,
  showTenantMeta = true,
  compact = false,
  className,
}: AppBrandHeaderProps) {
  const { t } = useTranslation()
  const { title, subtitle } = resolvePortalBrandDisplay(branding, t, { pending })
  const showSkeleton = pending && branding === undefined
  const hasLogo = Boolean(branding?.logo_url?.trim())

  const metaParts: string[] = []
  if (subtitle) {
    metaParts.push(subtitle)
  }
  if (showTenantMeta && tenantName?.trim()) {
    metaParts.push(tenantName.trim())
  }
  const metaLine = metaParts.join(' · ')

  return (
    <div className={cn('flex min-w-0 items-center gap-2.5', className)}>
      <div
        className={cn(
          'flex shrink-0 items-center justify-center overflow-hidden rounded-md border bg-card',
          compact ? 'h-8 w-8' : 'h-9 w-9'
        )}
        aria-hidden={hasLogo ? undefined : true}
      >
        {showSkeleton ? (
          <div className="h-full w-full animate-pulse rounded bg-muted" />
        ) : hasLogo ? (
          <PortalLogoImage
            logoUrl={branding?.logo_url}
            className="h-full w-full object-contain p-1"
          />
        ) : (
          <Bot className={cn('text-muted-foreground', compact ? 'h-5 w-5' : 'h-6 w-6')} />
        )}
      </div>
      <div className="min-w-0 leading-tight">
        {showSkeleton ? (
          <div className="space-y-1">
            <div className="h-3.5 w-28 animate-pulse rounded bg-muted" />
            <div className="h-3 w-36 animate-pulse rounded bg-muted" />
          </div>
        ) : (
          <>
            <p className={cn('font-semibold truncate', compact ? 'text-sm' : 'text-base')}>{title}</p>
            {metaLine ? (
              <p className="text-xs text-muted-foreground truncate">{metaLine}</p>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
