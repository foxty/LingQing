import EmptyState from '@/components/EmptyState'
import CollectionDetailPanel from '@/components/knowledge-base/CollectionDetailPanel'
import CollectionSidebar from '@/components/knowledge-base/CollectionSidebar'
import KnowledgeBaseDialogs from '@/components/knowledge-base/KnowledgeBaseDialogs'
import { Button } from '@/components/ui/button'
import { useKnowledgeBasePage } from '@/hooks/useKnowledgeBasePage'
import i18n from '@/i18n/config'
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
  },
}, true, true)

export default function KnowledgeBasePage() {
  const { t } = useTranslation()
  const kb = useKnowledgeBasePage()

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t('knowledgeBase.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('knowledgeBase.description')}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <CollectionSidebar
          collections={kb.collections}
          filteredCollections={kb.filteredCollections}
          isLoading={kb.collectionsLoading}
          selectedCollectionId={kb.selectedCollectionId}
          collectionSearch={kb.collectionSearch}
          showCollectionSearch={kb.showCollectionSearch}
          canUpload={kb.canUpload}
          canReadTags={kb.canReadTags}
          tagKeys={kb.tagKeys}
          collectionTagsMap={kb.collectionTagsMap}
          onCollectionSearchChange={kb.setCollectionSearch}
          onSelectCollection={kb.onSelectCollection}
          onCreateCollection={kb.onCreateCollection}
        />

        {!kb.selectedCollectionId || !kb.selectedCollection ? (
          <EmptyState
            title={t('knowledgeBase.noCollections')}
            description={t('knowledgeBase.selectCollection')}
            action={
              kb.canUpload && kb.collections.length === 0 ? (
                <Button size="sm" onClick={kb.onCreateCollection}>
                  {t('knowledgeBase.newCollection')}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <CollectionDetailPanel
            collection={kb.selectedCollection}
            data={kb.data}
            isLoading={kb.isLoading}
            normalizedQuery={kb.normalizedQuery}
            searchQuery={kb.searchQuery}
            selectedIds={kb.selectedIds}
            canUpload={kb.canUpload}
            canDelete={kb.canDelete}
            canReadTags={kb.canReadTags}
            uploading={kb.uploading}
            uploadProgress={kb.uploadProgress}
            onSearchQueryChange={kb.onSearchQueryChange}
            onClearSearchQuery={kb.onClearSearchQuery}
            onSelectionChange={kb.onSelectionChange}
            onPageChange={kb.onPageChange}
            onBatchDelete={kb.onBatchDeleteClick}
            onUpload={kb.triggerUpload}
            onShare={() => kb.setShareOpen(true)}
            onTags={() => kb.setTagsOpen(true)}
            onEdit={kb.onEditCollection}
            onDelete={kb.onDeleteCollectionClick}
            onReparseAll={kb.onReparseCollection}
            onReindexAll={kb.onReindexCollection}
            queuePending={kb.collectionQueuePending}
            onFileUpload={kb.handleFileUpload}
          />
        )}
      </div>

      <KnowledgeBaseDialogs
        selectedCollection={kb.selectedCollection}
        canReadTags={kb.canReadTags}
        canManageTags={kb.canManageTags}
        formOpen={kb.formOpen}
        formMode={kb.formMode}
        isFormSubmitting={kb.isFormSubmitting}
        shareOpen={kb.shareOpen}
        tagsOpen={kb.tagsOpen}
        onTagsOpenChange={kb.setTagsOpen}
        onCollectionTagsUpdated={kb.setCollectionTags}
        documentsData={kb.data}
        deleteBatchConfirm={kb.deleteBatchConfirm}
        deleteCollectionConfirm={kb.deleteCollectionConfirm}
        onFormOpenChange={kb.setFormOpen}
        onCollectionFormSubmit={kb.onCollectionFormSubmit}
        onShareOpenChange={kb.setShareOpen}
        onBatchDeleteConfirm={kb.onBatchDeleteConfirm}
        onDeleteCollectionConfirm={kb.onDeleteCollectionConfirm}
      />
    </div>
  )
}
