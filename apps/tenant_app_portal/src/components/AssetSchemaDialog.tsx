import { Trans, useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table2, Database } from 'lucide-react'
import {
  resolveAssetDescription,
  updateAssetMetaOverride,
  type AssetMetadata,
} from '@/lib/dataSourceApi'
import { useEffect, useMemo, useState } from 'react'
import { useNotification } from '@/hooks/useNotification'
import { formatDate } from '@/lib/dateTime'

i18n.addResourceBundle('en', 'translation', {
  components: {
    assetSchemaDialog: {
      title: 'Asset Schema',
      assetDescription: 'Schema for <1>{{name}}</1>',
      assetType: 'Type',
      rowCount: '{{count}} rows',
      columns: '{{count}} columns',
      createdAt: 'Created At',
      description: 'Description',
      descPlaceholder: 'Enter description...',
      descUpdated: 'Description updated',
      updateFailed: 'Failed to update',
      sourceInfo: 'Source Info',
      columnDefs: 'Column Definitions',
      colName: 'Name',
      colType: 'Type',
      colNullable: 'Nullable',
      colDescription: 'Description',
      colDescPlaceholder: 'Enter column description...',
      noColumns: 'No columns',
      cancel: 'Cancel',
      save: 'Save',
      edit: 'Edit',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    assetSchemaDialog: {
      title: '资产 Schema',
      assetDescription: '<1>{{name}}</1> 的 Schema',
      assetType: '类型',
      rowCount: '{{count}} 行',
      columns: '{{count}} 列',
      createdAt: '创建时间',
      description: '描述',
      descPlaceholder: '输入描述...',
      descUpdated: '描述已更新',
      updateFailed: '更新失败',
      sourceInfo: '源信息',
      columnDefs: '列定义',
      colName: '名称',
      colType: '类型',
      colNullable: '可空',
      colDescription: '描述',
      colDescPlaceholder: '输入列描述...',
      noColumns: '暂无列',
      cancel: '取消',
      save: '保存',
      edit: '编辑',
    },
  },
}, true, true)

interface AssetSchemaDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  asset: AssetMetadata
  onUpdated?: (asset: AssetMetadata) => void
}

export default function AssetSchemaDialog({
  open,
  onOpenChange,
  asset,
  onUpdated,
}: AssetSchemaDialogProps) {
  const { t } = useTranslation()
  const columns = asset.columns || []
  const sourceInfo = asset.source_info || {}
  const { showSuccess, showError } = useNotification()
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [draftDescription, setDraftDescription] = useState('')
  const [draftColumnDescriptions, setDraftColumnDescriptions] = useState<Record<string, string>>({})

  const baseDescription = asset.meta?.description || ''
  const baseColumnDescriptions = asset.meta?.column_description || {}

  const resolvedDescription = useMemo(() => resolveAssetDescription(asset) || '', [asset])

  useEffect(() => {
    if (!open) {
      setIsEditing(false)
    }
    const nextDescription = resolvedDescription
    const nextColumnDescriptions: Record<string, string> = {}
    for (const column of columns) {
      const resolved =
        asset.meta_override?.column_description?.[column.name] ||
        asset.meta?.column_description?.[column.name] ||
        column.description ||
        ''
      nextColumnDescriptions[column.name] = resolved
    }
    setDraftDescription(nextDescription)
    setDraftColumnDescriptions(nextColumnDescriptions)
  }, [asset, columns, open, resolvedDescription])

  const getDataTypeBadge = (dataType: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
      integer: 'default',
      float: 'secondary',
      text: 'outline',
      boolean: 'destructive',
      date: 'default',
      datetime: 'secondary',
      json: 'outline',
    }
    const variant = variants[dataType.toLowerCase()] || 'outline'
    return (
      <Badge variant={variant} className="font-mono text-xs">
        {dataType.toUpperCase()}
      </Badge>
    )
  }

  const handleSave = async () => {
    try {
      setIsSaving(true)
      const normalizedDescription = draftDescription.trim()
      const normalizedBaseDescription = baseDescription.trim()
      const descriptionPayload =
        normalizedDescription === normalizedBaseDescription ? '' : draftDescription

      const columnDescriptionPayload: Record<string, string | null> = {}
      for (const column of columns) {
        const current = (draftColumnDescriptions[column.name] || '').trim()
        const base = (baseColumnDescriptions[column.name] || '').trim()
        columnDescriptionPayload[column.name] = current === base ? null : draftColumnDescriptions[column.name] || ''
      }

      const updated = await updateAssetMetaOverride(asset.data_source_id, asset.id, {
        description: descriptionPayload,
        column_description: columnDescriptionPayload,
      })
      showSuccess(t('components.assetSchemaDialog.descUpdated'))
      setIsEditing(false)
      onUpdated?.(updated)
    } catch (error: any) {
      showError(error.response?.data?.detail || t('components.assetSchemaDialog.updateFailed'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 justify-between">
            <span className="flex items-center gap-2">
              <Database className="w-5 h-5" />
               {t('components.assetSchemaDialog.title')}
            </span>
            <div className="flex items-center gap-2">
              {isEditing ? (
                <>
                  <Button variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={isSaving}>
                    {t('components.assetSchemaDialog.cancel')}
                  </Button>
                  <Button size="sm" onClick={handleSave} disabled={isSaving}>
                    {isSaving ? t('common.loading') : t('components.assetSchemaDialog.save')}
                  </Button>
                </>
              ) : (
                <Button size="sm" variant="outline" onClick={() => setIsEditing(true)}>
                  {t('components.assetSchemaDialog.edit')}
                </Button>
              )}
            </div>
          </DialogTitle>
          <DialogDescription>
            <Trans i18nKey="components.assetSchemaDialog.assetDescription" values={{ name: asset.asset_name }} />
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 flex-1 overflow-auto">
          {/* Metadata Summary */}
          <div className="grid grid-cols-2 gap-4 p-4 bg-muted/50 rounded-lg border">
            <div>
              <p className="text-xs text-muted-foreground mb-1">{t('components.assetSchemaDialog.assetType')}</p>
              <Badge variant="default">
                {asset.asset_type.replace('_', ' ').toUpperCase()}
              </Badge>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">{t('components.assetSchemaDialog.rowCount', { count: 0 }).split(':')[0]}</p>
              <p className="text-sm font-medium">
                {t('components.assetSchemaDialog.rowCount', { count: asset.row_count || 0 })}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">{t('components.assetSchemaDialog.columns', { count: 0 }).split(':')[0]}</p>
              <p className="text-sm font-medium">{t('components.assetSchemaDialog.columns', { count: columns.length })}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">{t('components.assetSchemaDialog.createdAt')}</p>
              <p className="text-sm font-medium">{formatDate(asset.created_at)}</p>
            </div>
          </div>

          {/* Description */}
          {(isEditing || resolvedDescription) && (
            <div className="p-4 bg-muted/20 rounded-lg border">
              <p className="text-xs text-muted-foreground mb-1">{t('components.assetSchemaDialog.description')}</p>
              {isEditing ? (
                <Textarea
                  value={draftDescription}
                  onChange={(event) => setDraftDescription(event.target.value)}
                  placeholder={t('components.assetSchemaDialog.descPlaceholder')}
                  className="min-h-[80px]"
                />
              ) : (
                <p className="text-sm">{resolvedDescription}</p>
              )}
            </div>
          )}

          {/* Source Info */}
          {Object.keys(sourceInfo).length > 0 && (
            <div className="p-4 bg-muted/20 rounded-lg border">
              <p className="text-xs text-muted-foreground mb-2">{t('components.assetSchemaDialog.sourceInfo')}</p>
              <div className="space-y-1">
                {Object.entries(sourceInfo).map(([key, value]) => (
                  <div key={key} className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">{key}:</span>
                    <span className="font-mono">{String(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Column Schema */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Table2 className="w-4 h-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">{t('components.assetSchemaDialog.columnDefs')}</h3>
              <Badge variant="outline" className="ml-auto">
                {t('components.assetSchemaDialog.columns', { count: columns.length })}
              </Badge>
            </div>
            
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="h-9 w-[50px]">#</TableHead>
                    <TableHead className="h-9 w-[200px]">{t('components.assetSchemaDialog.colName')}</TableHead>
                    <TableHead className="h-9 w-[120px]">{t('components.assetSchemaDialog.colType')}</TableHead>
                    <TableHead className="h-9 w-[80px]">{t('components.assetSchemaDialog.colNullable')}</TableHead>
                    <TableHead className="h-9">{t('components.assetSchemaDialog.colDescription')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {columns.length === 0 ? (
                    <TableRow>
                        <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                         {t('components.assetSchemaDialog.noColumns')}
                        </TableCell>
                    </TableRow>
                  ) : (
                    columns.map((column, index) => (
                      <TableRow key={index}>
                        <TableCell className="py-2 text-xs text-muted-foreground">
                          {index + 1}
                        </TableCell>
                        <TableCell className="py-2 font-mono text-sm font-medium">
                          {column.name}
                        </TableCell>
                        <TableCell className="py-2">
                          {getDataTypeBadge(column.data_type)}
                        </TableCell>
                        <TableCell className="py-2">
                          {column.nullable !== false ? (
                            <Badge variant="outline" className="text-xs">
                              YES
                            </Badge>
                          ) : (
                            <Badge variant="secondary" className="text-xs">
                              NO
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="py-2 text-sm text-muted-foreground">
                          {isEditing ? (
                            <Input
                              value={draftColumnDescriptions[column.name] || ''}
                              onChange={(event) =>
                                setDraftColumnDescriptions((prev) => ({
                                  ...prev,
                                  [column.name]: event.target.value,
                                }))
                              }
                              placeholder={t('components.assetSchemaDialog.colDescPlaceholder')}
                            />
                          ) : (
                            column.description || '-'
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
