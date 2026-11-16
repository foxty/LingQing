import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { openFileSourcePicker } from '@/components/knowledge-base/file-source-picker/FileSourcePickerFacade'
import {
  useCreateSyncConnector,
  useDisconnectCollectionSyncFolder,
  usePauseSyncConnector,
  useResumeSyncConnector,
  useDisconnectSourceConnection,
  useGoogleDriveAuthorize,
  useTriggerSyncConnector,
} from '@/hooks/useDocumentSync'
import { useNotification } from '@/hooks/useNotification'
import { getApiErrorMessage } from '@/lib/api'
import type { DocumentSourceConnection, SyncConnector } from '@/lib/documentSyncApi'

export function useDriveSyncActions(
  collectionId: number,
  options: {
    documentCount?: number
    connector: SyncConnector | undefined
    activeConnection: DocumentSourceConnection | undefined
  }
) {
  const { t } = useTranslation()
  const { showError } = useNotification()
  const { documentCount = 0, connector, activeConnection } = options

  const authorizeMutation = useGoogleDriveAuthorize()
  const createConnectorMutation = useCreateSyncConnector(collectionId)
  const pauseConnectorMutation = usePauseSyncConnector(collectionId)
  const disconnectFolderMutation = useDisconnectCollectionSyncFolder(collectionId)
  const resumeConnectorMutation = useResumeSyncConnector(collectionId)
  const disconnectAccountMutation = useDisconnectSourceConnection()
  const syncMutation = useTriggerSyncConnector(collectionId)

  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [disconnectAccountOpen, setDisconnectAccountOpen] = useState(false)
  const [bindFolderOpen, setBindFolderOpen] = useState(false)
  const [pickingFolder, setPickingFolder] = useState(false)

  const actionsBusy =
    authorizeMutation.isPending ||
    createConnectorMutation.isPending ||
    pauseConnectorMutation.isPending ||
    disconnectFolderMutation.isPending ||
    resumeConnectorMutation.isPending ||
    disconnectAccountMutation.isPending ||
    syncMutation.isPending ||
    pickingFolder

  const connect = async () => {
    try {
      const { authorize_url } = await authorizeMutation.mutateAsync()
      window.location.href = authorize_url
    } catch {
      // mutation toast
    }
  }

  const bindFolder = async () => {
    if (!activeConnection) return
    setBindFolderOpen(false)
    setPickingFolder(true)
    try {
      const picked = await openFileSourcePicker('google_drive', activeConnection.id)
      if (!picked) return
      await createConnectorMutation.mutateAsync({
        source_connection_id: activeConnection.id,
        source_folder_id: picked.folderId,
        source_folder_name: picked.folderName,
        include_subfolders: true,
      })
    } catch (error: unknown) {
      showError(getApiErrorMessage(error, t('collectionSync.pickerFailed')))
    } finally {
      setPickingFolder(false)
    }
  }

  const bindFolderClick = () => {
    if (documentCount > 0) {
      setBindFolderOpen(true)
      return
    }
    void bindFolder()
  }

  const syncNow = () => {
    if (!connector) return
    syncMutation.mutate(connector.id)
  }

  const disconnectFolder = async () => {
    await disconnectFolderMutation.mutateAsync()
    setDisconnectOpen(false)
  }

  const disconnectAccount = async () => {
    if (!activeConnection) return
    await disconnectAccountMutation.mutateAsync(activeConnection.id)
    setDisconnectAccountOpen(false)
  }

  return {
    connect,
    bindFolder,
    bindFolderClick,
    syncNow,
    resume: () => resumeConnectorMutation.mutate(),
    pauseFolderSync: () => pauseConnectorMutation.mutate(),
    disconnectFolder,
    disconnectAccount,
    authorizePending: authorizeMutation.isPending,
    syncPending: syncMutation.isPending,
    resumePending: resumeConnectorMutation.isPending,
    pausePending: pauseConnectorMutation.isPending,
    disconnectFolderPending: disconnectFolderMutation.isPending,
    disconnectAccountPending: disconnectAccountMutation.isPending,
    createConnectorPending: createConnectorMutation.isPending,
    pickingFolder,
    actionsBusy,
    disconnectOpen,
    setDisconnectOpen,
    disconnectAccountOpen,
    setDisconnectAccountOpen,
    bindFolderOpen,
    setBindFolderOpen,
  }
}