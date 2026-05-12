import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { RefreshCw } from 'lucide-react'
import { useCallback, useState } from 'react'

import { Button } from '@/components/ui/button'
import ChartWidget from './ChartWidget'
import MetricWidget from './MetricWidget'
import TableWidget from './TableWidget'

import { useDashboardWidgetData } from '@/hooks/useDashboard'
import type { DashboardFilter, DashboardWidget } from '@/lib/dashboardApi'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      widgetRenderer: {
        refresh: 'Refresh widget data',
        loading: 'Loading data…',
        loadFailed: 'Could not load this widget',
        loadFailedHint: 'Check the query or refresh to try again.',
        noData: 'No rows for this period',
        noDataHint: 'Change the time range or refresh.',
        unsupported: 'This widget type is not supported.',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    components: {
      widgetRenderer: {
        refresh: '刷新组件数据',
        loading: '正在加载数据…',
        loadFailed: '无法加载此组件',
        loadFailedHint: '检查查询，或刷新后重试。',
        noData: '当前周期没有数据',
        noDataHint: '调整时间范围或刷新。',
        unsupported: '不支持此组件类型。',
      },
    },
  },
  true,
  true
)

interface WidgetRendererProps {
  dashboardId: number
  widget: DashboardWidget
  filters?: DashboardFilter[]
  refetchInterval?: number
  isEditing?: boolean
  isDragging?: boolean
  isSelected?: boolean
  onEdit?: (widgetId: string) => void
}

export default function WidgetRenderer({
  dashboardId,
  widget,
  filters = [],
  refetchInterval,
  isEditing = false,
  isDragging = false,
  isSelected = false,
  onEdit,
}: WidgetRendererProps) {
  const { t } = useTranslation()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const { data, isLoading, error, refetch } = useDashboardWidgetData(dashboardId, widget.id, {
    refetchInterval,
    filters,
    query: widget.query,
  })

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true)
    try {
      await refetch()
    } catch {
      // Errors are surfaced in UI state from the hook
    } finally {
      setIsRefreshing(false)
    }
  }, [refetch])

  const renderWidgetContent = useCallback(() => {
    if (widget.type === 'metric' && data) {
      return <MetricWidget widget={widget} data={data} />
    }

    if (widget.type === 'table' && data) {
      return <TableWidget data={data} displayConfig={widget.displayConfig?.table} />
    }

    if (widget.type === 'chart' && data) {
      return <ChartWidget widget={widget} data={data} />
    }

    return <div className="text-sm text-muted-foreground">{t('components.widgetRenderer.unsupported')}</div>
  }, [widget, data, t])

  const RefreshButton = () => (
    <Button
      size="sm"
      variant="ghost"
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        handleRefresh()
      }}
      disabled={isRefreshing}
      className="widget-action-button h-8 w-8 p-0 bg-background/95 hover:bg-background shadow-sm"
      title={t('components.widgetRenderer.refresh')}
    >
      <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
    </Button>
  )

  return (
    <div
      className={`relative border bg-card p-2 transition-shadow h-full ${
        isSelected ? 'ring-2 ring-primary/70 shadow-lg' : 'hover:shadow-md'
      }`}
      onClick={() => {
        if (!isEditing || isDragging) {
          return
        }
        onEdit?.(widget.id)
      }}
    >
      {isEditing && (
        <div
          className="widget-drag-area absolute inset-x-0 top-0 z-40 h-8 cursor-grab active:cursor-grabbing"
          aria-label="Drag widget"
        />
      )}
      <div className="flex flex-col h-full">
        {/* Action buttons - top-right corner */}
        <div className="absolute top-0 right-0 flex gap-1 z-50">
          <div className="flex gap-1">
            <RefreshButton />
          </div>
        </div>

        {isLoading && (
          <div className="flex h-full items-center justify-center">
            <div className="animate-pulse p-4 text-sm text-muted-foreground">
              {t('components.widgetRenderer.loading')}
            </div>
          </div>
        )}

        {error && (
          <div className="flex h-full items-center justify-center">
            <div className="space-y-1 text-center">
              <p className="text-sm font-medium text-destructive">
                {t('components.widgetRenderer.loadFailed')}
              </p>
              <p className="text-xs text-muted-foreground">
                {error instanceof Error ? error.message : t('components.widgetRenderer.loadFailedHint')}
              </p>
            </div>
          </div>
        )}

        {data && data.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="space-y-1 text-center">
              <p className="text-sm font-medium">{t('components.widgetRenderer.noData')}</p>
              <p className="text-xs text-muted-foreground">{t('components.widgetRenderer.noDataHint')}</p>
            </div>
          </div>
        )}

        {!isLoading && !error && data && data.length > 0 ? (
          <div className="flex-1 overflow-auto">{renderWidgetContent()}</div>
        ) : null}
      </div>
    </div>
  )
}
