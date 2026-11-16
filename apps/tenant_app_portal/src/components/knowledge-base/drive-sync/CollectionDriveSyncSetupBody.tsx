import { Button } from '@/components/ui/button'
import { buttonDestructiveOutlineClass } from '@/lib/uiControlPatterns'
import { cn } from '@/lib/utils'
import { FolderSync, Link2, Loader2, Unlink } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function CollectionDriveSyncSetupBody({
  activeConnection,
  userId,
  username,
  isBusy,
  authorizePending,
  pickingFolder,
  onConnect,
  onBindFolder,
  onDisconnectAccount,
}: {
  activeConnection: { id: number; account_email: string | null } | undefined
  userId: number | undefined
  username: string | null | undefined
  isBusy: boolean
  authorizePending: boolean
  pickingFolder: boolean
  onConnect: () => void
  onBindFolder: () => void
  onDisconnectAccount: () => void
}) {
  const { t } = useTranslation()

  if (!activeConnection) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">{t('collectionSync.setupHint')}</p>
        <Button type="button" size="sm" variant="default" className="h-8 gap-1.5" onClick={onConnect} disabled={isBusy}>
          {authorizePending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <>
              <Link2 className="h-3.5 w-3.5" />
              {t('collectionSync.connect')}
            </>
          )}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t('collectionSync.chooseFolderHint')}</p>
      <p className="text-xs text-muted-foreground">
        {t('collectionSync.connectedAs', {
          user: username ?? `#${userId ?? '?'}`,
          account: activeConnection.account_email ?? `#${activeConnection.id}`,
        })}
      </p>
      <div className="grid grid-cols-2 gap-1.5">
        <Button
          type="button"
          size="sm"
          variant="default"
          className="h-8 min-w-0 gap-1.5"
          onClick={onBindFolder}
          disabled={isBusy}
        >
          {pickingFolder ? (
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
          ) : (
            <>
              <FolderSync className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{t('collectionSync.bindFolder')}</span>
            </>
          )}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={cn('h-8 min-w-0 gap-1.5', buttonDestructiveOutlineClass)}
          onClick={onDisconnectAccount}
          disabled={isBusy}
        >
          <Unlink className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{t('collectionSync.disconnectAccount')}</span>
        </Button>
      </div>
    </div>
  )
}