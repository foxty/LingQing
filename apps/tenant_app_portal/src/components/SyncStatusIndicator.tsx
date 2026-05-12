import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

i18n.addResourceBundle('en', 'translation', {
  components: {
    syncStatusIndicator: {
      title: 'Sync Status',
      synced: 'Synced',
      unsynced: 'Not synced',
      error: 'Error',
      clickForDetails: 'Click for details',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    syncStatusIndicator: {
      title: '同步状态',
      synced: '已同步',
      unsynced: '未同步',
      error: '错误',
      clickForDetails: '点击查看详情',
    },
  },
}, true, true)
import { formatDate } from '@/lib/dateTime'

interface SyncStatusIndicatorProps {
  syncedAt?: string | null
  error?: string | null
  title?: string
  unsyncedText?: string
}

export default function SyncStatusIndicator({
  syncedAt,
  error,
  title,
  unsyncedText,
}: SyncStatusIndicatorProps) {
  const { t } = useTranslation()
  const resolvedTitle = title ?? t('components.syncStatusIndicator.title')
  const resolvedUnsyncedText = unsyncedText ?? t('components.syncStatusIndicator.unsynced')
  const hasSynced = Boolean(syncedAt)
  const hasError = Boolean(error)

  if (!hasSynced && !hasError) {
    return <span className="text-xs text-muted-foreground">{resolvedUnsyncedText}</span>
  }

  const indicatorColor = hasError ? 'text-destructive' : 'text-success'
  const indicatorBgColor = hasError
    ? 'bg-destructive/10 hover:bg-destructive/20'
    : 'bg-success/10 hover:bg-success/20'
  const indicatorBorder = hasError ? 'border-destructive/30' : 'border-success/30'

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-xs font-medium cursor-pointer transition-colors ${indicatorColor} ${indicatorBgColor} ${indicatorBorder}`}
          title={t('components.syncStatusIndicator.clickForDetails')}
          type="button"
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${hasError ? 'bg-destructive' : 'bg-success'}`}
          />
          {hasError ? t('components.syncStatusIndicator.error') : t('components.syncStatusIndicator.synced')}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-3" align="start">
        <div className="space-y-2 text-sm">
          <div className="font-medium mb-2.5">{resolvedTitle}</div>

          <div className="flex items-start gap-2">
            <div
              className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
                hasError ? 'bg-destructive/20' : hasSynced ? 'bg-success/20' : 'bg-muted'
              }`}
            >
              <span
                className={`text-xs font-bold ${
                  hasError
                    ? 'text-destructive'
                    : hasSynced
                      ? 'text-success'
                      : 'text-muted-foreground'
                }`}
              >
                {hasError ? '!' : hasSynced ? '✓' : '○'}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              {hasSynced && (
                <div className="text-xs text-muted-foreground">
                  {formatDate(syncedAt || undefined)}
                </div>
              )}
              {hasError && <div className="text-xs text-destructive break-words">{error}</div>}
              {!hasSynced && <div className="text-xs text-muted-foreground">{resolvedUnsyncedText}</div>}
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
