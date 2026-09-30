import api from './api'

export interface GoogleDriveSourceConfig {
  provider: string
  enabled: boolean
  client_id: string | null
  client_secret_configured: boolean
}

export interface GoogleDriveSourceConfigUpsert {
  client_id: string
  client_secret?: string
  enabled: boolean
}

export async function getGoogleDriveSource(): Promise<GoogleDriveSourceConfig> {
  const response = await api.get<GoogleDriveSourceConfig>('/document-sources/google-drive')
  return response.data
}

export async function upsertGoogleDriveSource(
  payload: GoogleDriveSourceConfigUpsert
): Promise<GoogleDriveSourceConfig> {
  const response = await api.put<GoogleDriveSourceConfig>('/document-sources/google-drive', payload)
  return response.data
}
