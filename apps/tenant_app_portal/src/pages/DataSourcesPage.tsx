import AddDataSourceDialog from '@/components/AddDataSourceDialog'
import ContainerRowActions from '@/components/ContainerRowActions'
import PaginationBar from '@/components/PaginationBar'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import TagChips from '@/components/TagChips'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
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
import { useDataSources } from '@/hooks/useDataSources'
import { useNotification } from '@/hooks/useNotification'
import { useResourceListTags } from '@/hooks/useResourceListTags'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import type { DataSource } from '@/lib/dataSourceApi'
import { listAssets } from '@/lib/dataSourceApi'
import { formatDate } from '@/lib/dateTime'
import { actionRules } from '@/lib/permissionRules'
import { TAG_RESOURCE_TYPES } from '@/lib/tagsApi'
import { Database, Plus, RefreshCw, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trans, useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  dataSources: {
    title: 'Data Sources',
    description: 'Connect and manage your data sources to enable AI-powered data analysis',
    searchPlaceholder: 'Search data sources...',
    addButton: 'Add Data Source',
    noDataSources: 'No data sources found',
    noMatchingSources: 'No matching data sources found',
    nameCol: 'Name',
    ownerCol: 'Owner',
    typeCol: 'Type',
    managedCol: 'Type',
    assetCountCol: 'Assets',
    descCol: 'Description',
    createdCol: 'Created At',
    deletedUser: 'Deleted User',
    platformManaged: 'Platform Managed',
    externalConnection: 'External',
    shareSource: 'Share',
    manageTags: 'Manage tags',
    platformManagedNote: 'This data source is managed by the platform',
    editSource: 'Edit data source',
    deleteSource: 'Delete data source',
    confirmDelete: 'Delete Data Source',
    confirmDeleteDesc: 'Are you sure you want to delete "{{name}}"?',
    deleteAssetWarning: 'This data source has {{count}} assets. Deleting it will remove all associated assets.',
    irreversible: 'This action is irreversible.',
    fetchError: 'Failed to fetch data sources',
    deleteSuccess: 'Data source deleted successfully',
    deleteFailed: 'Failed to delete data source',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  dataSources: {
    title: '数据源',
    description: '连接和管理您的数据源，实现AI驱动的数据分析',
    searchPlaceholder: '搜索数据源...',
    addButton: '添加数据源',
    noDataSources: '暂无数据源',
    noMatchingSources: '未找到匹配的数据源',
    nameCol: '名称',
    ownerCol: '所有者',
    typeCol: '类型',
    managedCol: '类型',
    assetCountCol: '资产数',
    descCol: '描述',
    createdCol: '创建时间',
    deletedUser: '已删除用户',
    platformManaged: '平台管理',
    externalConnection: '外部连接',
    shareSource: '分享',
    manageTags: '管理标签',
    platformManagedNote: '此数据源由平台管理',
    editSource: '编辑数据源',
    deleteSource: '删除数据源',
    confirmDelete: '删除数据源',
    confirmDeleteDesc: '确定要删除"{{name}}"吗？',
    deleteAssetWarning: '此数据源有{{count}}个资产。删除它将移除所有相关资产。',
    irreversible: '此操作不可撤销。',
    fetchError: '获取数据源失败',
    deleteSuccess: '数据源删除成功',
    deleteFailed: '删除数据源失败',
  }
}, true, true)

const DATA_SOURCE_PAGE_SIZE = 10

export default function DataSourcesPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { loading: authLoading, hasAny } = useAuth()
  const { dataSources, loading, page, total, totalPages, fetchDataSources, removeDataSource } =
    useDataSources()
  const { showSuccess, showError } = useNotification()

  const canCreate = hasAny(actionRules.canCreateDataSource())
  const canEdit = hasAny(actionRules.canEditDataSource())
  const canDelete = hasAny(actionRules.canDeleteDataSource())
  const canReadTags = hasAny(actionRules.canReadTags())
  const canManageTags = hasAny(actionRules.canManageTags())
  const { tagKeys, tagsMap: dataSourceTagsMap, setTagsForResource: setDataSourceTags } =
    useResourceListTags(TAG_RESOURCE_TYPES.DATA_SOURCE, dataSources, canReadTags)

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [dataSourceToDelete, setDataSourceToDelete] = useState<DataSource | null>(null)
  const [deleteAssetCount, setDeleteAssetCount] = useState<number>(0)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [editingDataSource, setEditingDataSource] = useState<DataSource | null>(null)
  const [sharingDataSource, setSharingDataSource] = useState<DataSource | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)

  // Fetch data sources on mount
  useEffect(() => {
    fetchDataSources(currentPage, DATA_SOURCE_PAGE_SIZE, searchQuery.trim() || undefined)
  }, [fetchDataSources, currentPage, searchQuery])

  useEffect(() => {
    if (page !== currentPage) {
      setCurrentPage(page)
    }
  }, [page, currentPage])

  const handleDataSourceClick = (dataSource: DataSource) => {
    navigate(`/data-sources/${dataSource.id}/assets`)
  }

  const handleDeleteClick = async (dataSource: DataSource) => {
    if (dataSource.managed) {
      return
    }
    setDataSourceToDelete(dataSource)

    // Fetch asset count for this data source
    try {
      const result = await listAssets(dataSource.id)
      setDeleteAssetCount(result.total)
    } catch {
      setDeleteAssetCount(0)
    }

    setDeleteDialogOpen(true)
  }

  const handleEditClick = (dataSource: DataSource) => {
    if (dataSource.managed) {
      return
    }
    setEditingDataSource(dataSource)
    setAddDialogOpen(true)
  }

  const handleAddSuccess = async () => {
    try {
      await fetchDataSources(currentPage, DATA_SOURCE_PAGE_SIZE, searchQuery.trim() || undefined)
      setAddDialogOpen(false)
      setEditingDataSource(null)
    } catch (error: any) {
      showError(error.message || t('dataSources.fetchError'))
    }
  }

  const handleDialogClose = () => {
    setAddDialogOpen(false)
    setEditingDataSource(null)
  }

  const handleDeleteConfirm = async () => {
    if (dataSourceToDelete) {
      try {
        await removeDataSource(dataSourceToDelete.id)
        await fetchDataSources(currentPage, DATA_SOURCE_PAGE_SIZE, searchQuery.trim() || undefined)
        setDeleteDialogOpen(false)
        setDataSourceToDelete(null)
        showSuccess(t('dataSources.deleteSuccess'))
      } catch (error: any) {
        showError(error.message || t('dataSources.deleteFailed'))
      }
    }
  }

  const getDataSourceTypeBadge = (type: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'outline'> = {
      postgres: 'outline',
      mysql: 'outline',
      databricks: 'outline',
      snowflake: 'outline',
      bigquery: 'outline',
    }
    return <Badge variant={variants[type] || 'default'}>{type.toUpperCase()}</Badge>
  }

  if (authLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t('dataSources.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('dataSources.description')}</p>
        </div>
        {canCreate && (
          <Button onClick={() => setAddDialogOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            {t('dataSources.addButton')}
          </Button>
        )}
      </div>

      {/* Data Sources Section */}
      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t('dataSources.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => {
                setCurrentPage(1)
                setSearchQuery(e.target.value)
              }}
              className="pl-8 h-9"
            />
            {searchQuery && (
              <Button
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1 h-7 w-7 p-0"
                onClick={() => {
                  setCurrentPage(1)
                  setSearchQuery('')
                }}
              >
                <X className="h-3 w-3" />
              </Button>
            )}
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button
              variant="outline"
              onClick={() =>
                fetchDataSources(
                  currentPage,
                  DATA_SOURCE_PAGE_SIZE,
                  searchQuery.trim() || undefined
                )
              }
              disabled={loading}
              size="sm"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              {t('common.refresh')}
            </Button>
          </div>
        </div>

        {/* Data Sources Table */}
        {loading && dataSources.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground py-8">{t('common.loading')}</p>
        ) : dataSources.length === 0 ? (
          <div className="text-center py-12 border rounded-lg bg-muted/20">
            <Database className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-50" />
            <p className="text-sm text-muted-foreground">
              {searchQuery ? t('dataSources.noMatchingSources') : t('dataSources.noDataSources')}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Table */}
            <div className="overflow-hidden rounded-lg border bg-card">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="h-10">{t('dataSources.nameCol')}</TableHead>
                    <TableHead className="h-10 w-32">{t('dataSources.ownerCol')}</TableHead>
                    <TableHead className="h-10 w-32">{t('dataSources.typeCol')}</TableHead>
                    <TableHead className="h-10 w-32">{t('dataSources.managedCol')}</TableHead>
                    <TableHead className="h-10 w-24 text-center">{t('dataSources.assetCountCol')}</TableHead>
                    <TableHead className="h-10">{t('dataSources.descCol')}</TableHead>
                    <TableHead className="h-10 w-40">{t('dataSources.createdCol')}</TableHead>
                    <TableHead className="h-10 w-24 text-right">{t('common.action')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dataSources.map((dataSource) => (
                    <TableRow key={dataSource.id}>
                      <TableCell className="py-2.5">
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2">
                            <Database className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                            <button
                              onClick={() => handleDataSourceClick(dataSource)}
                              className="text-sm font-medium hover:underline cursor-pointer text-left"
                            >
                              {dataSource.name}
                            </button>
                          </div>
                          {canReadTags && (dataSourceTagsMap[dataSource.id]?.length || 0) > 0 ? (
                            <TagChips
                              tags={dataSourceTagsMap[dataSource.id]}
                              tagKeys={tagKeys}
                              className="pl-6"
                              compact
                            />
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="py-2.5">
                        <span className="text-sm">{dataSource.owner_name || t('dataSources.deletedUser')}</span>
                      </TableCell>
                      <TableCell className="py-2.5">
                        {getDataSourceTypeBadge(dataSource.type)}
                      </TableCell>
                      <TableCell className="py-2.5">
                        {dataSource.managed ? (
                          <Badge variant="secondary">
                            {t('dataSources.platformManaged')}
                          </Badge>
                        ) : (
                          <Badge variant="outline">{t('dataSources.externalConnection')}</Badge>
                        )}
                      </TableCell>
                      <TableCell className="py-2.5 text-center">
                        <span className="text-sm font-medium">{dataSource.asset_count || '-'}</span>
                      </TableCell>
                      <TableCell className="py-2.5 text-sm max-w-xs truncate">
                        {dataSource.description || '-'}
                      </TableCell>
                      <TableCell className="py-2.5 text-sm text-muted-foreground">
                        {formatDate(dataSource.created_at)}
                      </TableCell>
                      <TableCell className="py-2.5 text-right">
                        <ContainerRowActions
                          onShare={() => setSharingDataSource(dataSource)}
                          shareTitle={t('dataSources.shareSource')}
                          tags={
                            canReadTags
                              ? {
                                  resourceType: TAG_RESOURCE_TYPES.DATA_SOURCE,
                                  resourceId: dataSource.id,
                                  resourceTitle: dataSource.name,
                                  canRead: canReadTags,
                                  canManage: canManageTags,
                                  onTagsUpdated: setDataSourceTags,
                                }
                              : undefined
                          }
                          tagsTitle={t('dataSources.manageTags')}
                          onEdit={() => handleEditClick(dataSource)}
                          editDisabled={dataSource.managed}
                          editHidden={!canEdit}
                          editTitle={
                            dataSource.managed
                              ? t('dataSources.platformManagedNote')
                              : t('dataSources.editSource')
                          }
                          onDelete={() => handleDeleteClick(dataSource)}
                          deleteDisabled={dataSource.managed || dataSource.asset_count > 0}
                          deleteHidden={!canDelete}
                          deleteTitle={
                            dataSource.managed
                              ? t('dataSources.platformManagedNote')
                              : t('dataSources.deleteSource')
                          }
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <PaginationBar
              page={page}
              pageSize={DATA_SOURCE_PAGE_SIZE}
              total={total}
              totalPages={totalPages}
              onPageChange={setCurrentPage}
              showWhenSinglePage={true}
            />
          </div>
        )}
      </div>

      {/* Add/Edit Data Source Dialog */}
      <AddDataSourceDialog
        open={addDialogOpen}
        onOpenChange={handleDialogClose}
        dataSource={editingDataSource}
        onSuccess={handleAddSuccess}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('dataSources.confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              <Trans i18nKey="dataSources.confirmDeleteDesc" values={{ name: dataSourceToDelete?.name }} />               
              <br />
              {deleteAssetCount > 0 && (
                <>
                  <strong className="text-red-600">
                    <Trans i18nKey="dataSources.deleteAssetWarning" count={deleteAssetCount} />
                  </strong>
                  <br />
                </>
              )}
              {deleteAssetCount === 0 && (
                <>
                  <strong className="text-red-600">{t('dataSources.irreversible')}</strong>
                  <br />
                </>
              )}
              <span className="text-xs text-muted-foreground mt-2 block">
                {t('dataSources.platformManagedNote')}
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className={buttonVariants({ variant: 'destructive' })}
            >
              {t('common.deleteConfirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {sharingDataSource && (
        <ResourceAclShareDialog
          open={Boolean(sharingDataSource)}
          onOpenChange={(open) => {
            if (!open) {
              setSharingDataSource(null)
            }
          }}
          resourceType={ACL_SHARE_RESOURCE_TYPES.DATA_SOURCE}
          resourceId={sharingDataSource.id}
          resourceTitle={sharingDataSource.name}
        />
      )}
    </div>
  )
}
