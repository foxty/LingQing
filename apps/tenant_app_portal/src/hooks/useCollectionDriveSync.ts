import { useCollectionSyncConnector, useSourceConnections } from '@/hooks/useDocumentSync'
import { useDriveSyncActions } from '@/hooks/useDriveSyncActions'
import { useAuth } from '@/hooks/useAuth'
import {
  formatDriveConnectionOwnerLabel,
  resolveDriveSyncUiState,
  type DriveSyncUiState,
} from '@/lib/driveSyncDisplay'
import { useTranslation } from 'react-i18next'
import { SOURCE_CONNECTION_STATUS } from '@/lib/documentSyncConstants'

interface UseCollectionDriveSyncOptions {
  collectionId: number
  documentCount?: number
  canManageCollection?: boolean
  /** When false, source connections query stays idle until user opens the popover. */
  popoverOpen?: boolean
}

export function useCollectionDriveSync({
  collectionId,
  documentCount = 0,
  canManageCollection = false,
  popoverOpen = false,
}: UseCollectionDriveSyncOptions) {
  const { t } = useTranslation()
  const { user } = useAuth()

  const { data: connector, isLoading: connectorLoading } = useCollectionSyncConnector(collectionId)
  const loadConnections = canManageCollection && (!connector || popoverOpen)
  const { data: connections = [], isLoading: connectionsLoading } = useSourceConnections(loadConnections)

  const activeConnection = connections.find((c) => c.status === SOURCE_CONNECTION_STATUS.ACTIVE)
  const actions = useDriveSyncActions(collectionId, {
    documentCount,
    connector: connector ?? undefined,
    activeConnection,
  })

  const canManageConnector = connector != null && user?.id === connector.connection_owner_id
  const connectorOwnerLabel = connector
    ? formatDriveConnectionOwnerLabel(
        t,
        connector.connection_owner_username,
        connector.account_email,
        connector.connection_owner_id
      )
    : null

  const isBusy =
    connectorLoading || (loadConnections && connectionsLoading) || actions.actionsBusy

  const triggerState: DriveSyncUiState | 'none' | 'loading' = connectorLoading
    ? 'loading'
    : connector
      ? resolveDriveSyncUiState(connector)
      : 'none'

  const showTrigger = Boolean(connector) || canManageCollection

  return {
    connector,
    connectorLoading,
    connectorOwnerLabel,
    canManageConnector,
    activeConnection,
    user,
    triggerState,
    showTrigger,
    isBusy,
    ...actions,
  }
}