import { Button } from '@/components/ui/button'
import {
  buttonCompactActionClass,
  buttonDestructiveOutlineClass,
} from '@/lib/uiControlPatterns'
import { cn } from '@/lib/utils'
import { resolveDriveSyncUiState } from '@/lib/driveSyncDisplay'
import { driveFolderViewUrl } from '@/lib/documentsApi'
import type { SyncConnector } from '@/lib/documentSyncApi'
import { CONNECTOR_STATUS } from '@/lib/documentSyncConstants'
import { ExternalLink, Link2, Loader2, Pause, RefreshCw, Unlink } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function CollectionDriveSyncConnectorBody({
  connector,
  connectorOwnerLabel,
  canManageFolderSync,
  canManageConnectionAccount,
  isBusy,
  syncPending,
  resumePending,
  pausePending,
  authorizePending,
  formatLastSynced,
  onSyncNow,
  onResume,
  onPause,
  onConnect,
  onDisconnectFolder,
}: {
  connector: SyncConnector
  connectorOwnerLabel: string | null
  canManageFolderSync: boolean
  canManageConnectionAccount: boolean
  isBusy: boolean
  syncPending: boolean
  resumePending: boolean
  pausePending: boolean
  authorizePending: boolean
  formatLastSynced: (iso: string) => string
  onSyncNow: () => void
  onResume: () => void
  onPause: () => void
  onConnect: () => void
  onDisconnectFolder: () => void
}) {
  const { t } = useTranslation()
  const state = resolveDriveSyncUiState(connector)
  const lastSyncedLine = connector.last_synced_at
    ? t('collectionSync.lastSynced', { time: formatLastSynced(connector.last_synced_at) })
    : t('collectionSync.neverSynced')

  const summary =
    state === 'active-error' && connector.last_sync_error
      ? connector.last_sync_error
      : state === 'stopped-paused'
        ? t('collectionSync.stoppedFolderSyncOff')
        : state === 'stopped-disconnected'
          ? t('collectionSync.stoppedAccountDisconnected')
          : null

  return (
    <div className="space-y-3">
      <a
        href={driveFolderViewUrl(connector.source_folder_id)}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
      >
        {connector.source_folder_name}
        <ExternalLink className="h-3.5 w-3.5 opacity-70" />
      </a>
      {connectorOwnerLabel ? (
        <p className="text-xs text-muted-foreground">{connectorOwnerLabel}</p>
      ) : null}
      <p className="text-xs text-muted-foreground">{lastSyncedLine}</p>
      {summary ? (
        <p
          className={`text-xs leading-snug break-words ${
            state === 'active-error' || state === 'stopped-disconnected'
              ? 'text-destructive'
              : 'text-amber-800 dark:text-amber-200'
          }`}
        >
          {summary}
        </p>
      ) : null}
      {canManageFolderSync ? (
        <div className="border-t pt-3">
          {connector.status === CONNECTOR_STATUS.ACTIVE ? (
            <div className="grid grid-cols-3 gap-1.5">
              <Button
                type="button"
                size="sm"
                variant="default"
                className={buttonCompactActionClass}
                onClick={onSyncNow}
                disabled={isBusy}
              >
                {syncPending ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                ) : (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{t('collectionSync.syncNow')}</span>
                  </>
                )}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={buttonCompactActionClass}
                onClick={onPause}
                disabled={isBusy}
              >
                {pausePending ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                ) : (
                  <>
                    <Pause className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{t('collectionSync.pauseSync')}</span>
                  </>
                )}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={cn(buttonCompactActionClass, buttonDestructiveOutlineClass)}
                onClick={onDisconnectFolder}
                disabled={isBusy}
              >
                <Unlink className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{t('collectionSync.disconnectFolder')}</span>
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-1.5">
              {state === 'stopped-paused' ? (
                <Button
                  type="button"
                  size="sm"
                  variant="default"
                  className="h-8 gap-1.5"
                  onClick={onResume}
                  disabled={isBusy}
                >
                  {resumePending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <>
                      <RefreshCw className="h-3.5 w-3.5" />
                      {t('collectionSync.resumeSync')}
                    </>
                  )}
                </Button>
              ) : null}
              {state === 'stopped-disconnected' ? (
                canManageConnectionAccount ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="default"
                    className="h-8 gap-1.5"
                    onClick={onConnect}
                    disabled={isBusy}
                  >
                    {authorizePending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <>
                        <Link2 className="h-3.5 w-3.5" />
                        {t('collectionSync.connect')}
                      </>
                    )}
                  </Button>
                ) : (
                  <p className="col-span-2 text-xs leading-snug text-muted-foreground">
                    {t('collectionSync.accountOwnerReconnectHint', {
                      owner: connectorOwnerLabel ?? t('collectionSync.connectionOwnerFallback'),
                    })}
                  </p>
                )
              ) : null}
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={cn('h-8 gap-1.5', buttonDestructiveOutlineClass)}
                onClick={onDisconnectFolder}
                disabled={isBusy}
              >
                <Unlink className="h-3.5 w-3.5" />
                {t('collectionSync.disconnectFolder')}
              </Button>
            </div>
          )}
        </div>
      ) : (
        <p className="border-t pt-3 text-xs leading-snug text-muted-foreground">
          {t('collectionSync.syncViewOnlyHint', {
            owner: connectorOwnerLabel ?? t('collectionSync.connectionOwnerFallback'),
          })}
        </p>
      )}
    </div>
  )
}