import { API_ENDPOINTS } from '@/constants/api'
import api from '@/lib/api'
import type { PaginatedResponse } from '@/lib/documentsApi'

export type ApiConnectorAuthType = 'none' | 'api_key' | 'bearer' | 'basic' | 'custom'
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
  auth_config_masked: Record<string, any>
  rate_policy: Record<string, any>
  schema_source_type: ApiConnectorSchemaSourceType
  schema_source_url: string | null
  schema_metadata: Record<string, any>
  schema_last_synced_at: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface ApiConnectorCreateRequest {
  name: string
  description?: string
  base_url: string
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
  auth_type?: ApiConnectorAuthType
  auth_config?: Record<string, any>
  rate_policy?: Record<string, any>
  schema_source_type?: ApiConnectorSchemaSourceType
  schema_source_url?: string | null
  status?: string
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

export async function listApiConnectors(): Promise<ApiConnector[]> {
  const response = await api.get<ApiConnector[]>(API_ENDPOINTS.apiConnectors)
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
