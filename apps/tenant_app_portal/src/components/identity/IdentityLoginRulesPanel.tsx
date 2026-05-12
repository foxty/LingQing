import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Trash2 } from 'lucide-react'
import type { LoginDomain } from '@/lib/identityApi'

type Props = {
  domains: LoginDomain[]
  newDomain: string
  onNewDomainChange: (value: string) => void
  onAddDomain: () => void
  onRemoveDomain: (domain: LoginDomain) => void
  forceSso: boolean
  breakGlassCount: number
  onToggleForceSso: (value: boolean) => void
  t: (key: string, options?: Record<string, unknown>) => string
}

export default function IdentityLoginRulesPanel({
  domains,
  newDomain,
  onNewDomainChange,
  onAddDomain,
  onRemoveDomain,
  forceSso,
  breakGlassCount,
  onToggleForceSso,
  t,
}: Props) {
  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div>
          <Label>{t('settings.identityTab.loginDomains')}</Label>
          <p className="mt-1 text-xs text-muted-foreground">
            {t('settings.identityTab.loginAccessDesc')}
          </p>
        </div>
        <div className="flex gap-2">
          <Input
            value={newDomain}
            onChange={(e) => onNewDomainChange(e.target.value)}
            placeholder={t('settings.identityTab.domainPlaceholder')}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                onAddDomain()
              }
            }}
          />
          <Button onClick={onAddDomain} variant="outline">
            {t('settings.identityTab.addDomain')}
          </Button>
        </div>
        <div className="space-y-2">
          {domains.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t('settings.identityTab.loginDomainsEmptyHint')}
            </p>
          ) : (
            domains.map((d) => (
              <div key={d.id} className="flex items-center justify-between rounded border px-3 py-2">
                <span className="text-sm">{d.domain}</span>
                <Button variant="ghost" size="sm" onClick={() => onRemoveDomain(d)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="space-y-3 border-t pt-6">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-1">
            <Label>{t('settings.identityTab.forceSso')}</Label>
            <p className="text-sm text-muted-foreground">
              {t('settings.identityTab.forceSsoDesc')}
            </p>
            <p className="text-xs text-muted-foreground">
              {t('settings.identityTab.breakGlassCount', { count: breakGlassCount })}
            </p>
            {breakGlassCount === 0 ? (
              <p className="text-xs text-warn">{t('settings.identityTab.forceSsoNoBreakGlass')}</p>
            ) : null}
          </div>
          <Switch checked={forceSso} onCheckedChange={onToggleForceSso} />
        </div>
      </section>
    </div>
  )
}
