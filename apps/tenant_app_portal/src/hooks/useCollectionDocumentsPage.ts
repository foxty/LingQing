import { useAuth } from '@/hooks/useAuth'
import { useConfirmation, type UseConfirmationReturn } from '@/hooks/useConfirmation'
import {
  useDocumentCollections,
  useReindexDocumentCollection,
  useReparseDocumentCollection,
} from '@/hooks/useDocumentCollections'
import { useDeleteDocuments, useDocuments } from '@/hooks/useDocuments'
import { useDriveOAuthCallback } from '@/hooks/useDriveOAuthCallback'
import { useFileUpload } from '@/hooks/useFileUpload'
import type { PaginatedResponse } from '@/lib/documentsApi'
import { actionRules } from '@/lib/permissionRules'
import type { Document } from '@/types'
import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

const ITEMS_PER_PAGE = 10

export function useCollectionDocumentsPage() {
  useDriveOAuthCallback()

  const { collectionId: collectionIdParam } = useParams<{ collectionId: string }>()
  const collectionId = collectionIdParam ? Number.parseInt(collectionIdParam, 10) : undefined

  const [searchQuery, setSearchQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  const { hasAny } = useAuth()
  const canUpload = hasAny(actionRules.canUploadDocument())
  const canDelete = hasAny(actionRules.canDeleteDocument())

  const { data: collections = [], isLoading: collectionsLoading } = useDocumentCollections()
  const collection = useMemo(
    () => (collectionId != null ? collections.find((c) => c.id === collectionId) : undefined),
    [collectionId, collections]
  )

  const normalizedQuery = searchQuery.trim() || undefined
  const { data, isLoading: documentsLoading } = useDocuments(
    currentPage,
    ITEMS_PER_PAGE,
    normalizedQuery,
    collectionId
  )

  const { uploading, uploadProgress, handleFileUpload } = useFileUpload(collectionId)
  const deleteMultipleMutation = useDeleteDocuments()
  const reparseCollectionMutation = useReparseDocumentCollection()
  const reindexCollectionMutation = useReindexDocumentCollection()
  const deleteBatchConfirm = useConfirmation<number[]>([])

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage)
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
    if (!collectionId) return
    reparseCollectionMutation.mutate(collectionId)
  }

  const handleReindexCollection = () => {
    if (!collectionId) return
    reindexCollectionMutation.mutate(collectionId)
  }

  const handleSearchQueryChange = (value: string) => {
    setSearchQuery(value)
    setCurrentPage(1)
  }

  const clearSearchQuery = () => {
    setSearchQuery('')
    setCurrentPage(1)
  }

  return {
    collectionId,
    collection,
    collectionsLoading,
    canUpload: canUpload && (collection?.can_write ?? false),
    canDelete: canDelete && (collection?.can_write ?? false),
    canManageCollectionSync: collection?.can_manage ?? false,
    data,
    isLoading: documentsLoading,
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
    onReparseCollection: handleReparseCollection,
    onReindexCollection: handleReindexCollection,
    collectionQueuePending:
      reparseCollectionMutation.isPending || reindexCollectionMutation.isPending,
    deleteBatchConfirm,
    onBatchDeleteConfirm: handleBatchDeleteConfirm,
  }
}

export type CollectionDocumentsPageState = ReturnType<typeof useCollectionDocumentsPage>
export type CollectionDocumentsData = PaginatedResponse<Document> | undefined
export type CollectionDocumentsDeleteBatchConfirm = UseConfirmationReturn<number[]>
