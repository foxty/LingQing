import api from './api'

/** Browser URL for a Google Drive file (native Google files and binary uploads). */
export function driveFileViewUrl(externalFileId: string): string {
  return `https://drive.google.com/file/d/${externalFileId}/view`
}

export interface DriveAuthorizeResponse {
  authorize_url: string
}

export interface DrivePickerConfig {
  client_id: string
  access_token: string
  app_id: string
}

export interface DocumentSourceConnection {
  id: number
  provider_id: number
  provider: string
  account_email: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface SyncConnector {
  id: number
  source_connection_id: number
  collection_id: number
  source_folder_id: string
  source_folder_name: string
  include_subfolders: boolean
  status: string
  last_synced_at: string | null
  last_sync_error: string | null
  connection_owner_id: number
  connection_owner_username: string | null
  account_email: string | null
  created_at: string
  updated_at: string
}

export interface CreateSyncConnectorRequest {
  source_connection_id: number
  source_folder_id: string
  source_folder_name: string
  include_subfolders?: boolean
}

export interface SyncConnectorResult {
  connector_id: number
  added: number
  updated: number
  deleted: number
  skipped: number
}

export async function getGoogleDriveAuthorizeUrl(): Promise<DriveAuthorizeResponse> {
  const response = await api.get<DriveAuthorizeResponse>('/document-sync/google/authorize')
  return response.data
}

export async function listSourceConnections(): Promise<DocumentSourceConnection[]> {
  const response = await api.get<DocumentSourceConnection[]>('/document-sync/connections')
  return response.data
}

export async function getDrivePickerConfig(connectionId: number): Promise<DrivePickerConfig> {
  const response = await api.get<DrivePickerConfig>(
    `/document-sync/connections/${connectionId}/picker-config`
  )
  return response.data
}

export async function disconnectSourceConnection(connectionId: number): Promise<void> {
  await api.delete(`/document-sync/connections/${connectionId}`)
}

export async function getCollectionSyncConnector(
  collectionId: number
): Promise<SyncConnector | null> {
  const response = await api.get<SyncConnector | null>(
    `/document-collections/${collectionId}/sync-connector`
  )
  return response.data
}

export async function createCollectionSyncConnector(
  collectionId: number,
  payload: CreateSyncConnectorRequest
): Promise<SyncConnector> {
  const response = await api.post<SyncConnector>(
    `/document-collections/${collectionId}/sync-connector`,
    payload
  )
  return response.data
}

export async function deleteCollectionSyncConnector(collectionId: number): Promise<void> {
  await api.delete(`/document-collections/${collectionId}/sync-connector`)
}

export async function triggerConnectorSync(connectorId: number): Promise<SyncConnectorResult> {
  const response = await api.post<SyncConnectorResult>(
    `/document-sync/connectors/${connectorId}/sync`
  )
  return response.data
}
