import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import type { SyncConnector } from '@/lib/documentSyncApi'
import { CONNECTOR_STATUS, SOURCE_CONNECTION_STATUS } from '@/lib/documentSyncConstants'
import type { TFunction } from 'i18next'
export type DriveSyncUiState = 'active-ok' | 'active-error' | 'stopped-paused' | 'stopped-disconnected'

export type DriveSyncBadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline'

export function resolveDriveSyncUiState(connector: SyncConnector): DriveSyncUiState {
  if (connector.status === CONNECTOR_STATUS.ACTIVE) {
    return connector.last_sync_error ? 'active-error' : 'active-ok'
  }
  return connector.source_connection_status === SOURCE_CONNECTION_STATUS.REVOKED
    ? 'stopped-disconnected'
    : 'stopped-paused'
}

export type DriveSyncTriggerState = DriveSyncUiState | 'none' | 'loading'

export type DriveSyncChipSpec = { variant: DriveSyncBadgeVariant; labelKey: string }

function driveSyncChipSpec(state: DriveSyncUiState | 'none'): DriveSyncChipSpec {
  if (state === 'none') {
    return { variant: 'secondary', labelKey: 'collectionSync.notConnected' }
  }
  switch (state) {
    case 'active-ok':
      return { variant: 'default', labelKey: 'collectionSync.statusActive' }
    case 'active-error':
      return { variant: 'destructive', labelKey: 'collectionSync.syncErrorBadge' }
    case 'stopped-paused':
      return { variant: 'secondary', labelKey: 'collectionSync.statusStopped' }
    case 'stopped-disconnected':
      return { variant: 'destructive', labelKey: 'collectionSync.statusDisconnected' }
  }
}

export function driveSyncHeaderChip(
  state: DriveSyncTriggerState
): DriveSyncChipSpec | 'loading' {
  if (state === 'loading') {
    return 'loading'
  }
  return driveSyncChipSpec(state)
}

export function resolveDriveSyncUiStateFromCollection(
  collection: DocumentCollection
): DriveSyncUiState | null {
  if (!collection.has_drive_sync) {
    return null
  }
  if (collection.sync_status === CONNECTOR_STATUS.STOPPED) {
    return 'stopped-paused'
  }
  if (collection.last_sync_error) {
    return 'active-error'
  }
  return 'active-ok'
}

export function collectionListSyncBadge(collection: DocumentCollection): DriveSyncChipSpec {
  const state = resolveDriveSyncUiStateFromCollection(collection)
  return driveSyncChipSpec(state ?? 'active-ok')
}

export function collectionListSyncInfo(
  collection: DocumentCollection,
  t: TFunction,
  formatTime: (iso: string) => string
): { headingKey: string; body: string; destructive: boolean } {
  if (collection.last_sync_error) {
    return {
      headingKey: 'collectionSync.listErrorHeading',
      body: collection.last_sync_error,
      destructive: true,
    }
  }
  if (collection.sync_status === CONNECTOR_STATUS.STOPPED) {
    return {
      headingKey: 'collectionSync.listStoppedHeading',
      body: t('collectionSync.stoppedFolderSyncOff'),
      destructive: false,
    }
  }
  if (collection.last_synced_at) {
    return {
      headingKey: 'collectionSync.listActiveHeading',
      body: t('collectionSync.lastSynced', { time: formatTime(collection.last_synced_at) }),
      destructive: false,
    }
  }
  return {
    headingKey: 'collectionSync.listActiveHeading',
    body: t('collectionSync.neverSynced'),
    destructive: false,
  }
}

export function formatDriveConnectionOwnerLabel(
  t: TFunction,
  username: string | null | undefined,
  accountEmail: string | null | undefined,
  fallbackUserId?: number
): string | null {
  const user = username ?? (fallbackUserId != null ? `#${fallbackUserId}` : null)
  if (user && accountEmail) {
    return t('collectionSync.connectionOwner', { user, account: accountEmail })
  }
  if (user) return user
  if (accountEmail) return accountEmail
  return null
}