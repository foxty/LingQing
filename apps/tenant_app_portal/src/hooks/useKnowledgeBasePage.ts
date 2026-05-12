import type { CollectionFormValues } from '@/components/CollectionFormDialog'
import { useAuth } from '@/hooks/useAuth'
import { useConfirmation, type UseConfirmationReturn } from '@/hooks/useConfirmation'
import {
  useCreateDocumentCollection,
  useDeleteDocumentCollection,
  useDocumentCollections,
  useReindexDocumentCollection,
  useReparseDocumentCollection,
  useUpdateDocumentCollection,
} from '@/hooks/useDocumentCollections'
import { useDeleteDocuments, useDocuments } from '@/hooks/useDocuments'
import { useFileUpload } from '@/hooks/useFileUpload'
import { useNotification } from '@/hooks/useNotification'
import type { PaginatedResponse } from '@/lib/documentsApi'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { actionRules } from '@/lib/permissionRules'
import { TAG_RESOURCE_TYPES } from '@/lib/tagsApi'
import type { Document } from '@/types'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useResourceListTags } from '@/hooks/useResourceListTags'

const ITEMS_PER_PAGE = 10

export function useKnowledgeBasePage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [searchQuery, setSearchQuery] = useState('')
  const [collectionSearch, setCollectionSearch] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [selectedCollectionId, setSelectedCollectionId] = useState<number | undefined>()
  const [shareOpen, setShareOpen] = useState(false)
  const [tagsOpen, setTagsOpen] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create')

  const { hasAny } = useAuth()
  const canReadTags = hasAny(actionRules.canReadTags())
  const canManageTags = hasAny(actionRules.canManageTags())
  const canUpload = hasAny(actionRules.canUploadDocument())
  const canDelete = hasAny(actionRules.canDeleteDocument())

  const { data: collections = [], isLoading: collectionsLoading } = useDocumentCollections()
  const { tagKeys, tagsMap: collectionTagsMap, setTagsForResource: setCollectionTags } =
    useResourceListTags(TAG_RESOURCE_TYPES.DOCUMENT_COLLECTION, collections, canReadTags)
  const createCollection = useCreateDocumentCollection()
  const updateCollection = useUpdateDocumentCollection()
  const deleteCollection = useDeleteDocumentCollection()

  useEffect(() => {
    if (!selectedCollectionId && collections.length > 0) {
      setSelectedCollectionId(collections[0].id)
    }
  }, [collections, selectedCollectionId])

  useEffect(() => {
    if (selectedCollectionId && !collections.some((c) => c.id === selectedCollectionId)) {
      setSelectedCollectionId(collections[0]?.id)
    }
  }, [collections, selectedCollectionId])

  const filteredCollections = useMemo(() => {
    const q = collectionSearch.trim().toLowerCase()
    if (!q) return collections
    return collections.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.description?.toLowerCase().includes(q) ?? false)
    )
  }, [collections, collectionSearch])

  const selectedCollection = useMemo(
    () => collections.find((c) => c.id === selectedCollectionId),
    [collections, selectedCollectionId]
  )

  const normalizedQuery = searchQuery.trim() || undefined
  const { data, isLoading } = useDocuments(
    currentPage,
    ITEMS_PER_PAGE,
    normalizedQuery,
    selectedCollectionId
  )

  const { uploading, uploadProgress, handleFileUpload } = useFileUpload(selectedCollectionId)

  const deleteMultipleMutation = useDeleteDocuments()
  const reparseCollectionMutation = useReparseDocumentCollection()
  const reindexCollectionMutation = useReindexDocumentCollection()
  const deleteBatchConfirm = useConfirmation<number[]>([])
  const deleteCollectionConfirm = useConfirmation<DocumentCollection | null>(null)

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage)
  }

  const handleSelectCollection = (collectionId: number) => {
    setSelectedCollectionId(collectionId)
    setCurrentPage(1)
    setSelectedIds(new Set())
    setSearchQuery('')
  }

  const openCreateDialog = () => {
    setFormMode('create')
    setFormOpen(true)
  }

  const openEditDialog = () => {
    setFormMode('edit')
    setFormOpen(true)
  }

  const handleCollectionFormSubmit = async (values: CollectionFormValues) => {
    try {
      if (formMode === 'create') {
        const created = await createCollection.mutateAsync({
          name: values.name,
          description: values.description || null,
        })
        setSelectedCollectionId(created.id)
        showSuccess(t('knowledgeBase.createCollectionSuccess'))
      } else if (selectedCollection) {
        await updateCollection.mutateAsync({
          collectionId: selectedCollection.id,
          payload: {
            name: values.name,
            description: values.description || null,
          },
        })
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

  const handleDeleteCollectionClick = () => {
    if (selectedCollection) {
      deleteCollectionConfirm.open(selectedCollection)
    }
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

  const handleBatchDeleteClick = () => {
    deleteBatchConfirm.open(Array.from(selectedIds))
  }

  const handleBatchDeleteConfirm = (docIds: number[]) => {
    if (docIds.length === 0) return
    deleteBatchConfirm.setLoading(true)
    deleteMultipleMutation.mutate(docIds, {
      onSuccess: () => {
        setSelectedIds(new Set())
      },
      onSettled: () => {
        deleteBatchConfirm.setLoading(false)
        deleteBatchConfirm.close()
      },
    })
  }

  const triggerUpload = () => {
    document.getElementById('file-upload')?.click()
  }

  const handleReparseCollection = () => {
    if (!selectedCollectionId) return
    reparseCollectionMutation.mutate(selectedCollectionId)
  }

  const handleReindexCollection = () => {
    if (!selectedCollectionId) return
    reindexCollectionMutation.mutate(selectedCollectionId)
  }

  const collectionQueuePending =
    reparseCollectionMutation.isPending || reindexCollectionMutation.isPending

  const handleSearchQueryChange = (value: string) => {
    setSearchQuery(value)
    setCurrentPage(1)
  }

  const clearSearchQuery = () => {
    setSearchQuery('')
    setCurrentPage(1)
  }

  const isFormSubmitting = createCollection.isPending || updateCollection.isPending
  const showCollectionSearch = collections.length > 3

  return {
    collections,
    collectionsLoading,
    filteredCollections,
    collectionSearch,
    setCollectionSearch,
    selectedCollectionId,
    selectedCollection,
    showCollectionSearch,
    onSelectCollection: handleSelectCollection,
    onCreateCollection: openCreateDialog,
    canUpload,
    canDelete,
    canReadTags,
    canManageTags,
    data,
    isLoading,
    normalizedQuery,
    searchQuery,
    onSearchQueryChange: handleSearchQueryChange,
    onClearSearchQuery: clearSearchQuery,
    selectedIds,
    onSelectionChange: setSelectedIds,
    onPageChange: handlePageChange,
    onBatchDeleteClick: handleBatchDeleteClick,
    uploading,
    uploadProgress,
    handleFileUpload,
    triggerUpload,
    onEditCollection: openEditDialog,
    onDeleteCollectionClick: handleDeleteCollectionClick,
    onReparseCollection: handleReparseCollection,
    onReindexCollection: handleReindexCollection,
    collectionQueuePending,
    shareOpen,
    setShareOpen,
    tagsOpen,
    setTagsOpen,
    tagKeys,
    collectionTagsMap,
    setCollectionTags,
    formOpen,
    setFormOpen,
    formMode,
    isFormSubmitting,
    onCollectionFormSubmit: handleCollectionFormSubmit,
    deleteBatchConfirm,
    onBatchDeleteConfirm: handleBatchDeleteConfirm,
    deleteCollectionConfirm,
    onDeleteCollectionConfirm: handleDeleteCollectionConfirm,
  }
}

export type KnowledgeBasePageState = ReturnType<typeof useKnowledgeBasePage>
export type KnowledgeBaseDocumentsData = PaginatedResponse<Document> | undefined
export type KnowledgeBaseDeleteBatchConfirm = UseConfirmationReturn<number[]>
export type KnowledgeBaseDeleteCollectionConfirm = UseConfirmationReturn<DocumentCollection | null>
