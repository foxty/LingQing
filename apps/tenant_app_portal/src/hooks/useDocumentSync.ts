import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCollectionSyncConnector,
  deleteCollectionSyncConnector,
  disconnectSourceConnection,
  getCollectionSyncConnector,
  getGoogleDriveAuthorizeUrl,
  listSourceConnections,
  triggerConnectorSync,
  type CreateSyncConnectorRequest,
} from '@/lib/documentSyncApi'
import {
  getGoogleDriveSource,
  upsertGoogleDriveSource,
  type GoogleDriveSourceConfigUpsert,
} from '@/lib/documentSourcesApi'
import { getApiErrorMessage } from '@/lib/api'
import { useNotification } from '@/hooks/useNotification'
import i18n from '@/i18n/config'
import { useAuth } from './useAuth'

export function useGoogleDriveSource() {
  const { user } = useAuth()

  return useQuery({
    queryKey: ['document-sources', 'google-drive', user?.tenantId],
    queryFn: getGoogleDriveSource,
    enabled: !!user,
  })
}

export function useUpsertGoogleDriveSource() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (payload: GoogleDriveSourceConfigUpsert) => upsertGoogleDriveSource(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-sources', 'google-drive', user?.tenantId] })
      showSuccess(i18n.t('settings.documentSourcesTab.saveSuccess'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('settings.documentSourcesTab.saveFailed')))
    },
  })
}

export function useSourceConnections(enabled = true) {
  const { user } = useAuth()

  return useQuery({
    queryKey: ['document-sync', 'connections', user?.tenantId],
    queryFn: listSourceConnections,
    enabled: !!user && enabled,
  })
}

export function useGoogleDriveAuthorize() {
  const { showError } = useNotification()

  return useMutation({
    mutationFn: getGoogleDriveAuthorizeUrl,
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.connectFailed')))
    },
  })
}

export function useDisconnectSourceConnection() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (connectionId: number) => disconnectSourceConnection(connectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-sync', 'connections', user?.tenantId] })
      queryClient.invalidateQueries({ queryKey: ['document-sync', 'connector'] })
      showSuccess(i18n.t('collectionSync.disconnectSuccess'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.disconnectFailed')))
    },
  })
}

export function useCollectionSyncConnector(collectionId: number | undefined) {
  const { user } = useAuth()

  return useQuery({
    queryKey: ['document-sync', 'connector', collectionId, user?.tenantId],
    queryFn: () => getCollectionSyncConnector(collectionId!),
    enabled: !!user && collectionId != null,
  })
}

export function useCreateSyncConnector(collectionId: number) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (payload: CreateSyncConnectorRequest) =>
      createCollectionSyncConnector(collectionId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['document-sync', 'connector', collectionId, user?.tenantId],
      })
      showSuccess(i18n.t('collectionSync.bindSuccess'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.bindFailed')))
    },
  })
}

export function useDeleteSyncConnector(collectionId: number) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: () => deleteCollectionSyncConnector(collectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['document-sync', 'connector', collectionId, user?.tenantId],
      })
      showSuccess(i18n.t('collectionSync.disconnectConnectorSuccess'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.disconnectConnectorFailed')))
    },
  })
}

export function useTriggerSyncConnector(collectionId: number) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (connectorId: number) => triggerConnectorSync(connectorId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({
        queryKey: ['document-sync', 'connector', collectionId, user?.tenantId],
      })
      queryClient.invalidateQueries({ queryKey: ['documents', user?.tenantId] })
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
      showSuccess(
        i18n.t('collectionSync.syncSuccess', {
          added: result.added,
          updated: result.updated,
          deleted: result.deleted,
        })
      )
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.syncFailed')))
    },
  })
}
