import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import EmptyState from '@/components/EmptyState'
import DashboardGrid from '@/components/dashboard/DashboardGrid'
import DashboardHeader from '@/components/dashboard/DashboardHeader'
import FilterBar from '@/components/dashboard/FilterBar'
import FilterEditor from '@/components/dashboard/FilterEditor'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import WidgetEditor from '@/components/dashboard/WidgetEditor'
import { Button } from '@/components/ui/button'
import { ResizeHandle } from '@/components/ui/ResizeHandle'
import {
  useCreateDashboardFilter,
  useDashboard,
  useDashboardEditor,
  useRemoveDashboardFilter,
  useRemoveDashboardWidget,
  useUpdateDashboard,
  useUpdateDashboardFilter,
  useUpdateDashboardWidget,
} from '@/hooks/useDashboard'
import { useDataSources } from '@/hooks/useDataSources'
import { useResizable } from '@/hooks/useResizable'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import type { DashboardConfig, DashboardFilter } from '@/lib/dashboardApi'
import { getDashboardPeriodLabel } from '@/lib/dashboardPeriod'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Share2 } from 'lucide-react'

i18n.addResourceBundle('en', 'translation', {
  dashboard: {
    newFilter: 'New Filter',
    share: 'Share',
    editMode: 'Edit Mode',
    previewMode: 'Preview Mode',
    switchToPreview: 'Preview',
    switchToEdit: 'Edit',
    loadFailed: 'Could not load this dashboard',
    loadFailedHint: 'It may have been deleted, or you do not have access. Return to the dashboard list.',
    backToDashboards: 'Back to dashboards',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  dashboard: {
    newFilter: '新建筛选器',
    share: '分享',
    editMode: '编辑模式',
    previewMode: '预览模式',
    switchToPreview: '切换预览',
    switchToEdit: '编辑模式',
    loadFailed: '无法加载此仪表盘',
    loadFailedHint: '仪表盘可能已删除，或你没有访问权限。请返回仪表盘列表。',
    backToDashboards: '返回仪表盘列表',
  }
}, true, true)

/**
 * Clean Dashboard Embed Page - for iframe embedding
 *
 * This page renders ONLY the dashboard widgets without:
 * - Navigation bar
 * - Sidebar
 * - Menu elements
 * - Layout wrapper
 *
 * Perfect for embedding in iframes within Workbench or other pages.
 */
export default function DashboardEmbedPage() {
  const { t } = useTranslation()
  const params = useParams()
  const dashboardId = Number(params.dashboardId)

  const { data: dashboard, isLoading, error } = useDashboard(dashboardId)
  const { mutateAsync: updateDashboardBase } = useUpdateDashboard()
  const { mutateAsync: updateDashboardWidget } = useUpdateDashboardWidget()
  const { mutateAsync: removeDashboardWidget } = useRemoveDashboardWidget()
  const { mutateAsync: createDashboardFilter } = useCreateDashboardFilter()
  const { mutateAsync: updateDashboardFilter } = useUpdateDashboardFilter()
  const { mutateAsync: removeDashboardFilter } = useRemoveDashboardFilter()
  const { dataSources, fetchDataSources } = useDataSources()

  const [selectedWidgetId, setSelectedWidgetId] = useState<string | null>(null)
  const [selectedFilterId, setSelectedFilterId] = useState<string | null>(null)
  const [newFilterId, setNewFilterId] = useState<string | null>(null)
  const [selectedFilterDraft, setSelectedFilterDraft] = useState<DashboardFilter | null>(null)
  const [selectedFilterOriginal, setSelectedFilterOriginal] = useState<DashboardFilter | null>(null)
  const [draftConfig, setDraftConfig] = useState<DashboardConfig | null>(null)
  const [isEditing, setIsEditing] = useState(true)
  const [isDragging, setIsDragging] = useState(false)
  const [editorWidth, setEditorWidth] = useState(360)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)

  const {
    isDragging: isEditorDragging,
    handleMouseDown: handleEditorMouseDown,
    containerRef: editorContainerRef,
  } = useResizable(editorWidth, {
    minWidth: 280,
    maxWidth: 640,
    onWidthChange: setEditorWidth,
    direction: 'left',
  })

  useEffect(() => {
    setDraftConfig(null)
    setSelectedWidgetId(null)
    setSelectedFilterId(null)
    setNewFilterId(null)
    setSelectedFilterDraft(null)
    setSelectedFilterOriginal(null)
  }, [dashboardId])

  useEffect(() => {
    if (!dashboard || newFilterId) {
      return
    }
    setDraftConfig((prev) => prev ?? dashboard.config)
  }, [dashboard, newFilterId])

  useEffect(() => {
    void fetchDataSources()
  }, [fetchDataSources])

  const layout = useMemo(
    () => ({
      cols: 12,
      rows: 12,
      gap: 16,
      rowHeight: 80,
      ...draftConfig?.layout,
    }),
    [draftConfig]
  )

  const widgets = useMemo(() => draftConfig?.widgets ?? [], [draftConfig])
  const filters = useMemo(() => draftConfig?.filters ?? [], [draftConfig])

  const selectedWidget = useMemo(
    () => widgets.find((widget) => widget.id === selectedWidgetId) ?? null,
    [widgets, selectedWidgetId]
  )

  const selectedFilter = useMemo(
    () => filters.find((filter) => filter.id === selectedFilterId) ?? null,
    [filters, selectedFilterId]
  )

  useEffect(() => {
    if (!selectedFilterId) {
      setSelectedFilterDraft(null)
      setSelectedFilterOriginal(null)
      return
    }

    const nextFilter = filters.find((filter) => filter.id === selectedFilterId)
    if (nextFilter) {
      setSelectedFilterDraft(nextFilter)
      setSelectedFilterOriginal((prev) => {
        if (prev && prev.id === selectedFilterId) {
          return prev
        }
        return nextFilter
      })
    }
  }, [filters, selectedFilterId])

  const {
    handleWidgetsChange,
    handleWidgetFieldChange,
    handleSaveWidget,
    handleRemoveWidget,
    handleFiltersChange,
    handleFilterUpdate,
    handleSaveFilter,
    handleRemoveFilter,
  } = useDashboardEditor({
    dashboardId,
    dashboard,
    draftConfig,
    layout,
    widgets,
    filters,
    selectedWidgetId,
    selectedFilterId,
    selectedFilter,
    selectedFilterDraft,
    newFilterId,
    setDraftConfig,
    setSelectedWidgetId,
    setSelectedFilterId,
    setSelectedFilterDraft,
    setNewFilterId,
    updateDashboardBase,
    updateDashboardWidget,
    removeDashboardWidget,
    createDashboardFilter,
    updateDashboardFilter,
    removeDashboardFilter,
  })

  const handleEditFilter = (filterId: string) => {
    const nextFilter = filters.find((filter) => filter.id === filterId)
    if (nextFilter) {
      setSelectedFilterDraft(nextFilter)
    }
    setSelectedFilterId(filterId)
    setSelectedWidgetId(null)
    if (!isEditing) {
      setIsEditing(true)
    }
  }

  const buildParamKey = (rawId: string) => {
    const normalized = rawId.replace(/[^A-Za-z0-9_]/g, '_')
    return normalized.match(/^[A-Za-z_]/) ? normalized : `filter_${normalized}`
  }

  const handleCreateFilter = () => {
    if (!draftConfig) return
    const filterId = `filter-${Date.now()}`
    const newFilter: DashboardFilter = {
      id: filterId,
      name: t('dashboard.newFilter'),
      type: 'time_range',
      paramKey: buildParamKey(filterId),
      value: { mode: 'relative', preset: 'last_7_days' },
      required: false,
    }
    const nextFilters = [...filters, newFilter]
    setSelectedFilterId(newFilter.id)
    setNewFilterId(newFilter.id)
    setSelectedFilterDraft(newFilter)
    setSelectedWidgetId(null)
    if (!isEditing) {
      setIsEditing(true)
    }
    void handleFiltersChange(nextFilters, false)
  }

  const handleCloseFilterEditor = async () => {
    if (newFilterId && selectedFilterId === newFilterId) {
      const nextFilters = filters.filter((filter) => filter.id !== newFilterId)
      setNewFilterId(null)
      setSelectedFilterId(null)
      setSelectedFilterDraft(null)
      await handleFiltersChange(nextFilters, false)
      return
    }
    setSelectedFilterId(null)
    setSelectedFilterDraft(null)
  }

  const handleUpdateDashboardHeader = async (payload: { name: string; description: string }) => {
    if (!dashboard || !draftConfig) return
    await updateDashboardBase({
      id: dashboardId,
      payload: {
        title: payload.name,
        description: payload.description,
      },
      invalidateWidgetData: false,
    })
  }

  if (isLoading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-background">
        <div className="text-sm text-muted-foreground">{t('common.loading')}</div>
      </div>
    )
  }

  if (error || !dashboard) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-background">
        <EmptyState
          title={t('dashboard.loadFailed')}
          description={t('dashboard.loadFailedHint')}
          action={
            <Button variant="outline" asChild>
              <Link to="/artifacts/dashboards">{t('dashboard.backToDashboards')}</Link>
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div className="flex w-full h-full bg-background min-w-[800px]">
      {/* Clean dashboard content - no header, no wrapper, just widgets */}
      <div className="flex-1 min-w-0 overflow-auto p-4">
        <div className="mb-4 flex items-start justify-between gap-4">
          {dashboard && (
            <DashboardHeader
              dashboard={dashboard}
              periodLabel={getDashboardPeriodLabel(filters, (preset) =>
                t(`components.timeRangePicker.${preset}`)
              )}
              onUpdate={handleUpdateDashboardHeader}
            />
          )}
          <div className="flex items-center gap-3">
            <Button size="sm" variant="outline" onClick={() => setShareDialogOpen(true)}>
              <Share2 className="w-4 h-4 mr-1.5" />
              {t('dashboard.share')}
            </Button>
            <div className="text-xs text-muted-foreground">
              {isEditing ? t('dashboard.editMode') : t('dashboard.previewMode')}
            </div>
            <Button
              size="sm"
              variant={isEditing ? 'default' : 'outline'}
              onClick={() => {
                setIsEditing((prev) => !prev)
                setSelectedWidgetId(null)
              }}
            >
              {isEditing ? t('dashboard.switchToPreview') : t('dashboard.switchToEdit')}
            </Button>
          </div>
        </div>
        <div className="mb-4">
          <FilterBar
            dashboardId={dashboardId}
            filters={filters}
            isEditing={isEditing}
            selectedFilterId={selectedFilterId}
            onFiltersChange={handleFiltersChange}
            onEditFilter={handleEditFilter}
            onCreateFilter={handleCreateFilter}
          />
        </div>
        <DashboardGrid
          widgets={widgets}
          filters={filters}
          config={{
            cols: layout.cols,
            rows: layout.rows,
            gap: layout.gap,
            rowHeight: layout.rowHeight,
          }}
          dashboardId={dashboardId}
          isEditing={isEditing}
          selectedWidgetId={selectedWidgetId}
          isDragging={isDragging}
          onWidgetSelect={(widgetId) => {
            setSelectedWidgetId(widgetId)
            setSelectedFilterId(null)
            if (!isEditing) {
              setIsEditing(true)
            }
          }}
          onWidgetsChange={handleWidgetsChange}
          onDragStateChange={setIsDragging}
        />
      </div>

      {selectedWidget && isEditing ? (
        <div
          ref={editorContainerRef}
          className="relative shrink-0"
          style={{ width: `${editorWidth}px`, willChange: isEditorDragging ? 'width' : 'auto' }}
        >
          <div
            className="sticky top-3 z-30"
            style={{ height: 'calc(100vh - 24px)', width: `${editorWidth}px` }}
          >
            <WidgetEditor
              dashboardId={dashboardId}
              widget={selectedWidget}
              filters={draftConfig?.filters ?? []}
              onFieldChange={handleWidgetFieldChange}
              onSave={handleSaveWidget}
              onRemove={handleRemoveWidget}
              onClose={() => setSelectedWidgetId(null)}
              containerClassName="h-full w-full"
              containerStyle={{ height: '100%' }}
            />
            <ResizeHandle
              onMouseDown={handleEditorMouseDown}
              isDragging={isEditorDragging}
              position="left"
            />
          </div>
        </div>
      ) : (selectedFilterDraft ?? selectedFilter) && isEditing ? (
        <div
          ref={editorContainerRef}
          className="relative shrink-0"
          style={{ width: `${editorWidth}px`, willChange: isEditorDragging ? 'width' : 'auto' }}
        >
          <div
            className="sticky top-3 z-30"
            style={{ height: 'calc(100vh - 24px)', width: `${editorWidth}px` }}
          >
            <FilterEditor
              filter={(selectedFilterDraft ?? selectedFilter)!}
              dataSources={dataSources}
              allWidgets={widgets}
              originalFilter={selectedFilterOriginal ?? undefined}
              onUpdate={handleFilterUpdate}
              onSave={handleSaveFilter}
              onRemove={handleRemoveFilter}
              onClose={handleCloseFilterEditor}
              containerClassName="h-full w-full"
              containerStyle={{ height: '100%' }}
            />
            <ResizeHandle
              onMouseDown={handleEditorMouseDown}
              isDragging={isEditorDragging}
              position="left"
            />
          </div>
        </div>
      ) : null}

      <ResourceAclShareDialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        resourceType={ACL_SHARE_RESOURCE_TYPES.DASHBOARD}
        resourceId={dashboard.id}
        resourceTitle={dashboard.name}
      />
    </div>
  )
}
