import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createDocumentCollection,
  deleteDocumentCollection,
  listDocumentCollections,
  reindexDocumentCollection,
  reparseDocumentCollection,
  updateDocumentCollection,
  type DocumentCollection,
  type DocumentCollectionCreate,
  type DocumentCollectionUpdate,
} from '@/lib/documentCollectionsApi'
import { useNotification } from '@/hooks/useNotification'
import i18n from '@/i18n/config'
import { useAuth } from './useAuth'

export function useDocumentCollections() {
  const { user } = useAuth()

  return useQuery<DocumentCollection[]>({
    queryKey: ['document-collections', user?.tenantId],
    queryFn: listDocumentCollections,
    enabled: !!user,
  })
}

export function useCreateDocumentCollection() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: DocumentCollectionCreate) => createDocumentCollection(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
    },
  })
}

export function useDeleteDocumentCollection() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (collectionId: number) => deleteDocumentCollection(collectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
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
