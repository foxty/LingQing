import type { CollectionFormValues } from '@/components/CollectionFormDialog'
import { useAuth } from '@/hooks/useAuth'
import { useConfirmation, type UseConfirmationReturn } from '@/hooks/useConfirmation'
import {
  useCreateDocumentCollection,
  useDeleteDocumentCollection,
  useDocumentCollections,
  useUpdateDocumentCollection,
} from '@/hooks/useDocumentCollections'
import { useDriveOAuthCallback } from '@/hooks/useDriveOAuthCallback'
import { useNotification } from '@/hooks/useNotification'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { actionRules } from '@/lib/permissionRules'
import { TAG_RESOURCE_TYPES } from '@/lib/tagsApi'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useResourceListTags } from '@/hooks/useResourceListTags'

export function useCollectionsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showSuccess, showError } = useNotification()
  useDriveOAuthCallback()

  const [collectionSearch, setCollectionSearch] = useState('')
  const [shareOpen, setShareOpen] = useState(false)
  const [tagsOpen, setTagsOpen] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create')
  const [activeCollection, setActiveCollection] = useState<DocumentCollection | null>(null)

  const { hasAny } = useAuth()
  const canReadTags = hasAny(actionRules.canReadTags())
  const canManageTags = hasAny(actionRules.canManageTags())
  const canUpload = hasAny(actionRules.canUploadDocument())

  const { data: collections = [], isLoading: collectionsLoading, refetch } = useDocumentCollections()
  const { tagKeys, tagsMap: collectionTagsMap, setTagsForResource: setCollectionTags } =
    useResourceListTags(TAG_RESOURCE_TYPES.DOCUMENT_COLLECTION, collections, canReadTags)

  const createCollection = useCreateDocumentCollection()
  const updateCollection = useUpdateDocumentCollection()
  const deleteCollection = useDeleteDocumentCollection()
  const deleteCollectionConfirm = useConfirmation<DocumentCollection | null>(null)

  const filteredCollections = useMemo(() => {
    const q = collectionSearch.trim().toLowerCase()
    if (!q) return collections
    return collections.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.description?.toLowerCase().includes(q) ?? false) ||
        (c.sync_folder_name?.toLowerCase().includes(q) ?? false)
    )
  }, [collections, collectionSearch])

  const openCreateDialog = () => {
    setActiveCollection(null)
    setFormMode('create')
    setFormOpen(true)
  }

  const openEditDialog = (collection: DocumentCollection) => {
    setActiveCollection(collection)
    setFormMode('edit')
    setFormOpen(true)
  }

  const openShareDialog = (collection: DocumentCollection) => {
    setActiveCollection(collection)
    setShareOpen(true)
  }

  const openTagsDialog = (collection: DocumentCollection) => {
    setActiveCollection(collection)
    setTagsOpen(true)
  }

  const handleCollectionFormSubmit = async (values: CollectionFormValues) => {
    try {
      if (formMode === 'create') {
        const created = await createCollection.mutateAsync({
          name: values.name,
          description: values.description || null,
        })
        showSuccess(t('knowledgeBase.createCollectionSuccess'))
        setFormOpen(false)
        navigate(`/knowledge/collections/${created.id}`)
      } else if (activeCollection) {
        await updateCollection.mutateAsync({
          collectionId: activeCollection.id,
          payload: {
            name: values.name,
            description: values.description || null,
          },
        })
        showSuccess(t('knowledgeBase.updateCollectionSuccess'))
        setFormOpen(false)
      }
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('knowledgeBase.saveCollectionFailed')
      showError(message)
    }
  }

  const handleDeleteCollectionClick = (collection: DocumentCollection) => {
    deleteCollectionConfirm.open(collection)
  }

  const handleDeleteCollectionConfirm = async (collection: DocumentCollection | null) => {
    if (!collection) return
    if (collection.document_count > 0) {
      showError(t('knowledgeBase.collectionNotEmpty', { count: collection.document_count }))
      deleteCollectionConfirm.close()
      return
    }
    deleteCollectionConfirm.setLoading(true)
    try {
      await deleteCollection.mutateAsync(collection.id)
      showSuccess(t('knowledgeBase.deleteCollectionSuccess'))
      deleteCollectionConfirm.close()
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('knowledgeBase.deleteCollectionFailed')
      showError(message)
    } finally {
      deleteCollectionConfirm.setLoading(false)
    }
  }

  const navigateToCollection = (collectionId: number) => {
    navigate(`/knowledge/collections/${collectionId}`)
  }

  return {
    collections,
    collectionsLoading,
    filteredCollections,
    collectionSearch,
    setCollectionSearch,
    refetchCollections: refetch,
    canUpload,
    canReadTags,
    canManageTags,
    tagKeys,
    collectionTagsMap,
    setCollectionTags,
    onCreateCollection: openCreateDialog,
    onEditCollection: openEditDialog,
    onShareCollection: openShareDialog,
    onTagsCollection: openTagsDialog,
    onDeleteCollectionClick: handleDeleteCollectionClick,
    onNavigateToCollection: navigateToCollection,
    shareOpen,
    setShareOpen,
    tagsOpen,
    setTagsOpen,
    activeCollection,
    formOpen,
    setFormOpen,
    formMode,
    isFormSubmitting: createCollection.isPending || updateCollection.isPending,
    onCollectionFormSubmit: handleCollectionFormSubmit,
    deleteCollectionConfirm,
    onDeleteCollectionConfirm: handleDeleteCollectionConfirm,
  }
}

export type CollectionsPageState = ReturnType<typeof useCollectionsPage>
export type CollectionsDeleteConfirm = UseConfirmationReturn<DocumentCollection | null>
