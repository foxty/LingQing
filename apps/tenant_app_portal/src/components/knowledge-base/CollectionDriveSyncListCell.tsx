import '@/components/knowledge-base/collectionSyncI18n'
import { StatusChip } from '@/components/StatusChip'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useFormatUserDateTime } from '@/hooks/useUserDateTimeFormat'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { collectionListSyncBadge, collectionListSyncInfo } from '@/lib/driveSyncDisplay'
import { iconButtonDenseClass } from '@/lib/uiControlPatterns'
import { driveFolderViewUrl } from '@/lib/documentsApi'
import { Cloud, ExternalLink, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface CollectionDriveSyncListCellProps {
  collection: DocumentCollection
}

export default function CollectionDriveSyncListCell({ collection }: CollectionDriveSyncListCellProps) {
  const { t } = useTranslation()
  const formatUserDateTime = useFormatUserDateTime()

  if (!collection.has_drive_sync) {
    return <span className="text-sm text-muted-foreground">—</span>
  }

  const syncBadge = collectionListSyncBadge(collection)
  const syncInfo = collectionListSyncInfo(collection, t, formatUserDateTime)

  return (
    <div className="space-y-0.5 min-w-0">
      <div className="flex items-center gap-0.5 min-w-0">
        <StatusChip
          variant={syncBadge.variant}
          size="table"
          icon={<Cloud className="h-3 w-3 shrink-0" aria-hidden />}
        >
          <span className="truncate">{t(syncBadge.labelKey)}</span>
        </StatusChip>
        <Popover>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={iconButtonDenseClass}
              aria-label={t('collectionSync.listInfoAria')}
            >
              <Info
                className={`h-3.5 w-3.5 ${collection.last_sync_error ? 'text-destructive' : ''}`}
                aria-hidden
              />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-80 p-3 text-sm" align="start">
            <div className="space-y-2">
              <p className="font-medium leading-tight">{t(syncInfo.headingKey)}</p>
              <p
                className={
                  syncInfo.destructive
                    ? 'text-destructive text-xs leading-snug break-words'
                    : 'text-muted-foreground text-xs leading-snug'
                }
              >
                {syncInfo.body}
              </p>
              <p className="text-xs text-muted-foreground border-t pt-2">
                {t('collectionSync.listInfoManageHint')}
              </p>
            </div>
          </PopoverContent>
        </Popover>
      </div>
      {collection.sync_folder_name ? (
        collection.sync_folder_id ? (
          <a
            href={driveFolderViewUrl(collection.sync_folder_id)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 max-w-full text-xs text-primary hover:underline truncate"
            title={t('collectionSync.listOpenDriveFolder', { name: collection.sync_folder_name })}
            onClick={(e) => e.stopPropagation()}
          >
            <span className="truncate">
              {t('collectionSync.listSyncFolder', { name: collection.sync_folder_name })}
            </span>
            <ExternalLink className="h-3 w-3 shrink-0 opacity-70" />
          </a>
        ) : (
          <p className="text-xs text-muted-foreground truncate" title={collection.sync_folder_name}>
            {t('collectionSync.listSyncFolder', { name: collection.sync_folder_name })}
          </p>
        )
      ) : null}
    </div>
  )
}