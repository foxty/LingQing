import type { CollectionFormValues } from '@/components/CollectionFormDialog'
import { useAuth } from '@/hooks/useAuth'
import { useConfirmation, type UseConfirmationReturn } from '@/hooks/useConfirmation'
import {
  useCreateDocumentCollection,
  useDeleteDocumentCollection,
  useDocumentCollectionsList,
  useUpdateDocumentCollection,
} from '@/hooks/useDocumentCollections'
import { useDriveOAuthCallback } from '@/hooks/useDriveOAuthCallback'
import { useNotification } from '@/hooks/useNotification'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { actionRules } from '@/lib/permissionRules'
import { TAG_RESOURCE_TYPES } from '@/lib/tagsApi'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useResourceListTags } from '@/hooks/useResourceListTags'

export const COLLECTIONS_PAGE_SIZE = 10

export function useCollectionsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showSuccess, showError } = useNotification()
  useDriveOAuthCallback()

  const [collectionSearch, setCollectionSearch] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [shareOpen, setShareOpen] = useState(false)
  const [tagsOpen, setTagsOpen] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create')
  const [activeCollection, setActiveCollection] = useState<DocumentCollection | null>(null)

  const { hasAny } = useAuth()
  const canReadTags = hasAny(actionRules.canReadTags())
  const canManageTags = hasAny(actionRules.canManageTags())
  const canUpload = hasAny(actionRules.canUploadDocument())

  const searchQuery = collectionSearch.trim() || undefined
  const {
    data: collectionsPage,
    isLoading: collectionsLoading,
    refetch,
  } = useDocumentCollectionsList(currentPage, COLLECTIONS_PAGE_SIZE, searchQuery)
  const collections = collectionsPage?.items ?? []
  const collectionsTotal = collectionsPage?.total ?? 0
  const collectionsTotalPages = collectionsPage?.total_pages ?? 0

  const { tagKeys, tagsMap: collectionTagsMap, setTagsForResource: setCollectionTags } =
    useResourceListTags(TAG_RESOURCE_TYPES.DOCUMENT_COLLECTION, collections, canReadTags)

  const createCollection = useCreateDocumentCollection()
  const updateCollection = useUpdateDocumentCollection()
  const deleteCollection = useDeleteDocumentCollection()
  const deleteCollectionConfirm = useConfirmation<DocumentCollection | null>(null)

  const setCollectionSearchAndResetPage = (value: string) => {
    setCurrentPage(1)
    setCollectionSearch(value)
  }

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
        await createCollection.mutateAsync(values)
        showSuccess(t('knowledgeBase.createCollectionSuccess'))
      } else if (activeCollection) {
        await updateCollection.mutateAsync({ collectionId: activeCollection.id, payload: values })
        showSuccess(t('knowledgeBase.updateCollectionSuccess'))
      }
      setFormOpen(false)
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
    if (!collection) {
      return
    }
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
    collectionsTotal,
    collectionsTotalPages,
    collectionsPage: currentPage,
    setCollectionsPage: setCurrentPage,
    collectionSearch,
    setCollectionSearch: setCollectionSearchAndResetPage,
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
