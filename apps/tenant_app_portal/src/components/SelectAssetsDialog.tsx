import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      selectAssetsDialog: {
        title: 'Select Assets',
        description: 'Select assets for {{name}}',
        searchPlaceholder: 'Search assets...',
        allTypes: 'All',
        table: 'Table',
        view: 'View',
        selectAll: 'Select All',
        resultsHeading: 'Results',
        selectedHeading: 'Selected',
        selectedEmpty: 'Checked assets appear here.',
        selectedCount: '{{selected}} selected',
        resultCap: 'Showing {{shown}} of {{total}}. Refine the search to see more.',
        searchPrompt: 'Type at least 2 characters to search by catalog, schema, or table.',
        loading: 'Searching...',
        noAssets: 'No assets found',
        noMatching: 'No matching assets',
        materializedView: 'Materialized View',
        rows: '{{count}} rows',
        columns: '{{count}} columns',
        save: 'Import Selected',
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
      selectAssetsDialog: {
        title: '选择数据资产',
        description: '为 {{name}} 选择数据资产',
        searchPlaceholder: '搜索资产...',
        allTypes: '全部',
        table: '表',
        view: '视图',
        selectAll: '全选',
        resultsHeading: '搜索结果',
        selectedHeading: '已选',
        selectedEmpty: '在左侧勾选资产。',
        selectedCount: '已选 {{selected}}',
        resultCap: '显示 {{shown}} / {{total}}。缩小搜索范围可查看更多。',
        searchPrompt: '输入至少 2 个字符，按目录、模式或表名搜索。',
        loading: '搜索中...',
        noAssets: '暂无资产',
        noMatching: '没有匹配的资产',
        materializedView: '物化视图',
        rows: '{{count}} 行',
        columns: '{{count}} 列',
        save: '导入所选',
      },
    },
  },
  true,
  true
)
import { discoverAssets, updateAssetSelection } from '@/lib/dataSourceApi'
import { loadImportedSelection } from '@/lib/importedAssetSelection'
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
import { Loader2, Search, AlertCircle } from 'lucide-react'
import type { DiscoveredAsset } from '@/lib/dataSourceApi'

function assetTypeLabel(type: DiscoveredAsset['type'], t: (key: string) => string): string {
  if (type === 'table') return t('components.selectAssetsDialog.table')
  if (type === 'view') return t('components.selectAssetsDialog.view')
  return t('components.selectAssetsDialog.materializedView')
}

function AssetCheckList({
  assets,
  selectedNames,
  onToggle,
  idPrefix,
  disabled = false,
}: {
  assets: DiscoveredAsset[]
  selectedNames: Set<string>
  onToggle: (asset: DiscoveredAsset) => void
  idPrefix: string
  disabled?: boolean
}) {
  const { t } = useTranslation()

  return (
    <div className="divide-y">
      {assets.map((asset) => (
        <div
          key={asset.name}
          className="flex items-center gap-3 px-3 py-2 transition-colors hover:bg-muted/50"
        >
          <Checkbox
            id={`${idPrefix}-${asset.name}`}
            checked={selectedNames.has(asset.name)}
            onCheckedChange={() => onToggle(asset)}
            disabled={disabled}
          />
          <Label
            htmlFor={`${idPrefix}-${asset.name}`}
            className={`min-w-0 flex-1 truncate text-sm font-normal ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
            title={asset.name}
          >
            {asset.name}
          </Label>
          <span className="shrink-0 text-xs text-muted-foreground">
            {assetTypeLabel(asset.type, t)}
          </span>
        </div>
      ))}
    </div>
  )
}

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
  const [resultTotal, setResultTotal] = useState(0)
  const [selectedByName, setSelectedByName] = useState<Record<string, DiscoveredAsset>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>('')
  const [assetSearchQuery, setAssetSearchQuery] = useState('')
  const [assetTypeFilter, setAssetTypeFilter] = useState<'all' | 'table' | 'view'>('all')
  const [requiresQuery, setRequiresQuery] = useState(false)
  const [selectionReady, setSelectionReady] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setSelectionReady(false)
    setSelectedByName({})
    setResultTotal(0)
    setAssetSearchQuery('')
    setAssetTypeFilter('all')
    setRequiresQuery(false)
    setDiscoveredAssets([])
    setError('')

    loadImportedSelection(dataSourceId)
      .then((selected) => {
        if (!cancelled) {
          setSelectedByName(selected)
          setSelectionReady(true)
        }
      })
      .catch((err: any) => {
        if (!cancelled) {
          setError(err.response?.data?.detail || err.message || t('common.failedToLoad'))
        }
      })

    return () => {
      cancelled = true
    }
  }, [open, dataSourceId, t])

  // Discovery (light) with server-side search
  useEffect(() => {
    if (!open) return

    const query = assetSearchQuery.trim()
    const delay = query ? 300 : 0
    if (!query) {
      setLoading(true)
    }

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
        setResultTotal(Number(result.total) || result.assets.length)
        if (result.requires_query) {
          setRequiresQuery(true)
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

  const selectedAssets = useMemo(
    () => Object.values(selectedByName).sort((left, right) => left.name.localeCompare(right.name)),
    [selectedByName]
  )
  const selectedNames = useMemo(
    () => new Set(selectedAssets.map((asset) => asset.name)),
    [selectedAssets]
  )

  const toggleAsset = (asset: DiscoveredAsset) => {
    if (saving || !selectionReady) return
    setSelectedByName((prev) => {
      const next = { ...prev }
      if (next[asset.name]) {
        delete next[asset.name]
      } else {
        next[asset.name] = asset
      }
      return next
    })
  }

  const visibleNames = filteredAssets.map((asset) => asset.name)
  const allVisibleSelected =
    visibleNames.length > 0 && visibleNames.every((name) => selectedNames.has(name))
  const showSearchPrompt = requiresQuery && assetSearchQuery.trim().length < 2
  const resultsTruncated = !showSearchPrompt && resultTotal > discoveredAssets.length

  const toggleAllAssets = () => {
    if (saving || !selectionReady) return
    setSelectedByName((prev) => {
      const next = { ...prev }
      if (allVisibleSelected) {
        for (const name of visibleNames) delete next[name]
      } else {
        for (const asset of filteredAssets) next[asset.name] = asset
      }
      return next
    })
  }

  const panelLocked = saving || !selectionReady

  const handleSave = async () => {
    if (!selectionReady || selectedAssets.length === 0) {
      setError(t('common.noData'))
      return
    }

    setSaving(true)
    setError('')

    try {
      await updateAssetSelection(
        dataSourceId,
        selectedAssets.map((asset) => asset.name)
      )
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
      <DialogContent className="flex h-[70vh] max-h-[80vh] w-full flex-col overflow-hidden sm:max-w-[960px]">
        <DialogHeader className="shrink-0">
          <DialogTitle>{t('components.selectAssetsDialog.title')}</DialogTitle>
          <DialogDescription>
            {t('components.selectAssetsDialog.description', { name: dataSourceName })}
          </DialogDescription>
        </DialogHeader>

        <div
          className={`flex min-h-0 flex-1 flex-col gap-3 ${panelLocked ? 'pointer-events-none opacity-60' : ''}`}
          aria-busy={panelLocked}
        >
          <div className="shrink-0 space-y-3">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder={t('components.selectAssetsDialog.searchPlaceholder')}
                  value={assetSearchQuery}
                  onChange={(e) => setAssetSearchQuery(e.target.value)}
                  className="h-9 pl-9"
                  disabled={panelLocked}
                />
              </div>
              <div className="flex gap-1 rounded-md border p-1">
                {(['all', 'table', 'view'] as const).map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setAssetTypeFilter(type)}
                    disabled={panelLocked}
                    className={`rounded px-3 py-1.5 text-xs transition-colors disabled:cursor-not-allowed ${
                      assetTypeFilter === type
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted'
                    }`}
                  >
                    {type === 'all'
                      ? t('components.selectAssetsDialog.allTypes')
                      : type === 'table'
                        ? t('components.selectAssetsDialog.table')
                        : t('components.selectAssetsDialog.view')}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
            <section className="flex min-h-0 min-w-0 flex-col gap-2">
              <div className="flex shrink-0 items-center justify-between rounded-md bg-muted/50 px-3 py-2">
                <span className="text-sm font-medium">
                  {t('components.selectAssetsDialog.resultsHeading')}
                </span>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="select-all"
                    checked={allVisibleSelected}
                    onCheckedChange={toggleAllAssets}
                    disabled={panelLocked || visibleNames.length === 0}
                  />
                  <Label htmlFor="select-all" className="cursor-pointer text-sm font-normal">
                    {t('components.selectAssetsDialog.selectAll')}
                  </Label>
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-auto rounded-lg border">
                {loading ? (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    <span className="ml-2 text-sm text-muted-foreground">
                      {t('components.selectAssetsDialog.loading')}
                    </span>
                  </div>
                ) : filteredAssets.length === 0 ? (
                  <div className="px-4 py-10 text-center">
                    <p className="text-sm text-muted-foreground">
                      {showSearchPrompt
                        ? t('components.selectAssetsDialog.searchPrompt')
                        : discoveredAssets.length === 0
                          ? t('components.selectAssetsDialog.noAssets')
                          : t('components.selectAssetsDialog.noMatching')}
                    </p>
                  </div>
                ) : (
                  <AssetCheckList
                    assets={filteredAssets}
                    selectedNames={selectedNames}
                    onToggle={toggleAsset}
                    idPrefix="result"
                    disabled={panelLocked}
                  />
                )}
              </div>
              {resultsTruncated ? (
                <p className="shrink-0 text-xs text-muted-foreground">
                  {t('components.selectAssetsDialog.resultCap', {
                    shown: discoveredAssets.length,
                    total: resultTotal,
                  })}
                </p>
              ) : null}
            </section>

            <section className="flex min-h-0 min-w-0 flex-col gap-2">
              <div className="flex shrink-0 items-center justify-between rounded-md bg-muted/50 px-3 py-2">
                <span className="text-sm font-medium">
                  {t('components.selectAssetsDialog.selectedHeading')}
                </span>
                <span className="text-xs text-muted-foreground">
                  {t('components.selectAssetsDialog.selectedCount', {
                    selected: selectedAssets.length,
                  })}
                </span>
              </div>
              <div className="min-h-0 flex-1 overflow-auto rounded-lg border">
                {!selectionReady ? (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : selectedAssets.length === 0 ? (
                  <div className="px-4 py-10 text-center">
                    <p className="text-sm text-muted-foreground">
                      {t('components.selectAssetsDialog.selectedEmpty')}
                    </p>
                  </div>
                ) : (
                  <AssetCheckList
                    assets={selectedAssets}
                    selectedNames={selectedNames}
                    onToggle={toggleAsset}
                    idPrefix="selected"
                    disabled={panelLocked}
                  />
                )}
              </div>
            </section>
          </div>

          {error ? (
            <Alert variant="destructive" className="shrink-0">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          ) : null}
        </div>

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={handleClose} disabled={saving || loading}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={handleSave}
            disabled={panelLocked || loading || selectedAssets.length === 0}
          >
            {saving ? t('common.loading') : t('components.selectAssetsDialog.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
