import ContainerDetailHeader from '@/components/ContainerDetailHeader'
import EmptyState from '@/components/EmptyState'
import CollectionDetailPanel from '@/components/knowledge-base/CollectionDetailPanel'
import DocumentBatchDeleteDialog from '@/components/knowledge-base/DocumentBatchDeleteDialog'
import { Button } from '@/components/ui/button'
import { useCollectionDocumentsPage } from '@/hooks/useCollectionDocumentsPage'
import i18n from '@/i18n/config'
import { Database, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

i18n.addResourceBundle('en', 'translation', {
  knowledgeBase: {
    collectionNotFound: 'Collection not found',
    collectionNotFoundDesc: 'This collection may have been deleted or you may not have access.',
    backToCollections: 'Back to collections',
    pipelineStatus: 'Pipeline',
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  knowledgeBase: {
    collectionNotFound: '集合不存在',
    collectionNotFoundDesc: '该集合可能已被删除，或您没有访问权限。',
    backToCollections: '返回集合列表',
    pipelineStatus: '处理状态',
  },
}, true, true)

export default function CollectionDocumentsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const page = useCollectionDocumentsPage()

  if (!page.collectionsLoading && page.collectionId != null && !page.collection) {
    return (
      <EmptyState
        title={t('knowledgeBase.collectionNotFound')}
        description={t('knowledgeBase.collectionNotFoundDesc')}
        action={
          <Button size="sm" variant="outline" onClick={() => navigate('/knowledge')}>
            {t('knowledgeBase.backToCollections')}
          </Button>
        }
      />
    )
  }

  const collection = page.collection
  if (!collection) {
    return <p className="text-center text-sm text-muted-foreground py-8">{t('common.loading')}</p>
  }

  const overflowItems = [
    {
      label: t('knowledgeBase.queueCollectionReparse'),
      icon: RefreshCw,
      onClick: page.onReparseCollection,
      hidden: !page.canUpload,
    },
    {
      label: t('knowledgeBase.queueCollectionReindex'),
      icon: Database,
      onClick: page.onReindexCollection,
      hidden: !page.canUpload,
    },
  ]

  return (
    <div className="space-y-4">
      <ContainerDetailHeader
        parentLabel={t('knowledgeBase.title')}
        onParentNavigate={() => navigate('/knowledge')}
        title={collection.name}
        meta={
          <div className="space-y-0.5">
            {collection.description ? <p>{collection.description}</p> : null}
            {collection.owner_name ? (
              <p>{t('knowledgeBase.ownerLabel', { name: collection.owner_name })}</p>
            ) : null}
          </div>
        }
      />

      <CollectionDetailPanel
        collection={collection}
        data={page.data}
        isLoading={page.isLoading}
        normalizedQuery={page.normalizedQuery}
        searchQuery={page.searchQuery}
        selectedIds={page.selectedIds}
        canUpload={page.canUpload}
        canDelete={page.canDelete}
        canManageCollectionSync={page.canManageCollectionSync}
        uploading={page.uploading}
        uploadProgress={page.uploadProgress}
        onUpload={page.triggerUpload}
        onBatchDelete={page.onBatchDeleteClick}
        overflowItems={overflowItems}
        onSearchQueryChange={page.onSearchQueryChange}
        onClearSearchQuery={page.onClearSearchQuery}
        onSelectionChange={page.onSelectionChange}
        onPageChange={page.onPageChange}
        onFileUpload={page.handleFileUpload}
      />

      <DocumentBatchDeleteDialog
        documentsData={page.data}
        deleteBatchConfirm={page.deleteBatchConfirm}
        onBatchDeleteConfirm={page.onBatchDeleteConfirm}
      />
    </div>
  )
}
