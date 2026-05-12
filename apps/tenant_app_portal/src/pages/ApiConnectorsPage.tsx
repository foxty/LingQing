import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { useConfirmation } from '@/hooks/useConfirmation'
import { Alert, AlertDescription } from '@/components/ui/alert'
import AddApiConnectorDialog from '@/components/AddApiConnectorDialog'
import ContainerRowActions from '@/components/ContainerRowActions'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import TagChips from '@/components/TagChips'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useApiConnectors } from '@/hooks/useApiConnectors'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { useResourceListTags } from '@/hooks/useResourceListTags'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import { formatDate } from '@/lib/dateTime'
import type { ApiConnector } from '@/lib/apiConnectorApi'
import { actionRules } from '@/lib/permissionRules'
import { TAG_RESOURCE_TYPES } from '@/lib/tagsApi'
import { Cable, Plus, RefreshCw, Search, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  apiConnectors: {
    title: 'API Connectors',
    description: 'Manage and configure API connectors to expose external APIs',
    searchPlaceholder: 'Search connectors...',
    addButton: 'Add Connector',
    noConnectors: 'No connectors found',
    noMatchingConnectors: 'No matching connectors found',
    nameCol: 'Name',
    ownerCol: 'Owner',
    baseUrlCol: 'Base URL',
    authCol: 'Auth Type',
    schemaCol: 'Schema',
    lastSyncCol: 'Last Synced',
    share: 'Share',
    manageTags: 'Manage tags',
    editConnector: 'Edit connector',
    deleteConnector: 'Delete connector',
    deletedUser: 'Deleted User',
    fetchError: 'Failed to fetch API connectors',
    confirmDelete: 'Are you sure you want to delete "{name}"?',
    deleteSuccess: 'API connector deleted successfully',
    deleteFailed: 'Failed to delete API connector',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  apiConnectors: {
    title: 'API连接器',
    description: '管理和配置API连接器以暴露外部API',
    searchPlaceholder: '搜索连接器...',
    addButton: '添加连接器',
    noConnectors: '暂无连接器',
    noMatchingConnectors: '未找到匹配的连接器',
    nameCol: '名称',
    ownerCol: '所有者',
    baseUrlCol: '基础URL',
    authCol: '认证类型',
    schemaCol: '模式',
    lastSyncCol: '最后同步',
    share: '分享',
    manageTags: '管理标签',
    editConnector: '编辑连接器',
    deleteConnector: '删除连接器',
    deletedUser: '已删除用户',
    fetchError: '获取API连接器失败',
    confirmDelete: '确定要删除"{name}"吗？',
    deleteSuccess: 'API连接器删除成功',
    deleteFailed: '删除API连接器失败',
  }
}, true, true)

export default function ApiConnectorsPage() {
  const { t } = useTranslation()
  const {
    connectors,
    loading,
    error,
    fetchConnectors,
    addConnector,
    modifyConnector,
    removeConnector,
  } = useApiConnectors()
  const { showError, showSuccess } = useNotification()
  const navigate = useNavigate()
  const { hasAny } = useAuth()
  const canManageTags = hasAny(actionRules.canManageTags())
  const canReadTags = hasAny(actionRules.canReadTags())
  const canCreateConnector = hasAny(actionRules.canCreateApiConnector())
  const canEditConnector = hasAny(actionRules.canEditApiConnector())
  const canDeleteConnector = hasAny(actionRules.canDeleteApiConnector())

  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editingConnector, setEditingConnector] = useState<ApiConnector | null>(null)
  const [sharingConnector, setSharingConnector] = useState<ApiConnector | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const deleteConfirm = useConfirmation<ApiConnector>()
  const { tagKeys, tagsMap: connectorTagsMap, setTagsForResource: setConnectorTags } =
    useResourceListTags(TAG_RESOURCE_TYPES.API_CONNECTOR, connectors, canReadTags)

  const normalizedQuery = searchQuery.trim().toLowerCase()
  const filteredConnectors = normalizedQuery
    ? connectors.filter((connector) => {
        const searchable = [
          connector.name,
          connector.owner_name || '',
          connector.base_url,
          connector.auth_type,
          connector.schema_source_type,
        ]
          .join(' ')
          .toLowerCase()
        return searchable.includes(normalizedQuery)
      })
    : connectors

  useEffect(() => {
    fetchConnectors().catch((err: any) => {
      showError(err.response?.data?.detail || t('apiConnectors.fetchError'))
    })
  }, [fetchConnectors, showError])

  const openCreateConnectorForm = () => {
    setAddDialogOpen(true)
  }

  const openConnectorManagement = (connectorId: number) => {
    navigate(`/api-connectors/${connectorId}`)
  }

  const openEditConnectorForm = (connector: ApiConnector) => {
    setEditingConnector(connector)
    setEditDialogOpen(true)
  }

  const handleDeleteConnector = async (connector: ApiConnector) => {
    deleteConfirm.setLoading(true)
    try {
      await removeConnector(connector.id)
      showSuccess(t('apiConnectors.deleteSuccess'))
      deleteConfirm.close()
    } catch (err: any) {
      showError(err.response?.data?.detail || t('apiConnectors.deleteFailed'))
      deleteConfirm.setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t('apiConnectors.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('apiConnectors.description')}</p>
        </div>
        {canCreateConnector && (
          <Button onClick={openCreateConnectorForm}>
            <Plus className="w-4 h-4 mr-2" />
            {t('apiConnectors.addButton')}
          </Button>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t('apiConnectors.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-9"
            />
            {searchQuery && (
              <Button
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1 h-7 w-7 p-0"
                onClick={() => setSearchQuery('')}
              >
                <X className="h-3 w-3" />
              </Button>
            )}
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="outline" onClick={() => fetchConnectors()} disabled={loading} size="sm">
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              {t('common.refresh')}
            </Button>
          </div>
        </div>

        {loading && connectors.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground py-8">{t('common.loading')}</p>
        ) : filteredConnectors.length === 0 ? (
          <div className="text-center py-12 border rounded-lg bg-muted/20">
            <Cable className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-50" />
            <p className="text-sm text-muted-foreground">
              {connectors.length === 0 ? t('apiConnectors.noConnectors') : t('apiConnectors.noMatchingConnectors')}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="overflow-hidden rounded-lg border bg-card">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="h-10">{t('apiConnectors.nameCol')}</TableHead>
                    <TableHead className="h-10 w-32">{t('apiConnectors.ownerCol')}</TableHead>
                    <TableHead className="h-10">{t('apiConnectors.baseUrlCol')}</TableHead>
                    <TableHead className="h-10 w-28">{t('apiConnectors.authCol')}</TableHead>
                    <TableHead className="h-10 w-36">{t('apiConnectors.schemaCol')}</TableHead>
                    <TableHead className="h-10 w-40">{t('apiConnectors.lastSyncCol')}</TableHead>
                    <TableHead className="h-10 w-24 text-right">{t('common.action')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredConnectors.map((connector) => (
                    <TableRow key={connector.id}>
                      <TableCell className="py-2.5">
                        <div className="flex flex-col gap-1">
                          <button
                            className="text-sm font-medium hover:underline text-left"
                            onClick={() => openConnectorManagement(connector.id)}
                          >
                            {connector.name}
                          </button>
                          {canReadTags && (connectorTagsMap[connector.id]?.length || 0) > 0 && (
                            <TagChips tags={connectorTagsMap[connector.id]} tagKeys={tagKeys} compact />
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="py-2.5">
                        <span className="text-sm">{connector.owner_name || t('apiConnectors.deletedUser')}</span>
                      </TableCell>
                      <TableCell className="py-2.5 font-mono text-xs">
                        {connector.base_url}
                      </TableCell>
                      <TableCell className="py-2.5">
                        <Badge variant="outline">{connector.auth_type}</Badge>
                      </TableCell>
                      <TableCell className="py-2.5 text-sm">
                        {connector.schema_source_type}
                      </TableCell>
                      <TableCell className="py-2.5 text-sm text-muted-foreground">
                        {formatDate(connector.schema_last_synced_at)}
                      </TableCell>
                      <TableCell className="py-2.5 text-right">
                        <ContainerRowActions
                          onShare={() => setSharingConnector(connector)}
                          shareTitle={t('apiConnectors.share')}
                          tags={
                            canReadTags
                              ? {
                                  resourceType: TAG_RESOURCE_TYPES.API_CONNECTOR,
                                  resourceId: connector.id,
                                  resourceTitle: connector.name,
                                  canRead: canReadTags,
                                  canManage: canManageTags,
                                  onTagsUpdated: setConnectorTags,
                                }
                              : undefined
                          }
                          tagsTitle={t('apiConnectors.manageTags')}
                          onEdit={() => openEditConnectorForm(connector)}
                          editHidden={!canEditConnector}
                          editTitle={t('apiConnectors.editConnector')}
                          onDelete={() => deleteConfirm.open(connector)}
                          deleteHidden={!canDeleteConnector}
                          deleteTitle={t('apiConnectors.deleteConnector')}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
      </div>

      <AddApiConnectorDialog
        open={addDialogOpen}
        submitting={loading}
        onOpenChange={setAddDialogOpen}
        onCreate={addConnector}
        onCreated={(created) => {
          openConnectorManagement(created.id)
        }}
      />

      <AddApiConnectorDialog
        open={editDialogOpen}
        submitting={loading}
        connector={editingConnector}
        onOpenChange={(nextOpen) => {
          setEditDialogOpen(nextOpen)
          if (!nextOpen) {
            setEditingConnector(null)
          }
        }}
        onUpdate={modifyConnector}
        onUpdated={(updated) => {
          setEditingConnector(updated)
        }}
      />

      <ConfirmationDialog
        open={deleteConfirm.isOpen}
        item={deleteConfirm.item}
        isLoading={deleteConfirm.isLoading}
        title={t('common.delete')}
        description={(item) => t('apiConnectors.confirmDelete', { name: item.name })}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={handleDeleteConnector}
        onCancel={deleteConfirm.close}
      />

      {sharingConnector && (
        <ResourceAclShareDialog
          open={Boolean(sharingConnector)}
          onOpenChange={(open) => {
            if (!open) {
              setSharingConnector(null)
            }
          }}
          resourceType={ACL_SHARE_RESOURCE_TYPES.API_CONNECTOR}
          resourceId={sharingConnector.id}
          resourceTitle={sharingConnector.name}
        />
      )}
    </div>
  )
}
