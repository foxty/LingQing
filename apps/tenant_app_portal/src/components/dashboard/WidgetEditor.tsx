import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  components: {
    widgetEditor: {
      displayConfig: 'Display',
      dataSource: 'Data Source',
      fieldMapping: 'Field Mapping',
      save: 'Save Widget',
      deleteWidget: 'Delete Widget',
      deleteConfirmTitle: 'Delete Widget',
      deleteConfirmDesc: 'Are you sure you want to delete this widget? This action cannot be undone.',
      confirmDelete: 'Delete',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    widgetEditor: {
      displayConfig: '显示配置',
      dataSource: '数据源',
      fieldMapping: '字段映射',
      save: '保存组件',
      deleteWidget: '删除组件',
      deleteConfirmTitle: '删除组件',
      deleteConfirmDesc: '确定要删除此组件吗？此操作不可撤销。',
      confirmDelete: '删除',
    },
  },
}, true, true)
import type { CSSProperties } from 'react'
import { Eye, Database, GitBranch } from 'lucide-react'
import type { DashboardFilter, DashboardWidget } from '@/lib/dashboardApi'
import DataSourceEditor from '@/components/dashboard/editors/DataSourceEditor'
import FieldMappingEditor from '@/components/dashboard/editors/FieldMappingEditor'
import DisplayConfigEditor from '@/components/dashboard/editors/DisplayConfigEditor'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { useDashboardWidgetPreview } from '@/hooks/useDashboard'
import { useConfirmation } from '@/hooks/useConfirmation'

interface WidgetEditorProps {
  dashboardId: number
  widget: DashboardWidget
  filters: DashboardFilter[]
  onFieldChange: (
    field: 'query' | 'displayConfig' | 'fieldMapping' | 'dataSourceId',
    value: any
  ) => void
  onSave: () => Promise<void>
  onRemove: () => Promise<void>
  onClose: () => void
  containerClassName?: string
  containerStyle?: CSSProperties
}

export default function WidgetEditor({
  dashboardId,
  widget,
  filters,
  onFieldChange,
  onSave,
  onRemove,
  onClose,
  containerClassName,
  containerStyle,
}: WidgetEditorProps) {
  const { t } = useTranslation()
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const {
    data: preview,
    isLoading: isPreviewLoading,
    refetch: refetchPreview,
    error: previewError,
  } = useDashboardWidgetPreview(dashboardId, widget.id, {
    query: widget.query ?? null,
    dataSourceId: widget.dataSourceId ?? null,
  })

  const removeConfirm = useConfirmation<boolean>(false)

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)
    try {
      await onSave()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setIsSaving(false)
    }
  }

  const handleRemoveClick = () => {
    removeConfirm.open(true)
  }

  const handleConfirmRemove = async () => {
    removeConfirm.setLoading(true)
    try {
      await onRemove()
      removeConfirm.close()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Remove failed')
      removeConfirm.setLoading(false)
    }
  }

  return (
    <div
      className={cn('shrink-0 border-l bg-background shadow-lg', containerClassName)}
      style={containerStyle}
    >
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="text-sm font-semibold">{t('common.edit')}: "{widget.displayConfig?.title}"</div>
        <button className="text-sm text-muted-foreground hover:text-foreground" onClick={onClose}>
          {t('common.close')}
        </button>
      </div>
      <div className="overflow-y-auto p-4 space-y-4" style={{ height: 'calc(100% - 53px)' }}>
        <Tabs defaultValue="display">
          <TabsList className="w-full grid grid-cols-3">
            <TabsTrigger value="display" className="gap-2">
              <Eye className="w-4 h-4" />
              {t('components.widgetEditor.displayConfig')}
            </TabsTrigger>
            <TabsTrigger value="datasource" className="gap-2">
              <Database className="w-4 h-4" />
              {t('components.widgetEditor.dataSource')}
            </TabsTrigger>
            <TabsTrigger value="mapping" className="gap-2">
              <GitBranch className="w-4 h-4" />
              {t('components.widgetEditor.fieldMapping')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="datasource" className="space-y-4">
            <DataSourceEditor
              widget={widget}
              filters={filters}
              preview={preview}
              isPreviewLoading={isPreviewLoading}
              previewError={previewError}
              onVerify={() => void refetchPreview()}
              onFieldChange={onFieldChange}
            />
          </TabsContent>

          <TabsContent value="mapping" className="space-y-4">
            <FieldMappingEditor
              widget={widget}
              columns={preview?.columns ?? []}
              isLoading={isPreviewLoading}
              error={previewError instanceof Error ? previewError.message : null}
              onFieldChange={onFieldChange}
            />
          </TabsContent>

          <TabsContent value="display" className="space-y-4">
            <DisplayConfigEditor
              widget={widget}
              columns={preview?.columns ?? []}
              onFieldChange={onFieldChange}
            />
          </TabsContent>
        </Tabs>

        {/* Error message */}
        {error && (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Action buttons */}
        <div className="space-y-2 pt-4 border-t">
          <Button className="w-full" onClick={handleSave} disabled={isSaving}>
            {isSaving ? `${t('common.save')}...` : t('components.widgetEditor.save')}
          </Button>
          <Button
            variant="destructive"
            onClick={handleRemoveClick}
            disabled={removeConfirm.isLoading}
            className="w-full"
          >
            {removeConfirm.isLoading ? `${t('common.delete')}...` : t('components.widgetEditor.deleteWidget')}
          </Button>
        </div>

        {/* Delete confirmation dialog */}
        {removeConfirm.isOpen && (
          <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center">
            <div className="bg-background border rounded-lg shadow-lg p-6 max-w-sm space-y-4">
              <div>
                <h2 className="text-lg font-semibold">{t('components.widgetEditor.deleteConfirmTitle')}</h2>
                <p className="text-sm text-muted-foreground mt-2">
                  {t('components.widgetEditor.deleteConfirmDesc')}
                </p>
              </div>
              <div className="flex gap-2 justify-end">
                <Button
                  variant="outline"
                  onClick={removeConfirm.close}
                  disabled={removeConfirm.isLoading}
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  variant="destructive"
                  onClick={handleConfirmRemove}
                  disabled={removeConfirm.isLoading}
                >
                  {removeConfirm.isLoading ? `${t('common.delete')}...` : t('components.widgetEditor.confirmDelete')}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
