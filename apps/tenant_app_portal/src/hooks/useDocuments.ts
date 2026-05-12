import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from './useAuth'
import {
  getDocuments,
  deleteDocuments,
  uploadDocument,
  reparseDocument,
  reindexDocument,
  getParsedDocument,
  type PaginatedResponse,
  type ApiParsedDocument,
} from '@/lib/documentsApi'
import type { Document } from '@/types'
import { convertApiDocumentToDocument } from '@/types'
import { useNotification } from '@/hooks/useNotification'
import i18n from '@/i18n/config'

/**
 * Custom hook to fetch documents for the current tenant with pagination
 * Tenant is automatically determined from authentication
 */
export function useDocuments(
  page: number = 1,
  pageSize: number = 10,
  query?: string,
  collectionId?: number
) {
  const { user } = useAuth()

  return useQuery<PaginatedResponse<Document>>({
    queryKey: ['documents', user?.tenantId, page, pageSize, query, collectionId],
    queryFn: async () => {
      const response = await getDocuments(page, pageSize, query, collectionId)
      return {
        items: response.items.map(convertApiDocumentToDocument),
        total: response.total,
        page: response.page,
        page_size: response.page_size,
        total_pages: response.total_pages,
      }
    },
    enabled: !!user,
  })
}

/**
 * Custom hook to delete one or multiple documents
 * Tenant is automatically determined from authentication
 * Supports both single document ID and array of IDs
 */
export function useDeleteDocuments() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showError } = useNotification()

  return useMutation({
    mutationFn: async (documentIds: number | number[]) => {
      const ids = Array.isArray(documentIds) ? documentIds : [documentIds]
      await deleteDocuments(ids)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', user?.tenantId] })
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
    },
    onError: (error: any) => {
      let errorMsg = 'Failed to delete documents'
      if (error?.response?.data?.detail) {
        errorMsg = error.response.data.detail
      } else if (error?.response?.data?.message) {
        errorMsg = error.response.data.message
      } else if (error?.message) {
        errorMsg = error.message
      }
      showError(errorMsg)
    },
  })
}

/**
 * Custom hook to upload documents
 * Tenant is automatically determined from authentication
 */
export function useUploadDocument(collectionId: number) {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (file: File) => {
      await uploadDocument(file, collectionId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', user?.tenantId] })
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
    },
  })
}

export function useDocumentParsed(documentId: number | null) {
  return useQuery<ApiParsedDocument>({
    queryKey: ['document-parsed', documentId],
    queryFn: () => getParsedDocument(documentId as number),
    enabled: documentId != null,
  })
}

function useInvalidateDocuments() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  return () => {
    queryClient.invalidateQueries({ queryKey: ['documents', user?.tenantId] })
    queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
  }
}

function useDocumentMutationError(defaultMessage: string) {
  const { showError } = useNotification()

  return (error: unknown) => {
    const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
    const errorMsg =
      err?.response?.data?.detail ||
      err?.response?.data?.message ||
      err?.message ||
      defaultMessage
    showError(errorMsg)
  }
}

export function useReparseDocument() {
  const invalidate = useInvalidateDocuments()
  const onError = useDocumentMutationError('Failed to queue document re-parse')
  const { showSuccess } = useNotification()

  return useMutation({
    mutationFn: reparseDocument,
    onSuccess: () => {
      invalidate()
      showSuccess(i18n.t('knowledgeBase.reparseQueued'))
    },
    onError,
  })
}

export function useReindexDocument() {
  const invalidate = useInvalidateDocuments()
  const onError = useDocumentMutationError('Failed to queue document re-index')
  const { showSuccess } = useNotification()

  return useMutation({
    mutationFn: reindexDocument,
    onSuccess: () => {
      invalidate()
      showSuccess(i18n.t('knowledgeBase.reindexQueued'))
    },
    onError,
  })
}
