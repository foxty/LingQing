import '@/components/knowledge-base/collectionSyncI18n'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { CollectionDriveSyncConnectorBody } from '@/components/knowledge-base/drive-sync/CollectionDriveSyncConnectorBody'
import { CollectionDriveSyncSetupBody } from '@/components/knowledge-base/drive-sync/CollectionDriveSyncSetupBody'
import { DriveSyncHeaderChip } from '@/components/knowledge-base/drive-sync/DriveSyncHeaderChip'
import { useCollectionDriveSync } from '@/hooks/useCollectionDriveSync'
import { useFormatUserDateTime } from '@/hooks/useUserDateTimeFormat'
import { popoverChipTriggerClass } from '@/lib/uiControlPatterns'
import { Loader2 } from 'lucide-react'

interface CollectionDriveSyncPopoverProps {
  collectionId: number
  documentCount?: number
  canManageCollection?: boolean
}

export default function CollectionDriveSyncPopover({
  collectionId,
  documentCount = 0,
  canManageCollection = false,
}: CollectionDriveSyncPopoverProps) {
  const { t } = useTranslation()
  const formatUserDateTime = useFormatUserDateTime()
  const [open, setOpen] = useState(false)
  const sync = useCollectionDriveSync({
    collectionId,
    documentCount,
    canManageCollection,
    popoverOpen: open,
  })

  if (!sync.showTrigger) {
    return null
  }

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={popoverChipTriggerClass}
            aria-label={t('collectionSync.syncedFromDrive')}
          >
            <DriveSyncHeaderChip state={sync.triggerState} t={t} />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-96 max-w-[calc(100vw-2rem)] p-4" align="start">
          <p className="text-sm font-medium mb-3">{t('collectionSync.syncedFromDrive')}</p>
          {sync.connectorLoading ? (
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('common.loading')}
            </span>
          ) : sync.connector ? (
            <CollectionDriveSyncConnectorBody
              connector={sync.connector}
              connectorOwnerLabel={sync.connectorOwnerLabel}
              canManageConnector={sync.canManageConnector}
              isBusy={sync.isBusy}
              syncPending={sync.syncPending}
              resumePending={sync.resumePending}
              pausePending={sync.pausePending}
              authorizePending={sync.authorizePending}
              formatLastSynced={formatUserDateTime}
              onSyncNow={sync.syncNow}
              onResume={sync.resume}
              onPause={sync.pauseFolderSync}
              onConnect={() => void sync.connect()}
              onDisconnectFolder={() => sync.setDisconnectOpen(true)}
            />
          ) : (
            <CollectionDriveSyncSetupBody
              activeConnection={sync.activeConnection}
              userId={sync.user?.id}
              username={sync.user?.username}
              isBusy={sync.isBusy}
              authorizePending={sync.authorizePending}
              pickingFolder={sync.pickingFolder}
              onConnect={() => void sync.connect()}
              onBindFolder={sync.bindFolderClick}
              onDisconnectAccount={() => sync.setDisconnectAccountOpen(true)}
            />
          )}
        </PopoverContent>
      </Popover>

      <ConfirmationDialog<boolean>
        open={sync.disconnectOpen}
        item={sync.disconnectOpen}
        isLoading={sync.disconnectFolderPending}
        title={t('collectionSync.confirmDisconnectFolder')}
        description={() => t('collectionSync.confirmDisconnectFolderDesc')}
        confirmText={t('collectionSync.disconnectFolder')}
        isDangerous
        onConfirm={() => void sync.disconnectFolder()}
        onCancel={() => sync.setDisconnectOpen(false)}
      />
      <ConfirmationDialog<boolean>
        open={sync.disconnectAccountOpen}
        item={sync.disconnectAccountOpen}
        isLoading={sync.disconnectAccountPending}
        title={t('collectionSync.confirmDisconnectAccount')}
        description={() => t('collectionSync.confirmDisconnectAccountDesc')}
        confirmText={t('collectionSync.disconnectAccount')}
        isDangerous
        onConfirm={() => void sync.disconnectAccount()}
        onCancel={() => sync.setDisconnectAccountOpen(false)}
      />
      <ConfirmationDialog<boolean>
        open={sync.bindFolderOpen}
        item={sync.bindFolderOpen}
        isLoading={sync.pickingFolder || sync.createConnectorPending}
        title={t('collectionSync.confirmBindFolder')}
        description={() => t('collectionSync.confirmBindFolderDesc', { count: documentCount })}
        confirmText={t('collectionSync.bindFolder')}
        onConfirm={() => void sync.bindFolder()}
        onCancel={() => sync.setBindFolderOpen(false)}
      />
    </>
  )
}