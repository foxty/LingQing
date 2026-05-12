import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    selectAssetsDialog: {
      title: 'Select Assets',
      description: 'Select assets for {{name}}',
      searchPlaceholder: 'Search assets...',
      allTypes: 'All',
      table: 'Table',
      view: 'View',
      selectAll: 'Select All',
      selectedCount: '{{selected}} of {{total}} selected',
      loading: 'Searching...',
      noAssets: 'No assets found',
      noMatching: 'No matching assets',
      materializedView: 'Materialized View',
      rows: '{{count}} rows',
      columns: '{{count}} columns',
      hint: 'Select the assets you want to import. You can search by name or filter by type.',
      save: 'Import Selected',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    selectAssetsDialog: {
      title: '选择数据资产',
      description: '为 {{name}} 选择数据资产',
      searchPlaceholder: '搜索资产...',
      allTypes: '全部',
      table: '表',
      view: '视图',
      selectAll: '全选',
      selectedCount: '已选 {{selected}} / {{total}}',
      loading: '搜索中...',
      noAssets: '暂无资产',
      noMatching: '没有匹配的资产',
      materializedView: '物化视图',
      rows: '{{count}} 行',
      columns: '{{count}} 列',
      hint: '选择要导入的数据资产，你可以按名称搜索或按类型筛选。',
      save: '导入所选',
    },
  },
}, true, true)
import { discoverAssets, updateAssetSelection } from '@/lib/dataSourceApi'
import { useNotification } from '@/hooks/useNotification'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Database, Loader2, Search, AlertCircle } from 'lucide-react'
import type { DiscoveredAsset } from '@/lib/dataSourceApi'

interface SelectAssetsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  dataSourceId: number
  dataSourceName: string
  mode?: 'create' | 'import' // 'create' for new data source, 'import' for adding assets
  onSuccess?: () => void
}

export default function SelectAssetsDialog({
  open,
  onOpenChange,
  dataSourceId,
  dataSourceName,
  onSuccess,
}: SelectAssetsDialogProps) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [discoveredAssets, setDiscoveredAssets] = useState<DiscoveredAsset[]>([])
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>('')
  const [assetSearchQuery, setAssetSearchQuery] = useState('')
  const [assetTypeFilter, setAssetTypeFilter] = useState<'all' | 'table' | 'view'>('all')
  const initialLoadRef = useRef(true)

  useEffect(() => {
    if (open) {
      initialLoadRef.current = true
    }
  }, [open, dataSourceId])

  // Discovery (light) with server-side search
  useEffect(() => {
    if (!open) return

    const query = assetSearchQuery.trim()
    const delay = query ? 300 : 0

    const handle = window.setTimeout(async () => {
      setLoading(true)
      setError('')
      try {
        const result = await discoverAssets({
          dataSourceId,
          light: true,
          query: query || undefined,
        })
        setDiscoveredAssets(result.assets)
        if (initialLoadRef.current) {
          setSelectedAssets(new Set(result.assets.map((a) => a.name)))
          initialLoadRef.current = false
        } else {
          setSelectedAssets(
            (prev) =>
              new Set([...prev].filter((name) => result.assets.some((a) => a.name === name)))
          )
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || err.message || t('common.failedToLoad'))
        setDiscoveredAssets([])
      } finally {
        setLoading(false)
      }
    }, delay)

    return () => window.clearTimeout(handle)
  }, [assetSearchQuery, dataSourceId, open])

  const filteredAssets = useMemo(() => {
    return discoveredAssets.filter((asset) => {
      const matchesSearch = true
      const matchesType = assetTypeFilter === 'all' || asset.type === assetTypeFilter
      return matchesSearch && matchesType
    })
  }, [discoveredAssets, assetTypeFilter])

  const toggleAsset = (assetName: string) => {
    setSelectedAssets((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(assetName)) {
        newSet.delete(assetName)
      } else {
        newSet.add(assetName)
      }
      return newSet
    })
  }

  const toggleAllAssets = () => {
    if (selectedAssets.size === filteredAssets.length) {
      setSelectedAssets(new Set())
    } else {
      setSelectedAssets(new Set(filteredAssets.map((a) => a.name)))
    }
  }

  const handleSave = async () => {
    if (selectedAssets.size === 0) {
      setError(t('common.noData'))
      return
    }

    setSaving(true)
    setError('')

    try {
      await updateAssetSelection(dataSourceId, Array.from(selectedAssets))
      showSuccess(t('common.uploadSuccess'))
      onSuccess?.()
      onOpenChange(false)
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || t('common.failedToLoad')
      setError(errorMsg)
      showError(errorMsg)
    } finally {
      setSaving(false)
    }
  }

  const handleClose = () => {
    if (!saving && !loading) {
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('components.selectAssetsDialog.title')}</DialogTitle>
          <DialogDescription>{t('components.selectAssetsDialog.description', { name: dataSourceName })}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-auto py-4 space-y-4">
          {/* Search and Filter */}
          <div className="space-y-3">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder={t('components.selectAssetsDialog.searchPlaceholder')}
                  value={assetSearchQuery}
                  onChange={(e) => setAssetSearchQuery(e.target.value)}
                  className="pl-9 h-9"
                />
              </div>
              <div className="flex gap-1 border rounded-md p-1">
                {(['all', 'table', 'view'] as const).map((type) => (
                  <button
                    key={type}
                    onClick={() => setAssetTypeFilter(type)}
                    className={`px-3 py-1.5 text-xs rounded transition-colors ${
                      assetTypeFilter === type
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted'
                    }`}
                  >
                    {type === 'all' ? t('components.selectAssetsDialog.allTypes') : type === 'table' ? t('components.selectAssetsDialog.table') : t('components.selectAssetsDialog.view')}
                  </button>
                ))}
              </div>
            </div>

            {/* Select All */}
            <div className="flex items-center justify-between py-2 px-3 bg-muted/50 rounded-md">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="select-all"
                  checked={
                    filteredAssets.length > 0 && selectedAssets.size === filteredAssets.length
                  }
                  onCheckedChange={toggleAllAssets}
                />
                  <Label htmlFor="select-all" className="font-medium cursor-pointer text-sm">
                   {t('components.selectAssetsDialog.selectAll')}
                 </Label>
              </div>
              <span className="text-xs text-muted-foreground">
                {t('components.selectAssetsDialog.selectedCount', { selected: selectedAssets.size, total: discoveredAssets.length })}
              </span>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              <span className="ml-2 text-sm text-muted-foreground">{t('components.selectAssetsDialog.loading')}</span>
            </div>
          ) : discoveredAssets.length === 0 ? (
            <div className="text-center py-12">
              <Database className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-50" />
              <p className="text-sm text-muted-foreground">{t('components.selectAssetsDialog.noAssets')}</p>
            </div>
          ) : (
            <>
              {/* Asset List */}
              <div className="border rounded-lg max-h-64 overflow-auto">
                {filteredAssets.length === 0 ? (
                    <div className="text-center py-6 text-sm text-muted-foreground">
                     {t('components.selectAssetsDialog.noMatching')}
                    </div>
                ) : (
                  <div className="divide-y">
                    {filteredAssets.map((asset) => (
                      <div
                        key={asset.name}
                        className="flex items-center space-x-3 p-3 hover:bg-muted/50 transition-colors"
                      >
                        <Checkbox
                          id={`asset-${asset.name}`}
                          checked={selectedAssets.has(asset.name)}
                          onCheckedChange={() => toggleAsset(asset.name)}
                        />
                        <div className="flex-1 min-w-0">
                          <Label
                            htmlFor={`asset-${asset.name}`}
                            className="font-medium cursor-pointer text-sm truncate block"
                          >
                            {asset.name}
                          </Label>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-muted-foreground">
                              {asset.type === 'table'
                                ? t('components.selectAssetsDialog.table')
                                : asset.type === 'view'
                                  ? t('components.selectAssetsDialog.view')
                                  : t('components.selectAssetsDialog.materializedView')}
                            </span>
                            {asset.row_count != null && (
                              <>
                                <span className="text-xs text-muted-foreground">•</span>
                                <span className="text-xs text-muted-foreground">
                                  {t('components.selectAssetsDialog.rows', { count: asset.row_count })}
                                </span>
                              </>
                            )}
                            {asset.columns && (
                              <>
                                <span className="text-xs text-muted-foreground">•</span>
                                <span className="text-xs text-muted-foreground">
                                  {t('components.selectAssetsDialog.columns', { count: asset.columns.length })}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Info */}
              <Alert>
                <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">
                {t('components.selectAssetsDialog.hint')}
              </AlertDescription>
              </Alert>
            </>
          )}

          {/* Error */}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={handleClose} disabled={saving || loading}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSave} disabled={saving || loading || selectedAssets.size === 0}>
            {saving ? t('common.loading') : t('components.selectAssetsDialog.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
