import ContainerRowActions from '@/components/ContainerRowActions'
import CollectionsDialogs from '@/components/knowledge-base/CollectionsDialogs'
import ListIndexToolbar from '@/components/ListIndexToolbar'
import TagChips from '@/components/TagChips'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useCollectionsPage } from '@/hooks/useCollectionsPage'
import { formatDate } from '@/lib/dateTime'
import { TAG_RESOURCE_TYPES } from '@/lib/tagsApi'
import i18n from '@/i18n/config'
import { Cloud, FolderOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle('en', 'translation', {
  knowledgeBase: {
    title: 'Knowledge Base',
    description: 'Manage and upload unstructured documents for knowledge retrieval and Q&A',
    collections: 'Collections',
    searchCollections: 'Search collections...',
    newCollection: 'New Collection',
    noCollections: 'No collections yet',
    noCollectionsDesc: 'Create a collection to organize documents and control access.',
    shareCollection: 'Share',
    collectionTags: 'Tags',
    renameCollection: 'Rename',
    deleteCollection: 'Delete',
    selectCollection: 'Select a collection to view documents',
    searchPlaceholder: 'Search documents...',
    uploadDocument: 'Upload',
    uploadFirstDocument: 'Upload your first document',
    emptyCollectionDesc: 'Upload documents to this collection for search and Q&A.',
    noDocuments: 'No documents yet',
    batchTagCount: 'Tag ({{count}})',
    deleteSelected: 'Delete ({{count}})',
    confirmBatchDelete: 'Delete Multiple Documents',
    confirmBatchDeleteDesc: 'Are you sure you want to delete {{count}} documents?',
    confirmDeleteCollection: 'Delete Collection',
    confirmDeleteCollectionDesc: 'Delete "{{name}}"?',
    collectionNotEmpty: 'This collection has {{count}} documents. Delete or move them first.',
    deleteCollectionSuccess: 'Collection deleted',
    deleteCollectionFailed: 'Failed to delete collection',
    createCollectionSuccess: 'Collection created',
    updateCollectionSuccess: 'Collection updated',
    saveCollectionFailed: 'Failed to save collection',
    andMore: 'and {{count}} more...',
    batchDriveDeleteWarning:
      '{{count}} selected document(s) are synced from Google Drive and may reappear after the next sync.',
    irreversible: 'This action cannot be undone.',
    batchDelete: 'Delete',
    ownerLabel: 'Owner: {{name}}',
    queueCollectionReparse: 'Queue re-parse all',
    queueCollectionReindex: 'Queue re-index all',
    collectionReparseQueued: 'Queued {{count}} documents for re-parse',
    collectionReindexQueued: 'Queued {{count}} documents for re-index',
    reparseQueued: 'Queued for re-parse',
    reindexQueued: 'Queued for re-index',
    fileTooLarge: 'This file exceeds the upload size limit. Choose a smaller file or split the document.',
    driveConnected: 'Google Drive connected successfully',
    driveConnectError: 'Failed to connect Google Drive',
    nameCol: 'Name',
    docsCol: 'Documents',
    ownerCol: 'Owner',
    syncCol: 'Drive Sync',
    descCol: 'Description',
    updatedCol: 'Updated',
    syncActive: 'Synced',
    syncStopped: 'Stopped',
    syncFolder: 'Folder: {{name}}',
    noMatchingCollections: 'No matching collections',
    openCollection: 'Open collection {{name}}',
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  knowledgeBase: {
    title: '知识库',
    description: '管理和上传非结构化文档，用于知识检索和问答',
    collections: '集合',
    searchCollections: '搜索集合...',
    newCollection: '新建集合',
    noCollections: '暂无集合',
    noCollectionsDesc: '创建集合以组织文档并管理访问权限。',
    shareCollection: '共享',
    collectionTags: '标签',
    renameCollection: '重命名',
    deleteCollection: '删除',
    selectCollection: '请选择一个集合查看文档',
    searchPlaceholder: '搜索文档...',
    uploadDocument: '上传',
    uploadFirstDocument: '上传第一个文档',
    emptyCollectionDesc: '向此集合上传文档，用于检索与问答。',
    noDocuments: '暂无文档',
    batchTagCount: '标签（{{count}}）',
    deleteSelected: '删除（{{count}}）',
    confirmBatchDelete: '批量删除文档',
    confirmBatchDeleteDesc: '确定要删除{{count}}个文档吗？',
    confirmDeleteCollection: '删除集合',
    confirmDeleteCollectionDesc: '确定删除"{{name}}"？',
    collectionNotEmpty: '此集合中有 {{count}} 个文档，请先删除或移出文档。',
    deleteCollectionSuccess: '集合已删除',
    deleteCollectionFailed: '删除集合失败',
    createCollectionSuccess: '集合已创建',
    updateCollectionSuccess: '集合已更新',
    saveCollectionFailed: '保存集合失败',
    andMore: '还有{{count}}个...',
    batchDriveDeleteWarning:
      '所选 {{count}} 个文档来自 Google Drive 同步，下次同步后可能会重新出现。',
    irreversible: '此操作不可撤销。',
    batchDelete: '删除',
    ownerLabel: '所有者：{{name}}',
    queueCollectionReparse: '全部排队重新解析',
    queueCollectionReindex: '全部排队重新索引',
    collectionReparseQueued: '已将 {{count}} 个文档加入重新解析队列',
    collectionReindexQueued: '已将 {{count}} 个文档加入重新索引队列',
    reparseQueued: '已加入重新解析队列',
    reindexQueued: '已加入重新索引队列',
    fileTooLarge: '文件超过上传大小上限，请选择更小的文件或拆分文档。',
    driveConnected: 'Google Drive 连接成功',
    driveConnectError: 'Google Drive 连接失败',
    nameCol: '名称',
    docsCol: '文档数',
    ownerCol: '所有者',
    syncCol: 'Drive 同步',
    descCol: '描述',
    updatedCol: '更新时间',
    syncActive: '已同步',
    syncStopped: '已停止',
    syncFolder: '文件夹：{{name}}',
    noMatchingCollections: '没有匹配的集合',
    openCollection: '打开集合 {{name}}',
  },
}, true, true)

export default function KnowledgeBasePage() {
  const { t } = useTranslation()
  const page = useCollectionsPage()

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t('knowledgeBase.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('knowledgeBase.description')}</p>
      </div>

      <ListIndexToolbar
        searchQuery={page.collectionSearch}
        searchPlaceholder={t('knowledgeBase.searchCollections')}
        onSearchQueryChange={page.setCollectionSearch}
        onClearSearchQuery={() => page.setCollectionSearch('')}
        onRefresh={() => page.refetchCollections()}
        refreshing={page.collectionsLoading}
        refreshLabel={t('common.refresh')}
        primaryAction={{
          label: t('knowledgeBase.newCollection'),
          onClick: page.onCreateCollection,
          hidden: !page.canUpload,
        }}
      />

      {page.collectionsLoading && page.collections.length === 0 ? (
        <p className="text-center text-sm text-muted-foreground py-8">{t('common.loading')}</p>
      ) : page.collections.length === 0 ? (
        <div className="text-center py-12 border rounded-lg bg-card">
          <FolderOpen className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-50" />
          <p className="text-sm font-medium">{t('knowledgeBase.noCollections')}</p>
          <p className="text-sm text-muted-foreground mt-1">{t('knowledgeBase.noCollectionsDesc')}</p>
          {page.canUpload && (
            <Button variant="outline" className="mt-4" onClick={page.onCreateCollection}>
              {t('knowledgeBase.newCollection')}
            </Button>
          )}
        </div>
      ) : page.filteredCollections.length === 0 ? (
        <p className="text-center text-sm text-muted-foreground py-8">
          {t('knowledgeBase.noMatchingCollections')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <Table className="table-fixed w-full">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-10 w-[34%] min-w-[12rem]">{t('knowledgeBase.nameCol')}</TableHead>
                <TableHead className="h-10 w-20 text-center">{t('knowledgeBase.docsCol')}</TableHead>
                <TableHead className="h-10 w-28 hidden md:table-cell">{t('knowledgeBase.ownerCol')}</TableHead>
                <TableHead className="h-10 w-36 hidden lg:table-cell">{t('knowledgeBase.syncCol')}</TableHead>
                <TableHead className="h-10 hidden xl:table-cell">{t('knowledgeBase.descCol')}</TableHead>
                <TableHead className="h-10 w-36 hidden sm:table-cell">{t('knowledgeBase.updatedCol')}</TableHead>
                <TableHead className="h-10 w-28 text-right">{t('common.action')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page.filteredCollections.map((collection) => (
                <TableRow key={collection.id}>
                  <TableCell className="py-2.5 max-w-0">
                    <button
                      type="button"
                      className="flex items-start gap-2 min-w-0 w-full text-left group"
                      onClick={() => page.onNavigateToCollection(collection.id)}
                      aria-label={t('knowledgeBase.openCollection', { name: collection.name })}
                    >
                      <FolderOpen className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground" />
                      <div className="min-w-0 flex-1 space-y-1">
                        <span className="text-sm font-medium truncate block group-hover:underline">
                          {collection.name}
                        </span>
                        {page.canReadTags && (page.collectionTagsMap[collection.id]?.length || 0) > 0 ? (
                          <TagChips
                            tags={page.collectionTagsMap[collection.id]}
                            tagKeys={page.tagKeys}
                            compact
                            maxVisible={2}
                          />
                        ) : null}
                      </div>
                    </button>
                  </TableCell>
                  <TableCell className="py-2.5 text-center text-sm tabular-nums">
                    {collection.document_count}
                  </TableCell>
                  <TableCell className="py-2.5 text-sm hidden md:table-cell truncate">
                    {collection.owner_name || '—'}
                  </TableCell>
                  <TableCell className="py-2.5 hidden lg:table-cell">
                    {collection.has_drive_sync ? (
                      <div className="space-y-0.5 min-w-0">
                        <Badge variant="outline" className="h-5 gap-1 px-1.5 text-[11px] font-normal">
                          <Cloud className="h-3 w-3" />
                          {collection.sync_status === 'active'
                            ? t('knowledgeBase.syncActive')
                            : t('knowledgeBase.syncStopped')}
                        </Badge>
                        {collection.sync_folder_name ? (
                          <p
                            className="text-xs text-muted-foreground truncate"
                            title={collection.sync_folder_name}
                          >
                            {t('knowledgeBase.syncFolder', { name: collection.sync_folder_name })}
                          </p>
                        ) : null}
                      </div>
                    ) : (
                      <span className="text-sm text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="py-2.5 hidden xl:table-cell max-w-0">
                    <p className="text-sm text-muted-foreground truncate" title={collection.description ?? undefined}>
                      {collection.description || '—'}
                    </p>
                  </TableCell>
                  <TableCell className="py-2.5 text-sm hidden sm:table-cell">
                    {formatDate(collection.updated_at)}
                  </TableCell>
                  <TableCell className="py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                    <ContainerRowActions
                      onShare={() => page.onShareCollection(collection)}
                      shareTitle={t('knowledgeBase.shareCollection')}
                      tags={{
                        resourceType: TAG_RESOURCE_TYPES.DOCUMENT_COLLECTION,
                        resourceId: collection.id,
                        resourceTitle: collection.name,
                        canRead: page.canReadTags,
                        canManage: page.canManageTags,
                        onTagsUpdated: page.setCollectionTags,
                      }}
                      tagsTitle={t('knowledgeBase.collectionTags')}
                      onEdit={() => page.onEditCollection(collection)}
                      editHidden={!collection.can_write}
                      editTitle={t('knowledgeBase.renameCollection')}
                      onDelete={() => page.onDeleteCollectionClick(collection)}
                      deleteHidden={!collection.can_write}
                      deleteTitle={t('knowledgeBase.deleteCollection')}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <CollectionsDialogs
        activeCollection={page.activeCollection}
        canReadTags={page.canReadTags}
        canManageTags={page.canManageTags}
        formOpen={page.formOpen}
        formMode={page.formMode}
        isFormSubmitting={page.isFormSubmitting}
        shareOpen={page.shareOpen}
        tagsOpen={page.tagsOpen}
        onTagsOpenChange={page.setTagsOpen}
        onCollectionTagsUpdated={page.setCollectionTags}
        deleteCollectionConfirm={page.deleteCollectionConfirm}
        onFormOpenChange={page.setFormOpen}
        onCollectionFormSubmit={page.onCollectionFormSubmit}
        onShareOpenChange={page.setShareOpen}
        onDeleteCollectionConfirm={page.onDeleteCollectionConfirm}
      />
    </div>
  )
}
