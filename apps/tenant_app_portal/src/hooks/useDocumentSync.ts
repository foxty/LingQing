import '@/components/knowledge-base/collectionSyncI18n'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCollectionSyncConnector,
  disconnectCollectionSyncFolder,
  pauseCollectionSyncConnector,
  resumeCollectionSyncConnector,
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
import { invalidateAgentAttachmentPickerQueries } from '@/lib/agentAttachmentPicker'
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
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
      showSuccess(i18n.t('collectionSync.bindSuccess'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.bindFailed')))
    },
  })
}

export function usePauseSyncConnector(collectionId: number) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: () => pauseCollectionSyncConnector(collectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['document-sync', 'connector', collectionId, user?.tenantId],
      })
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
      showSuccess(i18n.t('collectionSync.pauseSuccess'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.pauseFailed')))
    },
  })
}

export function useResumeSyncConnector(collectionId: number) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: () => resumeCollectionSyncConnector(collectionId),
    onSuccess: (connector) => {
      queryClient.invalidateQueries({
        queryKey: ['document-sync', 'connector', collectionId, user?.tenantId],
      })
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
      queryClient.invalidateQueries({ queryKey: ['documents', user?.tenantId] })
      invalidateAgentAttachmentPickerQueries(queryClient, user?.tenantId)
      if (connector.last_sync_error) {
        showError(connector.last_sync_error)
      } else {
        showSuccess(i18n.t('collectionSync.resumeSuccess'))
      }
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.resumeFailed')))
    },
  })
}

export function useDisconnectCollectionSyncFolder(collectionId: number) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: () => disconnectCollectionSyncFolder(collectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['document-sync', 'connector', collectionId, user?.tenantId],
      })
      queryClient.invalidateQueries({ queryKey: ['document-collections', user?.tenantId] })
      showSuccess(i18n.t('collectionSync.disconnectFolderSuccess'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.disconnectFolderFailed')))
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
      invalidateAgentAttachmentPickerQueries(queryClient, user?.tenantId)
      const changed = result.added + result.updated + result.deleted
      if (changed === 0) {
        const unchanged = result.skipped_unchanged ?? result.skipped
        showSuccess(i18n.t('collectionSync.syncUpToDate', { skipped: unchanged }))
      } else {
        showSuccess(
          i18n.t('collectionSync.syncSuccess', {
            added: result.added,
            updated: result.updated,
            deleted: result.deleted,
          })
        )
      }
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('collectionSync.syncFailed')))
    },
  })
}
