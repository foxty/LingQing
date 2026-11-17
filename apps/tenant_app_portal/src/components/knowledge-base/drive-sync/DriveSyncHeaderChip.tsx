import { StatusChip } from '@/components/StatusChip'
import { driveSyncHeaderChip } from '@/lib/driveSyncDisplay'
import type { TFunction } from 'i18next'
import { Cloud, Loader2 } from 'lucide-react'

export function DriveSyncHeaderChip({
  state,
  t,
}: {
  state: Parameters<typeof driveSyncHeaderChip>[0]
  t: TFunction
}) {
  const chip = driveSyncHeaderChip(state)
  if (chip === 'loading') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Cloud className="h-3.5 w-3.5" aria-hidden />
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      </span>
    )
  }
  return (
    <StatusChip
      variant={chip.variant}
      size="header"
      icon={<Cloud className="h-3 w-3 shrink-0 opacity-90" aria-hidden />}
    >
      {t(chip.labelKey)}
    </StatusChip>
  )
}