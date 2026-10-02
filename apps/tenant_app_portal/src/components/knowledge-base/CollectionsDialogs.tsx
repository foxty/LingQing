import CollectionFormDialog, { type CollectionFormValues } from '@/components/CollectionFormDialog'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import TagBindingsDialog from '@/components/TagBindingsDialog'
import type { CollectionsDeleteConfirm } from '@/hooks/useCollectionsPage'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { TAG_RESOURCE_TYPES, type TagValueDTO } from '@/lib/tagsApi'
import { useTranslation } from 'react-i18next'

interface CollectionsDialogsProps {
  activeCollection: DocumentCollection | null
  canReadTags: boolean
  canManageTags: boolean
  formOpen: boolean
  formMode: 'create' | 'edit'
  isFormSubmitting: boolean
  shareOpen: boolean
  tagsOpen: boolean
  onTagsOpenChange: (open: boolean) => void
  onCollectionTagsUpdated: (resourceId: number, tags: TagValueDTO[]) => void
  deleteCollectionConfirm: CollectionsDeleteConfirm
  onFormOpenChange: (open: boolean) => void
  onCollectionFormSubmit: (values: CollectionFormValues) => Promise<void>
  onShareOpenChange: (open: boolean) => void
  onDeleteCollectionConfirm: (collection: DocumentCollection | null) => Promise<void>
}

export default function CollectionsDialogs({
  activeCollection,
  canReadTags,
  canManageTags,
  formOpen,
  formMode,
  isFormSubmitting,
  shareOpen,
  tagsOpen,
  onTagsOpenChange,
  onCollectionTagsUpdated,
  deleteCollectionConfirm,
  onFormOpenChange,
  onCollectionFormSubmit,
  onShareOpenChange,
  onDeleteCollectionConfirm,
}: CollectionsDialogsProps) {
  const { t } = useTranslation()

  return (
    <>
      <CollectionFormDialog
        open={formOpen}
        onOpenChange={onFormOpenChange}
        mode={formMode}
        collection={formMode === 'edit' ? activeCollection : null}
        isSubmitting={isFormSubmitting}
        onSubmit={onCollectionFormSubmit}
      />

      {activeCollection && canReadTags && (
        <TagBindingsDialog
          resourceType={TAG_RESOURCE_TYPES.DOCUMENT_COLLECTION}
          resourceId={activeCollection.id}
          title={t('knowledgeBase.collectionTags')}
          canManage={canManageTags}
          canRead={canReadTags}
          open={tagsOpen}
          onOpenChange={onTagsOpenChange}
          onTagsUpdated={onCollectionTagsUpdated}
        />
      )}

      {activeCollection && (
        <ResourceAclShareDialog
          open={shareOpen}
          onOpenChange={onShareOpenChange}
          resourceType={ACL_SHARE_RESOURCE_TYPES.DOCUMENT_COLLECTION}
          resourceId={activeCollection.id}
          resourceTitle={activeCollection.name}
        />
      )}

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
