import { API_ENDPOINTS } from '@/constants/api'
import api from '@/lib/api'
import type { PaginatedResponse } from '@/lib/documentsApi'
import type { PaginatedListResponse } from '@/lib/paginatedList'
import type {
  UserIntegrationConnection,
  UserIntegrationConnectionSummary,
  UserIntegrationConnectionUpsert,
} from '@/lib/userIntegrationConnection'

export type { UserIntegrationConnection, UserIntegrationConnectionUpsert }

export type ApiConnectorAuthType = 'none' | 'api_key' | 'bearer' | 'basic' | 'custom' | 'oauth2'
export type ApiConnectorSchemaSourceType = 'manual' | 'openapi_url' | 'openapi_upload'

export interface ApiConnector {
  id: number
  tenant_id: number
  owner_id: number | null
  owner_name?: string | null
  name: string
  description: string | null
  base_url: string
  auth_type: ApiConnectorAuthType
  auth_config: Record<string, any>
  rate_policy: Record<string, any>
  execution_rules?: Record<string, any>
  pack_ref?: string | null
  schema_source_type: ApiConnectorSchemaSourceType
  schema_source_url: string | null
  schema_metadata: Record<string, any>
  schema_last_synced_at: string | null
  status: string
  credential_mode?: 'shared' | 'user'
  user_connection_status?: 'not_connected' | 'connected' | 'expired' | null
  can_write?: boolean
  masked_fields?: string[]
  created_at: string
  updated_at: string
}

export interface ApiConnectorCreateRequest {
  name: string
  description?: string
  base_url: string
  credential_mode?: 'shared' | 'user'
  auth_type: ApiConnectorAuthType
  auth_config: Record<string, any>
  rate_policy: Record<string, any>
  schema_source_type: ApiConnectorSchemaSourceType
  schema_source_url?: string | null
}

export interface ApiConnectorUpdateRequest {
  name?: string
  description?: string
  base_url?: string
  credential_mode?: 'shared' | 'user'
  auth_type?: ApiConnectorAuthType
  auth_config?: Record<string, any>
  rate_policy?: Record<string, any>
  schema_source_type?: ApiConnectorSchemaSourceType
  schema_source_url?: string | null
  status?: string
}

export interface ApiConnectorPackSummary {
  pack_id: string
  version: string
  name: string
  description: string | null
}

export interface ApiOperation {
  id: number
  connector_id: number
  operation_uid: string
  method: string
  path_template: string
  operation_id: string | null
  summary: string
  description: string | null
  tags: string[]
  request_schema: Record<string, any> | null
  response_schema: Record<string, any> | null
  auth_requirement: string
  risk_level: string
  source: 'imported' | 'manual'
  upstream_key: string | null
  status: string
  last_vector_synced_at: string | null
  last_vector_sync_error: string | null
  last_vector_sync_failed_at: string | null
  owner_id: number | null
  created_at: string
  updated_at: string
}

export interface ApiOperationStats {
  path_count: number
  total: number
  active: number
  disabled: number
  stale: number
  manual: number
  imported: number
}

export interface ApiOperationCreateRequest {
  method: string
  path_template: string
  operation_id?: string | null
  summary?: string
  description?: string | null
  tags?: string[]
  request_schema: Record<string, any>
  response_schema: Record<string, any>
  auth_requirement?: string
  risk_level?: string
}

export interface ApiOperationUpdateRequest {
  method?: string
  path_template?: string
  operation_id?: string | null
  summary?: string
  description?: string | null
  tags?: string[]
  request_schema?: Record<string, any> | null
  response_schema?: Record<string, any> | null
  auth_requirement?: string
  risk_level?: string
}

export interface SyncSchemaResponse {
  operations_created: number
  added: number
  updated: number
  staled: number
  unchanged: number
}

export interface ApiOperationCallResponse {
  status_code: number
  body: any
  headers: Record<string, string>
  elapsed_ms: number
  error: string | null
}

export type ApiConnectorListResponse = PaginatedListResponse<ApiConnector>

export async function listApiConnectors(
  page = 1,
  pageSize = 100,
  query?: string
): Promise<ApiConnectorListResponse> {
  const params = { page, page_size: pageSize, ...(query ? { query } : {}) }
  const response = await api.get<ApiConnectorListResponse>(API_ENDPOINTS.apiConnectors, { params })
  return response.data
}

export async function createApiConnector(
  payload: ApiConnectorCreateRequest
): Promise<ApiConnector> {
  const response = await api.post<ApiConnector>(API_ENDPOINTS.apiConnectors, payload)
  return response.data
}

export async function updateApiConnector(
  connectorId: number,
  payload: ApiConnectorUpdateRequest
): Promise<ApiConnector> {
  const response = await api.patch<ApiConnector>(
    API_ENDPOINTS.apiConnectorById(connectorId),
    payload
  )
  return response.data
}

export async function deleteApiConnector(connectorId: number): Promise<void> {
  await api.delete(API_ENDPOINTS.apiConnectorById(connectorId))
}

export async function syncApiConnectorSchema(
  connectorId: number,
  fileContent?: string
): Promise<SyncSchemaResponse> {
  const response = await api.post<SyncSchemaResponse>(
    API_ENDPOINTS.apiConnectorSyncSchema(connectorId),
    {
      file_content: fileContent,
    }
  )
  return response.data
}

export async function listApiConnectorOperations(
  connectorId: number,
  page: number = 1,
  pageSize: number = 10,
  query?: string,
  status?: 'active' | 'disabled' | 'stale'
): Promise<PaginatedResponse<ApiOperation>> {
  const response = await api.get<PaginatedResponse<ApiOperation>>(
    API_ENDPOINTS.apiConnectorOperations(connectorId),
    {
      params: {
        page,
        page_size: pageSize,
        ...(query ? { query } : {}),
        ...(status ? { status } : {}),
      },
    }
  )
  return response.data
}

export async function getApiConnectorOperationStats(
  connectorId: number
): Promise<ApiOperationStats> {
  const response = await api.get<ApiOperationStats>(
    API_ENDPOINTS.apiConnectorOperationStats(connectorId)
  )
  return response.data
}

export async function createApiConnectorOperation(
  connectorId: number,
  payload: ApiOperationCreateRequest
): Promise<ApiOperation> {
  const response = await api.post<ApiOperation>(
    API_ENDPOINTS.apiConnectorOperations(connectorId),
    payload
  )
  return response.data
}

export async function updateApiConnectorOperation(
  operationId: number,
  payload: ApiOperationUpdateRequest
): Promise<ApiOperation> {
  const response = await api.patch<ApiOperation>(
    API_ENDPOINTS.apiConnectorOperationById(operationId),
    payload
  )
  return response.data
}

export async function updateApiConnectorOperationStatus(
  operationId: number,
  status: 'active' | 'disabled'
): Promise<ApiOperation> {
  const response = await api.patch<ApiOperation>(
    API_ENDPOINTS.apiConnectorOperationStatusById(operationId),
    {
      status,
    }
  )
  return response.data
}

export async function deleteApiConnectorOperation(operationId: number): Promise<void> {
  await api.delete(API_ENDPOINTS.apiConnectorOperationById(operationId))
}

export async function callApiOperation(
  operationUid: string,
  parameters: Record<string, any>
): Promise<ApiOperationCallResponse> {
  const response = await api.post<ApiOperationCallResponse>(
    API_ENDPOINTS.apiConnectorCallOperation(operationUid),
    { parameters }
  )
  return response.data
}

export async function getMyApiConnectorConnection(
  connectorId: number
): Promise<UserIntegrationConnection> {
  const response = await api.get<UserIntegrationConnection>(
    `/api-connectors/${connectorId}/connections/me`
  )
  return response.data
}

export async function listApiConnectorPacks(): Promise<ApiConnectorPackSummary[]> {
  const response = await api.get<{ items: ApiConnectorPackSummary[] }>('/integration-packs')
  return response.data.items
}

export async function installApiConnectorPack(body: {
  pack_id: string
  client_id: string
  client_secret: string
  redirect_uri?: string
}): Promise<ApiConnector> {
  const response = await api.post<ApiConnector>('/integration-packs/install', body)
  return response.data
}

export async function startMyApiConnectorOAuth(
  connectorId: number
): Promise<{ authorization_url: string }> {
  const response = await api.post<{ authorization_url: string }>(
    `/api-connectors/${connectorId}/oauth/start`
  )
  return response.data
}

export async function upsertMyApiConnectorConnection(
  connectorId: number,
  body: UserIntegrationConnectionUpsert
): Promise<UserIntegrationConnection> {
  const response = await api.put<UserIntegrationConnection>(
    `/api-connectors/${connectorId}/connections/me`,
    body
  )
  return response.data
}

export async function deleteMyApiConnectorConnection(connectorId: number): Promise<void> {
  await api.delete(`/api-connectors/${connectorId}/connections/me`)
}

export async function testMyApiConnectorConnection(
  connectorId: number,
  body?: UserIntegrationConnectionUpsert
): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>(
    `/api-connectors/${connectorId}/connections/me/test`,
    body ?? undefined
  )
  return response.data
}

export async function listApiConnectorUserConnections(
  connectorId: number
): Promise<UserIntegrationConnectionSummary[]> {
  const response = await api.get<{ items: UserIntegrationConnectionSummary[] }>(
    `/api-connectors/${connectorId}/connections`
  )
  return response.data.items
}

export async function getUserApiConnectorConnection(
  connectorId: number,
  userId: number
): Promise<UserIntegrationConnection> {
  const response = await api.get<UserIntegrationConnection>(
    `/api-connectors/${connectorId}/connections/users/${userId}`
  )
  return response.data
}

export async function upsertUserApiConnectorConnection(
  connectorId: number,
  userId: number,
  body: UserIntegrationConnectionUpsert
): Promise<UserIntegrationConnection> {
  const response = await api.put<UserIntegrationConnection>(
    `/api-connectors/${connectorId}/connections/users/${userId}`,
    body
  )
  return response.data
}

export async function deleteUserApiConnectorConnection(
  connectorId: number,
  userId: number
): Promise<void> {
  await api.delete(`/api-connectors/${connectorId}/connections/users/${userId}`)
}

export async function testUserApiConnectorConnection(
  connectorId: number,
  userId: number,
  body?: UserIntegrationConnectionUpsert
): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>(
    `/api-connectors/${connectorId}/connections/users/${userId}/test`,
    body ?? undefined
  )
  return response.data
}
