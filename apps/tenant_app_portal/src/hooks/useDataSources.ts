/**
 * useDataSources Hook
 * React hook for managing data sources and assets
 */

import {
  batchDeleteAssets,
  createDataSource,
  deleteDataSource,
  getAsset,
  getDataSource,
  listAssets,
  listDataSources,
  queryAsset,
  updateDataSource,
  uploadCsv,
  type AssetMetadata,
  type BatchDeleteResponse,
  type DataSource,
  type DataSourceCreate,
  type DataSourceUpdate,
  type QueryResult,
} from '@/lib/dataSourceApi'
import { invalidateAgentAttachmentPickerQueries } from '@/lib/agentAttachmentPicker'
import type { DashboardConfig } from '@/lib/dashboardApi'
import { useAuth } from '@/hooks/useAuth'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

/** Backend max page size for GET /data-sources */
export const DATA_SOURCE_LIST_MAX_PAGE_SIZE = 100

export function dataSourceSelectOptionsQueryKey(
  tenantId: number | undefined,
  ensureIds: number[]
): readonly ['data-sources', 'select-options', number | undefined, string] {
  const ensureKey = [...new Set(ensureIds)].sort((a, b) => a - b).join(',')
  return ['data-sources', 'select-options', tenantId, ensureKey] as const
}

export function collectDataSourceIdsFromDashboard(
  config: DashboardConfig | null | undefined
): number[] {
  const ids = new Set<number>()
  for (const widget of config?.widgets ?? []) {
    if (widget.dataSourceId != null) {
      ids.add(widget.dataSourceId)
    }
  }
  for (const filter of config?.filters ?? []) {
    if (filter.dataSourceId != null) {
      ids.add(filter.dataSourceId)
    }
  }
  return [...ids]
}

/** Paginated list (first page, max size) plus any referenced IDs not on that page. */
export function useDataSourceSelectOptions(ensureIds: number[] = []) {
  const { user } = useAuth()

  return useQuery({
    queryKey: dataSourceSelectOptionsQueryKey(user?.tenantId, ensureIds),
    queryFn: async (): Promise<DataSource[]> => {
      const response = await listDataSources(1, DATA_SOURCE_LIST_MAX_PAGE_SIZE)
      const byId = new Map(response.items.map((ds) => [ds.id, ds]))
      for (const id of ensureIds) {
        if (byId.has(id)) {
          continue
        }
        try {
          byId.set(id, await getDataSource(id))
        } catch {
          // Missing or denied — omit from dropdown
        }
      }
      return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name))
    },
    enabled: !!user,
  })
}

function invalidateDataSourceQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  tenantId: number | undefined
): void {
  void queryClient.invalidateQueries({ queryKey: ['data-sources'] })
  invalidateAgentAttachmentPickerQueries(queryClient, tenantId)
}


export function useDataSources() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [dataSources, setDataSources] = useState<DataSource[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

  const fetchDataSources = useCallback(async (pageNum: number = 1, pageSizeNum: number = 10, query?: string) => {
    setLoading(true)
    setError(null)
    try {
      const response = await listDataSources(pageNum, pageSizeNum, query)
      setDataSources(response.items)
      setTotal(response.total)
      setPage(response.page)
      setPageSize(response.page_size)
      setTotalPages(response.total_pages)
      return response
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to fetch data sources'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchDataSource = useCallback(async (id: number) => {
    setLoading(true)
    setError(null)
    try {
      const dataSource = await getDataSource(id)
      return dataSource
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to fetch data source'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const addDataSource = useCallback(async (data: DataSourceCreate) => {
    setLoading(true)
    setError(null)
    try {
      const newDataSource = await createDataSource(data)
      setDataSources((prev) => [...prev, newDataSource])
      invalidateDataSourceQueries(queryClient, user?.tenantId)
      return newDataSource
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to create data source'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [queryClient, user?.tenantId])

  const modifyDataSource = useCallback(async (id: number, data: DataSourceUpdate) => {
    setLoading(true)
    setError(null)
    try {
      const updated = await updateDataSource(id, data)
      setDataSources((prev) => prev.map((ds) => (ds.id === id ? updated : ds)))
      invalidateDataSourceQueries(queryClient, user?.tenantId)
      return updated
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to update data source'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [queryClient, user?.tenantId])

  const removeDataSource = useCallback(async (id: number) => {
    setLoading(true)
    setError(null)
    try {
      await deleteDataSource(id)
      setDataSources((prev) => prev.filter((ds) => ds.id !== id))
      invalidateDataSourceQueries(queryClient, user?.tenantId)
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to delete data source'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [queryClient, user?.tenantId])

  return {
    dataSources,
    loading,
    error,
    page,
    pageSize,
    total,
    totalPages,
    fetchDataSources,
    fetchDataSource,
    addDataSource,
    modifyDataSource,
    removeDataSource,
  }
}

export function useAssets(dataSourceId: number) {
  const [assets, setAssets] = useState<AssetMetadata[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

  const fetchAssets = useCallback(
    async (pageNum: number = 1, pageSizeNum: number = 10, query?: string) => {
      setLoading(true)
      setError(null)
      try {
        const response = await listAssets(dataSourceId, pageNum, pageSizeNum, query)
        setAssets(response.items)
        setTotal(response.total)
        setPage(response.page)
        setPageSize(response.page_size)
        setTotalPages(response.total_pages)
        return response
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to fetch assets'
        setError(errorMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [dataSourceId]
  )

  const fetchAsset = useCallback(
    async (assetName: string) => {
      setLoading(true)
      setError(null)
      try {
        const asset = await getAsset(dataSourceId, assetName)
        return asset
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to fetch asset'
        setError(errorMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [dataSourceId]
  )

  const uploadCsvFile = useCallback(
    async (file: File, tableName: string) => {
      setLoading(true)
      setError(null)
      try {
        const newAsset = await uploadCsv(dataSourceId, file, tableName)
        setAssets((prev) => [...prev, newAsset])
        return newAsset
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to upload CSV'
        setError(errorMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [dataSourceId]
  )

  const executeQuery = useCallback(
    async (assetName: string, query: string, limit?: number): Promise<QueryResult> => {
      setLoading(true)
      setError(null)
      try {
        const result = await queryAsset(dataSourceId, assetName, query, limit)
        return result
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to execute query'
        setError(errorMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [dataSourceId]
  )

  const removeAssets = useCallback(
    async (assetNames: string[]): Promise<BatchDeleteResponse> => {
      setLoading(true)
      setError(null)
      try {
        const result = await batchDeleteAssets(dataSourceId, assetNames)

        // Update local state to remove successfully deleted assets
        const deletedAssets = assetNames.filter((name) => !result.failed_assets.includes(name))
        setAssets((prev) => prev.filter((asset) => !deletedAssets.includes(asset.asset_name)))

        return result
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to batch delete assets'
        setError(errorMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [dataSourceId]
  )

  return {
    assets,
    loading,
    error,
    page,
    pageSize,
    total,
    totalPages,
    fetchAssets,
    fetchAsset,
    uploadCsvFile,
    executeQuery,
    removeAssets,
  }
}
