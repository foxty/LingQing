import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createDocumentCollection,
  deleteDocumentCollection,
  getDocumentCollection,
  listDocumentCollections,
  reindexDocumentCollection,
  reparseDocumentCollection,
  updateDocumentCollection,
  type DocumentCollectionCreate,
  type DocumentCollectionUpdate,
} from '@/lib/documentCollectionsApi'
import { useNotification } from '@/hooks/useNotification'
import i18n from '@/i18n/config'
import { invalidateAgentAttachmentPickerQueries } from '@/lib/agentAttachmentPicker'
import { useAuth } from './useAuth'

export function documentCollectionsListQueryKey(
  tenantId: number | undefined,
  page: number,
  pageSize: number,
  query?: string
) {
  return ['document-collections', tenantId, page, pageSize, query ?? ''] as const
}

export function useDocumentCollectionsList(page: number, pageSize: number, query?: string) {
  const { user } = useAuth()
  const normalizedQuery = query?.trim() || undefined

  return useQuery({
    queryKey: documentCollectionsListQueryKey(user?.tenantId, page, pageSize, normalizedQuery),
    queryFn: () => listDocumentCollections(page, pageSize, normalizedQuery),
    enabled: !!user,
  })
}

export function useDocumentCollection(collectionId: number | undefined) {
  const { user } = useAuth()

  return useQuery({
    queryKey: ['document-collection', user?.tenantId, collectionId],
    queryFn: () => getDocumentCollection(collectionId!),
    enabled: !!user && collectionId != null && !Number.isNaN(collectionId),
  })
}

function invalidateCollectionQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  tenantId: number | undefined
) {
  void queryClient.invalidateQueries({ queryKey: ['document-collections', tenantId] })
  void queryClient.invalidateQueries({ queryKey: ['document-collection', tenantId] })
  invalidateAgentAttachmentPickerQueries(queryClient, tenantId)
}

export function useCreateDocumentCollection() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: DocumentCollectionCreate) => createDocumentCollection(payload),
    onSuccess: () => {
      invalidateCollectionQueries(queryClient, user?.tenantId)
    },
  })
}

export function useUpdateDocumentCollection() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      collectionId,
      payload,
    }: {
      collectionId: number
      payload: DocumentCollectionUpdate
    }) => updateDocumentCollection(collectionId, payload),
    onSuccess: (_data, variables) => {
      invalidateCollectionQueries(queryClient, user?.tenantId)
      void queryClient.invalidateQueries({
        queryKey: ['document-collection', user?.tenantId, variables.collectionId],
      })
    },
  })
}

export function useDeleteDocumentCollection() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (collectionId: number) => deleteDocumentCollection(collectionId),
    onSuccess: () => {
      invalidateCollectionQueries(queryClient, user?.tenantId)
    },
  })
}

function useCollectionQueueMutation(
  mutationFn: (collectionId: number) => ReturnType<typeof reparseDocumentCollection>,
  defaultError: string,
  successKey: string
) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showError, showSuccess } = useNotification()

  return useMutation({
    mutationFn,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['documents', user?.tenantId] })
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
      showSuccess(i18n.t(successKey, { count: result.queued_count }))
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: string } }; message?: string }
      showError(err?.response?.data?.detail || err?.message || defaultError)
    },
  })
}

export function useReparseDocumentCollection() {
  return useCollectionQueueMutation(
    reparseDocumentCollection,
    'Failed to queue collection re-parse',
    'knowledgeBase.collectionReparseQueued'
  )
}

export function useReindexDocumentCollection() {
  return useCollectionQueueMutation(
    reindexDocumentCollection,
    'Failed to queue collection re-index',
    'knowledgeBase.collectionReindexQueued'
  )
}
