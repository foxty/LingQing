import CollectionFormDialog, { type CollectionFormValues } from '@/components/CollectionFormDialog'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import TagBindingsDialog from '@/components/TagBindingsDialog'
import type {
  KnowledgeBaseDeleteBatchConfirm,
  KnowledgeBaseDeleteCollectionConfirm,
  KnowledgeBaseDocumentsData,
} from '@/hooks/useKnowledgeBasePage'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { TAG_RESOURCE_TYPES, type TagValueDTO } from '@/lib/tagsApi'
import { Trans, useTranslation } from 'react-i18next'

interface KnowledgeBaseDialogsProps {
  selectedCollection?: DocumentCollection
  canReadTags: boolean
  canManageTags: boolean
  formOpen: boolean
  formMode: 'create' | 'edit'
  isFormSubmitting: boolean
  shareOpen: boolean
  tagsOpen: boolean
  onTagsOpenChange: (open: boolean) => void
  onCollectionTagsUpdated: (resourceId: number, tags: TagValueDTO[]) => void
  documentsData: KnowledgeBaseDocumentsData
  deleteBatchConfirm: KnowledgeBaseDeleteBatchConfirm
  deleteCollectionConfirm: KnowledgeBaseDeleteCollectionConfirm
  onFormOpenChange: (open: boolean) => void
  onCollectionFormSubmit: (values: CollectionFormValues) => Promise<void>
  onShareOpenChange: (open: boolean) => void
  onBatchDeleteConfirm: (docIds: number[]) => void
  onDeleteCollectionConfirm: (collection: DocumentCollection | null) => Promise<void>
}

export default function KnowledgeBaseDialogs({
  selectedCollection,
  canReadTags,
  canManageTags,
  formOpen,
  formMode,
  isFormSubmitting,
  shareOpen,
  tagsOpen,
  onTagsOpenChange,
  onCollectionTagsUpdated,
  documentsData,
  deleteBatchConfirm,
  deleteCollectionConfirm,
  onFormOpenChange,
  onCollectionFormSubmit,
  onShareOpenChange,
  onBatchDeleteConfirm,
  onDeleteCollectionConfirm,
}: KnowledgeBaseDialogsProps) {
  const { t } = useTranslation()

  return (
    <>
      <CollectionFormDialog
        open={formOpen}
        onOpenChange={onFormOpenChange}
        mode={formMode}
        collection={formMode === 'edit' ? selectedCollection ?? null : null}
        isSubmitting={isFormSubmitting}
        onSubmit={onCollectionFormSubmit}
      />

      {selectedCollection && canReadTags && (
        <TagBindingsDialog
          resourceType={TAG_RESOURCE_TYPES.DOCUMENT_COLLECTION}
          resourceId={selectedCollection.id}
          title={t('knowledgeBase.collectionTags')}
          canManage={canManageTags}
          canRead={canReadTags}
          open={tagsOpen}
          onOpenChange={onTagsOpenChange}
          onTagsUpdated={onCollectionTagsUpdated}
        />
      )}

      {selectedCollection && (
        <ResourceAclShareDialog
          open={shareOpen}
          onOpenChange={onShareOpenChange}
          resourceType={ACL_SHARE_RESOURCE_TYPES.DOCUMENT_COLLECTION}
          resourceId={selectedCollection.id}
          resourceTitle={selectedCollection.name}
        />
      )}

      <ConfirmationDialog<number[]>
        open={deleteBatchConfirm.isOpen}
        item={deleteBatchConfirm.item}
        isLoading={deleteBatchConfirm.isLoading}
        title={t('knowledgeBase.confirmBatchDelete')}
        description={(docIds) => {
          const selectedDocs = documentsData?.items.filter((doc) => docIds?.includes(doc.id)) || []
          const driveLinkedCount = selectedDocs.filter((doc) => doc.intakeSource === 'drive_sync').length
          return (
            <>
              <Trans i18nKey="knowledgeBase.confirmBatchDeleteDesc" count={docIds?.length || 0} />
              {driveLinkedCount > 0 ? (
                <span className="text-amber-600 mt-2 block">
                  {t('knowledgeBase.batchDriveDeleteWarning', { count: driveLinkedCount })}
                </span>
              ) : null}
              <div className="mt-2 max-h-32 overflow-y-auto text-sm">
                <ul className="list-disc list-inside space-y-1">
                  {selectedDocs.slice(0, 5).map((doc) => (
                    <li key={doc.id} className="truncate">
                      {doc.filename}
                    </li>
                  ))}
                  {selectedDocs.length > 5 && (
                    <li className="text-muted-foreground">
                      {t('knowledgeBase.andMore', { count: selectedDocs.length - 5 })}
                    </li>
                  )}
                </ul>
              </div>
              <span className="text-red-600 mt-2 block">{t('knowledgeBase.irreversible')}</span>
            </>
          )
        }}
        confirmText={t('knowledgeBase.batchDelete')}
        isDangerous
        onConfirm={onBatchDeleteConfirm}
        onCancel={deleteBatchConfirm.close}
      />

      <ConfirmationDialog<DocumentCollection | null>
        open={deleteCollectionConfirm.isOpen}
        item={deleteCollectionConfirm.item}
        isLoading={deleteCollectionConfirm.isLoading}
        title={t('knowledgeBase.confirmDeleteCollection')}
        description={(collection) => {
          if (!collection) return null
          if (collection.document_count > 0) {
            return t('knowledgeBase.collectionNotEmpty', { count: collection.document_count })
          }
          return (
            <>
              {t('knowledgeBase.confirmDeleteCollectionDesc', { name: collection.name })}
              <span className="text-red-600 mt-2 block">{t('knowledgeBase.irreversible')}</span>
            </>
          )
        }}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={onDeleteCollectionConfirm}
        onCancel={deleteCollectionConfirm.close}
      />
    </>
  )
}
