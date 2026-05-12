import { Button } from '@/components/ui/button'
import type { PendingIdentity } from '@/lib/identityApi'

type Props = {
  pending: PendingIdentity[]
  onApprove: (id: number) => void
  onReject: (identity: PendingIdentity) => void
  t: (key: string, options?: Record<string, unknown>) => string
}

export default function IdentityPendingPanel({ pending, onApprove, onReject, t }: Props) {
  if (pending.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('settings.identityTab.noPending')}</p>
  }

  return (
    <div className="divide-y divide-border/60">
      {pending.map((p) => (
        <div key={p.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium">{p.email || p.external_subject}</p>
            <p className="text-xs text-muted-foreground">
              {p.provider_display_name} · {p.display_name || '—'}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => onApprove(p.id)}>
              {t('settings.identityTab.approve')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => onReject(p)}>
              {t('settings.identityTab.reject')}
            </Button>
          </div>
        </div>
      ))}
    </div>
  )
}
