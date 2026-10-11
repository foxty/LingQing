/**
 * Data Source API Service
 * Handles all data source and asset-related API calls
 */

import api from './api'
import { API_ENDPOINTS } from '@/constants/api'

export interface DataSource {
  id: number
  tenant_id: number
  name: string
  type: 'postgres' | 'mysql' | 'databricks' | 'snowflake' | 'bigquery' | 'other'
  managed: boolean
  config: Record<string, any>
  description?: string
  owner_name?: string | null
  created_at: string
  updated_at: string
  asset_count: number
}

export interface DataSourceCreate {
  name: string
  type: 'postgres' | 'mysql' | 'databricks' | 'snowflake' | 'bigquery' | 'other'
  managed: boolean
  config?: Record<string, any>
  description?: string
}

export interface DataSourceUpdate {
  name?: string
  config?: Record<string, any>
  description?: string
}

export interface AssetMetadata {
  id: number
  data_source_id: number
  asset_name: string
  asset_type: 'table' | 'view' | 'materialized_view' | 'api_endpoint'
  columns: ColumnInfo[]
  row_count?: number
  source_info: Record<string, any>
  meta?: AssetMeta
  meta_override?: AssetMeta
  owner_name?: string | null
  created_at: string
  updated_at: string
  last_metadata_synced_at?: string | null
  last_metadata_sync_error?: string | null
  last_vector_synced_at?: string | null
  last_vector_sync_error?: string | null
}

export interface AssetMeta {
  description?: string | null
  column_description?: Record<string, string | null>
}

export interface ColumnInfo {
  name: string
  data_type: string
  nullable?: boolean
  description?: string
}

export function resolveAssetDescription(asset: AssetMetadata): string | undefined {
  return asset.meta_override?.description ?? asset.meta?.description ?? undefined
}

export interface DataSourceListResponse {
  items: DataSource[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface AssetListResponse {
  items: AssetMetadata[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface QueryResult {
  data: Record<string, any>[]
  columns: string[]
  row_count: number
  asset_name: string
}

export interface BatchDeleteResponse {
  deleted_count: number
  failed_assets: string[]
  errors: Record<string, string>
}

export interface TestConnectionRequest {
  type: 'postgres' | 'mysql' | 'databricks'
  config: Record<string, any>
}

export interface TestConnectionResponse {
  success: boolean
  message: string
  error?: string
  details?: Record<string, any>
}

export interface DiscoveredAsset {
  name: string
  type: 'table' | 'view' | 'materialized_view'
  description?: string
  row_count?: number
  columns?: Array<{
    name: string
    data_type: string
  }>
}

export interface DiscoverAssetsRequest {
  dataSourceId: number
  query?: string
  light?: boolean
}

export interface DiscoverAssetsResponse {
  assets: DiscoveredAsset[]
  total: number
  requires_query?: boolean
}

/**
 * List all data sources for current tenant
 */
export async function listDataSources(
  page: number = 1,
  pageSize: number = 10,
  query?: string
): Promise<DataSourceListResponse> {
  const params = { page, page_size: pageSize, ...(query ? { query } : {}) }
  const response = await api.get<DataSourceListResponse>(API_ENDPOINTS.dataSources, { params })
  return response.data
}

/**
 * Get a specific data source by ID
 */
export async function getDataSource(id: number): Promise<DataSource> {
  const response = await api.get<DataSource>(API_ENDPOINTS.dataSourceById(id))
  return response.data
}

/**
 * Create a new data source (without assets)
 */
export async function createDataSource(data: DataSourceCreate): Promise<DataSource> {
  const formData = new FormData()
  formData.append('name', data.name)
  formData.append('type', data.type)
  formData.append('config', JSON.stringify(data.config || {}))

  if (data.description) {
    formData.append('description', data.description)
  }

  const response = await api.post<DataSource>(API_ENDPOINTS.dataSources, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

/**
 * Update an existing data source configuration
 */
export async function updateDataSource(id: number, data: DataSourceUpdate): Promise<DataSource> {
  const formData = new FormData()

  if (data.name) {
    formData.append('name', data.name)
  }

  if (data.description !== undefined) {
    formData.append('description', data.description || '')
  }

  if (data.config) {
    formData.append('config', JSON.stringify(data.config))
  }

  const response = await api.put<DataSource>(API_ENDPOINTS.dataSourceById(id), formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

/**
 * Delete a data source
 */
export async function deleteDataSource(id: number): Promise<void> {
  await api.delete(API_ENDPOINTS.dataSourceById(id))
}

/**
 * Test connection to a data source without saving (PostgreSQL/MySQL only)
 */
export async function testConnection(
  request: TestConnectionRequest
): Promise<TestConnectionResponse> {
  const formData = new FormData()
  formData.append('type', request.type)
  formData.append('config', JSON.stringify(request.config))

  const response = await api.post<TestConnectionResponse>(API_ENDPOINTS.testConnection, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

/**
 * Discover available assets from a saved data source
 */
export async function discoverAssets(
  request: DiscoverAssetsRequest
): Promise<DiscoverAssetsResponse> {
  const params = {
    ...(request.query ? { query: request.query } : {}),
    ...(request.light ? { light: request.light } : {}),
  }
  const response = await api.get<DiscoverAssetsResponse>(
    API_ENDPOINTS.discoverAssets(request.dataSourceId),
    { params }
  )
  return response.data
}

/**
 * Update asset selection for a data source
 */
export async function updateAssetSelection(
  dataSourceId: number,
  assetNames: string[]
): Promise<void> {
  const params = new URLSearchParams()
  assetNames.forEach((name) => params.append('asset_names', name))

  await api.put(`${API_ENDPOINTS.updateAssetSelection(dataSourceId)}?${params.toString()}`)
}

/**
 * List assets for a data source with pagination
 */
export async function listAssets(
  dataSourceId: number,
  page: number = 1,
  pageSize: number = 10,
  query?: string
): Promise<AssetListResponse> {
  const params = { page, page_size: pageSize, ...(query ? { query } : {}) }
  const response = await api.get<AssetListResponse>(API_ENDPOINTS.dataSourceAssets(dataSourceId), {
    params,
  })
  return response.data
}

/**
 * Get asset schema
 */
export async function getAsset(dataSourceId: number, assetName: string): Promise<AssetMetadata> {
  const response = await api.get<AssetMetadata>(API_ENDPOINTS.assetByName(dataSourceId, assetName))
  return response.data
}

/**
 * Upload CSV file to create a new asset
 */
export async function uploadCsv(
  dataSourceId: number,
  file: File,
  tableName: string
): Promise<AssetMetadata> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('asset_name', tableName)

  const response = await api.post<AssetMetadata>(API_ENDPOINTS.uploadCsv(dataSourceId), formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

/**
 * Sync asset metadata from external data source
 */
export async function syncAssetMetadata(
  dataSourceId: number,
  assetId: number,
  force: boolean = false
): Promise<{
  status: string
  asset_id: number
  updated: boolean
  stats?: Record<string, any>
  error?: string
  task_run_id?: number
}> {
  const response = await api.post(
    `/data-sources/${dataSourceId}/assets/${assetId}/sync?force=${force}`
  )
  return response.data
}

/**
 * Update asset metadata overrides
 */
export async function updateAssetMetaOverride(
  dataSourceId: number,
  assetId: number,
  payload: AssetMeta
): Promise<AssetMetadata> {
  const response = await api.put<AssetMetadata>(
    `/data-sources/${dataSourceId}/assets/${assetId}/meta-override`,
    payload
  )
  return response.data
}

/**
 * Query an asset with SQL
 */
export async function queryAsset(
  dataSourceId: number,
  assetName: string,
  query: string,
  limit?: number
): Promise<QueryResult> {
  const response = await api.post<QueryResult>(API_ENDPOINTS.queryAsset(dataSourceId, assetName), {
    query,
    limit,
  })
  return response.data
}

/**
 * Delete one or multiple assets
 */
export async function deleteAssets(
  dataSourceId: number,
  assetNames: string[]
): Promise<BatchDeleteResponse> {
  // Batch asset deletion - use query parameters
  const params = new URLSearchParams()
  assetNames.forEach((name) => params.append('asset_names', name))
  const response = await api.delete<BatchDeleteResponse>(
    `${API_ENDPOINTS.dataSourceAssets(dataSourceId)}?${params.toString()}`
  )
  return response.data
}

/**
 * Delete a single asset (convenience wrapper)
 */
export async function deleteAsset(dataSourceId: number, assetName: string): Promise<void> {
  await deleteAssets(dataSourceId, [assetName])
}

/**
 * Batch delete multiple assets (convenience wrapper)
 */
export async function batchDeleteAssets(
  dataSourceId: number,
  assetNames: string[]
): Promise<BatchDeleteResponse> {
  const result = await deleteAssets(dataSourceId, assetNames)
  return result as BatchDeleteResponse
}
