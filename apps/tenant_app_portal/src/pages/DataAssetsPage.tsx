import AssetSchemaDialog from '@/components/AssetSchemaDialog'
import ContainerDetailHeader from '@/components/ContainerDetailHeader'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import CSVUploadDialog from '@/components/CSVUploadDialog'
import PaginationBar from '@/components/PaginationBar'
import SelectAssetsDialog from '@/components/SelectAssetsDialog'
import SyncStatusIndicator from '@/components/SyncStatusIndicator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/hooks/useAuth'
import { useConfirmation } from '@/hooks/useConfirmation'
import { useAssets } from '@/hooks/useDataSources'
import { useNotification } from '@/hooks/useNotification'
import { formatDate } from '@/lib/dateTime'
import {
  getDataSource,
  resolveAssetDescription,
  syncAssetMetadata,
  type AssetMetadata,
  type DataSource,
} from '@/lib/dataSourceApi'
import { Info, RefreshCw, Search, Table2, Trash2, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Trans, useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  dataAssets: {
    title: 'Data Assets',
    parentLabel: 'Data Sources',
    back: 'Back',
    dataSource: 'Data Source: {{name}} ({{type}})',
    platformManaged: 'Platform Managed',
    searchPlaceholder: 'Search assets...',
    noDataAssets: 'No data assets found',
    noMatchingAssets: 'No matching assets found',
    uploadCsv: 'Upload CSV',
    addAsset: 'Add Asset',
    batchTag: 'Batch Tag',
    batchTagCount: 'Tag ({{count}})',
    deleteSelected: 'Delete ({{count}})',
    uploadFirstCsv: 'Upload Your First CSV',
    assetNameCol: 'Asset Name',
    typeCol: 'Type',
    rowCountCol: 'Rows',
    columnCountCol: 'Cols',
    descCol: 'Description',
    ownerCol: 'Owner',
    updatedCol: 'Updated',
    metaSyncCol: 'Meta Sync',
    vectorSyncCol: 'Vector Sync',
    metaSyncStatus: 'Metadata Sync Status',
    vectorSyncStatus: 'Vector Sync Status',
    shareDataSource: 'Share Data Source',
    dataSourceTags: 'Data Source Tags',
    deleteAsset: 'Delete',
    dataSourceNotExists: 'Data source not found',
    fetchFailed: 'Failed to fetch data',
    metadataUpdated: 'Metadata updated for {{name}}',
    metadataNoChange: 'No changes for {{name}}',
    syncFailed: 'Metadata sync failed',
    deleteCountSuccess: 'Successfully deleted {{count}} assets',
    deleteCountFailed: 'Failed to delete {{count}} assets',
    batchDeleteFailed: 'Batch delete failed',
    assetDeleteSuccess: 'Asset deleted successfully',
    deleteFailed: 'Failed to delete asset',
    confirmDelete: 'Delete Asset',
    confirmDeleteDesc: 'Are you sure you want to delete {{name}}?',
    deleteTableDataWarning: 'This will permanently delete the table data.',
    confirmDeleteButton: 'Delete',
    batchDeleteConfirmTitle: 'Delete Multiple Assets',
    batchDeleteConfirmDesc: 'Are you sure you want to delete {{count}} assets?',
    batchDeleteWarning: 'This action will permanently delete the selected assets.',
    willDelete: 'Will delete: {{items}}',
    confirmBatchDeleteButton: 'Delete {{count}} assets',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  dataAssets: {
    title: '数据资产',
    parentLabel: '数据源',
    back: '返回',
    dataSource: '数据源：{{name}}（{{type}}）',
    platformManaged: '平台管理',
    searchPlaceholder: '搜索资产...',
    noDataAssets: '暂无数据资产',
    noMatchingAssets: '未找到匹配的资产',
    uploadCsv: '上传CSV',
    addAsset: '添加资产',
    batchTag: '批量标签',
    batchTagCount: '标签（{{count}}）',
    deleteSelected: '删除（{{count}}）',
    uploadFirstCsv: '上传您的第一个CSV',
    assetNameCol: '资产名称',
    typeCol: '类型',
    rowCountCol: '行数',
    columnCountCol: '列数',
    descCol: '描述',
    ownerCol: '所有者',
    updatedCol: '更新于',
    metaSyncCol: '元数据同步',
    vectorSyncCol: '向量同步',
    metaSyncStatus: '元数据同步状态',
    vectorSyncStatus: '向量同步状态',
    shareDataSource: '分享数据源',
    dataSourceTags: '数据源标签',
    syncMetadata: '同步元数据',
    deleteAsset: '删除',
    dataSourceNotExists: '数据源不存在',
    fetchFailed: '获取数据失败',
    metadataUpdated: '{{name}}的元数据已更新',
    metadataNoChange: '{{name}}没有变化',
    syncFailed: '元数据同步失败',
    deleteCountSuccess: '成功删除{{count}}个资产',
    deleteCountFailed: '删除{{count}}个资产失败',
    batchDeleteFailed: '批量删除失败',
    assetDeleteSuccess: '资产删除成功',
    deleteFailed: '删除资产失败',
    confirmDelete: '删除资产',
    confirmDeleteDesc: '确定要删除{{name}}吗？',
    deleteTableDataWarning: '这将永久删除表数据。',
    confirmDeleteButton: '删除',
    batchDeleteConfirmTitle: '批量删除资产',
    batchDeleteConfirmDesc: '确定要删除{{count}}个资产吗？',
    batchDeleteWarning: '此操作将永久删除所选资产。',
    willDelete: '将删除：{{items}}',
    confirmBatchDeleteButton: '删除{{count}}个资产',
  }
}, true, true)

export default function DataAssetsPage() {
  const { t } = useTranslation()
  const { dataSourceId } = useParams<{ dataSourceId: string }>()
  const navigate = useNavigate()
  const { loading: authLoading } = useAuth()
  const { showSuccess, showError } = useNotification()

  const {
    assets,
    loading: assetsLoading,
    fetchAssets,
    removeAssets,
    pageSize,
    total,
    totalPages,
  } = useAssets(dataSourceId ? parseInt(dataSourceId) : 0)

  const [dataSource, setDataSource] = useState<DataSource | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)
  const [schemaDialogOpen, setSchemaDialogOpen] = useState(false)
  const [selectedAsset, setSelectedAsset] = useState<AssetMetadata | null>(null)
  const [selectedAssets, setSelectedAssets] = useState<string[]>([])
  const [selectAssetsDialogOpen, setSelectAssetsDialogOpen] = useState(false)
  const [syncingAssetIds, setSyncingAssetIds] = useState<Set<number>>(new Set())
  const normalizedQuery = searchQuery.trim() || undefined

  const singleDeleteConfirm = useConfirmation<AssetMetadata | null>(null)
  const batchDeleteConfirm = useConfirmation<string[] | null>(null)

  // Sync asset metadata handler
  const handleSyncAsset = async (asset: AssetMetadata) => {
    if (!dataSource || dataSource.managed) return

    setSyncingAssetIds((prev) => new Set(prev).add(asset.id))

    try {
      const result = await syncAssetMetadata(dataSource.id, asset.id, false)

      if (result.status === 'success') {
        if (result.updated) {
          showSuccess(t('dataAssets.metadataUpdated', { name: asset.asset_name }))
          await fetchAssets(currentPage, pageSize, normalizedQuery) // Refresh current page
        } else {
          showSuccess(t('dataAssets.metadataNoChange', { name: asset.asset_name }))
        }
      } else {
        showError(result.error || t('dataAssets.syncFailed'))
      }
    } catch (error: any) {
      showError(error.message || t('dataAssets.syncFailed'))
    } finally {
      setSyncingAssetIds((prev) => {
        const next = new Set(prev)
        next.delete(asset.id)
        return next
      })
    }
  }

  // Fetch data source and assets
  const fetchData = async (pageNum: number = 1, query?: string) => {
    if (!dataSourceId) return

    try {
      const dsData = await getDataSource(parseInt(dataSourceId))
      setDataSource(dsData)
      await fetchAssets(pageNum, pageSize, query)
    } catch (error: any) {
      console.error('Failed to fetch data source:', error)
      showError(error.message || t('dataAssets.fetchFailed'))
    }
  }

  useEffect(() => {
    fetchData()
  }, [dataSourceId])

  // Reset to page 1 when search query changes
  useEffect(() => {
    setCurrentPage(1)
    setSelectedAssets([])
    if (!dataSourceId) return
    fetchAssets(1, pageSize, normalizedQuery)
  }, [searchQuery, dataSourceId, normalizedQuery, pageSize, fetchAssets])

  // Batch selection handlers
  const isAllSelected = assets.length > 0 && selectedAssets.length === assets.length
  const isIndeterminate = selectedAssets.length > 0 && selectedAssets.length < assets.length

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedAssets(assets.map((asset) => asset.asset_name))
    } else {
      setSelectedAssets([])
    }
  }

  const handleSelectAsset = (assetName: string, checked: boolean) => {
    if (checked) {
      setSelectedAssets((prev) => [...prev, assetName])
    } else {
      setSelectedAssets((prev) => prev.filter((name) => name !== assetName))
    }
  }

  const handleBatchDeleteClick = () => {
    if (selectedAssets.length === 0) return
    batchDeleteConfirm.open(selectedAssets)
  }

  const handleBatchDeleteConfirm = async (assets: string[] | null) => {
    if (!assets || assets.length === 0 || !dataSourceId) return

    batchDeleteConfirm.setLoading(true)
    try {
      const result = await removeAssets(assets)
      setSelectedAssets([])
      batchDeleteConfirm.close()
      if (result.deleted_count > 0) {
        showSuccess(t('dataAssets.deleteCountSuccess', { count: result.deleted_count }))
      }
      if (result.failed_assets.length > 0) {
        showError(t('dataAssets.deleteCountFailed', { count: result.failed_assets.length }))
      }
      // Refresh current page
      await fetchData(currentPage, normalizedQuery)
    } catch (error: any) {
      console.error('Failed to batch delete assets:', error)
      showError(error.message || t('dataAssets.batchDeleteFailed'))
    } finally {
      batchDeleteConfirm.setLoading(false)
    }
  }

  const handleDeleteClick = (asset: AssetMetadata) => {
    singleDeleteConfirm.open(asset)
  }

  const handleDeleteConfirm = async (asset: AssetMetadata | null) => {
    if (!asset || !dataSourceId) return

    singleDeleteConfirm.setLoading(true)
    try {
      await removeAssets([asset.asset_name])
      singleDeleteConfirm.close()
      showSuccess(t('dataAssets.assetDeleteSuccess'))
      // Refresh current page
      await fetchData(currentPage, normalizedQuery)
    } catch (error: any) {
      console.error('Failed to delete asset:', error)
      showError(error.message || t('dataAssets.deleteFailed'))
    } finally {
      singleDeleteConfirm.setLoading(false)
    }
  }

  const handleUploadSuccess = () => {
    setUploadDialogOpen(false)
    // Refresh to last page to see new asset
    fetchData(totalPages || 1, normalizedQuery)
  }

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage)
    fetchData(newPage, normalizedQuery)
    setSelectedAssets([])
  }

  const handleViewSchema = (asset: AssetMetadata) => {
    if (!asset) return
    setSelectedAsset(asset)
    setSchemaDialogOpen(true)
  }

  const handleAssetUpdated = async (updated: AssetMetadata) => {
    setSelectedAsset(updated)
    await fetchAssets(currentPage, pageSize, normalizedQuery)
  }

  const getAssetTypeBadge = (type: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'outline'> = {
      table: 'default',
      view: 'secondary',
      materialized_view: 'outline',
      api_endpoint: 'outline',
    }
    return (
      <Badge variant={variants[type] || 'default'}>{type.replace('_', ' ').toUpperCase()}</Badge>
    )
  }

  const renderMetadataSyncStatus = (asset: AssetMetadata) => {
    return (
      <SyncStatusIndicator
        syncedAt={asset.last_metadata_synced_at}
        error={asset.last_metadata_sync_error}
        title={t('dataAssets.metaSyncStatus')}
      />
    )
  }

  const renderVectorSyncStatus = (asset: AssetMetadata) => {
    return (
      <SyncStatusIndicator
        syncedAt={asset.last_vector_synced_at}
        error={asset.last_vector_sync_error}
        title={t('dataAssets.vectorSyncStatus')}
      />
    )
  }

  if (authLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (assetsLoading && !dataSource) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!dataSource) {
    return (
      <div className="space-y-4">
        <Alert variant="destructive">
          <Info className="h-4 w-4" />
          <AlertDescription>{t('dataAssets.dataSourceNotExists')}</AlertDescription>
        </Alert>
      </div>
    )
  }

  const displayTotal = total
  const displayTotalPages = totalPages
  const displayPage = currentPage

  return (
    <div className="space-y-4">
      <ContainerDetailHeader
        parentLabel={t('dataAssets.parentLabel')}
        onParentNavigate={() => navigate('/data-sources')}
        title={dataSource.name}
        meta={
          <>
            {t('dataAssets.title')}
            {' · '}
            {dataSource.type.toUpperCase()}
            {dataSource.managed ? (
              <Badge variant="secondary" className="ml-2">
                {t('dataAssets.platformManaged')}
              </Badge>
            ) : null}
          </>
        }
        primaryAction={
          dataSource.managed ? (
            <Button onClick={() => setUploadDialogOpen(true)}>
              <Upload className="w-4 h-4 mr-2" />
              {t('dataAssets.uploadCsv')}
            </Button>
          ) : (
            <Button onClick={() => setSelectAssetsDialogOpen(true)}>
              <Upload className="w-4 h-4 mr-2" />
              {t('dataAssets.addAsset')}
            </Button>
          )
        }
        onRefresh={() => fetchData(currentPage, normalizedQuery)}
        refreshing={assetsLoading}
        trailingActions={
          selectedAssets.length > 0 ? (
            <Button onClick={handleBatchDeleteClick} variant="outline" size="sm">
              <Trash2 className="w-4 h-4 mr-2" />
              {t('dataAssets.deleteSelected', { count: selectedAssets.length })}
            </Button>
          ) : null
        }
      />

      {/* Search Bar */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={t('dataAssets.searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Assets Table */}
      {assets.length === 0 ? (
        <div className="text-center py-12 border rounded-lg bg-muted/20">
          <Table2 className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-50" />
          <p className="text-sm text-muted-foreground">
            {searchQuery ? t('dataAssets.noMatchingAssets') : t('dataAssets.noDataAssets')}
          </p>
          {!searchQuery && dataSource.managed && (
            <Button onClick={() => setUploadDialogOpen(true)} className="mt-4" variant="outline">
              <Upload className="w-4 h-4 mr-2" />
              {t('dataAssets.uploadFirstCsv')}
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {/* Table */}
          <div className="overflow-hidden rounded-lg border bg-card">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-10 w-[50px]">
                    <Checkbox
                      checked={isAllSelected}
                      onCheckedChange={handleSelectAll}
                      aria-label="Select all assets"
                      className={isIndeterminate ? 'data-[state=checked]:bg-muted-foreground' : ''}
                    />
                  </TableHead>
                  <TableHead className="h-10 w-[200px]">{t('dataAssets.assetNameCol')}</TableHead>
                  <TableHead className="h-10 w-[100px]">{t('dataAssets.typeCol')}</TableHead>
                  <TableHead className="h-10 w-[80px]">{t('dataAssets.rowCountCol')}</TableHead>
                  <TableHead className="h-10 w-[80px]">{t('dataAssets.columnCountCol')}</TableHead>
                  <TableHead className="h-10">{t('dataAssets.descCol')}</TableHead>
                  <TableHead className="h-10 w-[120px]">{t('dataAssets.ownerCol')}</TableHead>
                  <TableHead className="h-10 w-[140px]">{t('dataAssets.updatedCol')}</TableHead>
                  <TableHead className="h-10 w-[120px]">{t('dataAssets.metaSyncCol')}</TableHead>
                  <TableHead className="h-10 w-[120px]">{t('dataAssets.vectorSyncCol')}</TableHead>
                  <TableHead className="h-10 w-[80px] text-right">{t('common.action')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {assets.map((asset) => (
                  <TableRow key={asset.id}>
                    <TableCell className="py-2.5">
                      <Checkbox
                        checked={selectedAssets.includes(asset.asset_name)}
                        onCheckedChange={(checked: boolean) =>
                          handleSelectAsset(asset.asset_name, checked)
                        }
                        aria-label={`Select ${asset.asset_name}`}
                      />
                    </TableCell>
                    <TableCell className="py-2.5">
                      <button
                        onClick={() => handleViewSchema(asset)}
                        className="font-mono text-sm font-medium hover:underline cursor-pointer text-left"
                      >
                        {asset.asset_name}
                      </button>
                    </TableCell>
                    <TableCell className="py-2.5">{getAssetTypeBadge(asset.asset_type)}</TableCell>
                    <TableCell className="py-2.5 text-sm">
                      {asset.row_count?.toLocaleString() || '-'}
                    </TableCell>
                    <TableCell className="py-2.5 text-sm">{asset.columns.length}</TableCell>
                    <TableCell className="py-2.5 text-sm max-w-xs truncate">
                      {resolveAssetDescription(asset) || '-'}
                    </TableCell>
                    <TableCell className="py-2.5 text-sm">
                      {asset.owner_name || '-'}
                    </TableCell>
                    <TableCell className="py-2.5 text-sm text-muted-foreground">
                      {formatDate(asset.updated_at)}
                    </TableCell>
                    <TableCell className="py-2.5 text-sm">{renderMetadataSyncStatus(asset)}</TableCell>
                    <TableCell className="py-2.5 text-sm">{renderVectorSyncStatus(asset)}</TableCell>
                    <TableCell className="py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {!dataSource.managed && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleSyncAsset(asset)}
                            disabled={syncingAssetIds.has(asset.id)}
                            className="h-8 w-8 p-0"
                            title={t('dataAssets.syncMetadata')}
                          >
                            <RefreshCw
                              className={`w-4 h-4 ${syncingAssetIds.has(asset.id) ? 'animate-spin' : ''}`}
                            />
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDeleteClick(asset)}
                          className="h-8 w-8 p-0"
                          title={t('dataAssets.deleteAsset')}
                        >
                          <Trash2 className="w-4 h-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <PaginationBar
            page={displayPage}
            pageSize={pageSize}
            total={displayTotal}
            totalPages={displayTotalPages}
            onPageChange={handlePageChange}
          />

        </div>
      )}

      {/* CSV Upload Dialog */}
      {dataSource && (
        <CSVUploadDialog
          open={uploadDialogOpen}
          onOpenChange={setUploadDialogOpen}
          dataSource={dataSource}
          onSuccess={handleUploadSuccess}
        />
      )}

      {/* Asset Schema Dialog */}
      {selectedAsset && (
        <AssetSchemaDialog
          open={schemaDialogOpen}
          onOpenChange={setSchemaDialogOpen}
          asset={selectedAsset}
          onUpdated={handleAssetUpdated}
        />
      )}

      {dataSource && (
        <SelectAssetsDialog
          open={selectAssetsDialogOpen}
          onOpenChange={setSelectAssetsDialogOpen}
          dataSourceId={dataSource.id}
          dataSourceName={dataSource.name}
          mode="import"
          onSuccess={handleUploadSuccess}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmationDialog<AssetMetadata | null>
        open={singleDeleteConfirm.isOpen}
        item={singleDeleteConfirm.item}
        isLoading={singleDeleteConfirm.isLoading}
        title={t('dataAssets.confirmDelete')}
        description={(asset) => (
          <>
            <Trans i18nKey="dataAssets.confirmDeleteDesc" values={{ name: asset?.asset_name }} />            
            <br />
            <span className="text-red-600">{t('dataAssets.deleteTableDataWarning')}</span>
          </>
        )}
        confirmText={t('dataAssets.confirmDeleteButton')}
        isDangerous
        onConfirm={handleDeleteConfirm}
        onCancel={singleDeleteConfirm.close}
      />

      {/* Batch Delete Confirmation Dialog */}
      <ConfirmationDialog<string[] | null>
        open={batchDeleteConfirm.isOpen}
        item={batchDeleteConfirm.item}
        isLoading={batchDeleteConfirm.isLoading}
        title={t('dataAssets.batchDeleteConfirmTitle')}
        description={(items) => (
          <>
            <Trans i18nKey="dataAssets.batchDeleteConfirmDesc" count={items?.length || 0} />            
            <br />
            <span className="text-red-600">{t('dataAssets.batchDeleteWarning')}</span>
            {items && items.length > 0 && (
              <div className="mt-2 p-2 bg-muted rounded text-xs">{t('dataAssets.willDelete', { items: items.join(', ') })}</div>
            )}
          </>
        )}
        confirmText={t('dataAssets.confirmBatchDeleteButton', { count: batchDeleteConfirm.item?.length || 0 })}
        isDangerous
        onConfirm={handleBatchDeleteConfirm}
        onCancel={batchDeleteConfirm.close}
      />
    </div>
  )
}
