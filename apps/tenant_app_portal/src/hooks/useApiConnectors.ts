import { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/hooks/useAuth'
import { invalidateAgentAttachmentPickerQueries } from '@/lib/agentAttachmentPicker'
import {
  callApiOperation,
  createApiConnector,
  createApiConnectorOperation,
  deleteApiConnectorOperation,
  deleteApiConnector,
  getApiConnectorOperationStats,
  listApiConnectorOperations,
  listApiConnectors,
  syncApiConnectorSchema,
  updateApiConnectorOperation,
  updateApiConnectorOperationStatus,
  updateApiConnector,
  type ApiConnector,
  type ApiConnectorCreateRequest,
  type ApiConnectorUpdateRequest,
  type ApiOperation,
  type ApiOperationCallResponse,
  type ApiOperationCreateRequest,
  type ApiOperationStats,
  type ApiOperationUpdateRequest,
} from '@/lib/apiConnectorApi'

const getErrorMessage = (err: any, fallback: string) =>
  err.response?.data?.message || err.response?.data?.detail || fallback

/**
 * List/load failures set `error` for page Alert.
 * Mutations only throw — callers toast (DESIGN §5: one channel per event).
 */
export function useApiConnectors() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [connectors, setConnectors] = useState<ApiConnector[]>([])
  const [operations, setOperations] = useState<ApiOperation[]>([])
  const [operationsTotal, setOperationsTotal] = useState(0)
  const [operationStats, setOperationStats] = useState<ApiOperationStats>({
    path_count: 0,
    total: 0,
    active: 0,
    disabled: 0,
    stale: 0,
    manual: 0,
    imported: 0,
  })
  const [operationsPage, setOperationsPage] = useState(1)
  const [operationsPageSize, setOperationsPageSize] = useState(10)
  const [operationsTotalPages, setOperationsTotalPages] = useState(0)
  const [connectorsPage, setConnectorsPage] = useState(1)
  const [connectorsPageSize, setConnectorsPageSize] = useState(10)
  const [connectorsTotal, setConnectorsTotal] = useState(0)
  const [connectorsTotalPages, setConnectorsTotalPages] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchConnectors = useCallback(
    async (pageNum: number = 1, pageSizeNum: number = 10, query?: string) => {
      setLoading(true)
      setError(null)
      try {
        const result = await listApiConnectors(pageNum, pageSizeNum, query)
        setConnectors(result.items)
        setConnectorsTotal(result.total)
        setConnectorsPage(result.page)
        setConnectorsPageSize(result.page_size)
        setConnectorsTotalPages(result.total_pages)
        return result
      } catch (err: any) {
        setError(getErrorMessage(err, 'Failed to fetch API connectors'))
        throw err
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const addConnector = useCallback(
    async (payload: ApiConnectorCreateRequest) => {
      setLoading(true)
      try {
        const created = await createApiConnector(payload)
        setConnectors((prev) => [created, ...prev])
        invalidateAgentAttachmentPickerQueries(queryClient, user?.tenantId)
        return created
      } finally {
        setLoading(false)
      }
    },
    [queryClient, user?.tenantId]
  )

  const removeConnector = useCallback(
    async (connectorId: number) => {
      setLoading(true)
      try {
        await deleteApiConnector(connectorId)
        setConnectors((prev) => prev.filter((item) => item.id !== connectorId))
        setOperations((prev) => prev.filter((item) => item.connector_id !== connectorId))
        invalidateAgentAttachmentPickerQueries(queryClient, user?.tenantId)
      } finally {
        setLoading(false)
      }
    },
    [queryClient, user?.tenantId]
  )

  const modifyConnector = useCallback(
    async (connectorId: number, payload: ApiConnectorUpdateRequest) => {
      setLoading(true)
      try {
        const updated = await updateApiConnector(connectorId, payload)
        setConnectors((prev) => prev.map((item) => (item.id === connectorId ? updated : item)))
        invalidateAgentAttachmentPickerQueries(queryClient, user?.tenantId)
        return updated
      } finally {
        setLoading(false)
      }
    },
    [queryClient, user?.tenantId]
  )

  const syncSchema = useCallback(async (connectorId: number, fileContent?: string) => {
    setLoading(true)
    try {
      return await syncApiConnectorSchema(connectorId, fileContent)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchOperations = useCallback(
    async (
      connectorId: number,
      options?: {
        page?: number
        pageSize?: number
        query?: string
        status?: 'active' | 'disabled' | 'stale'
      }
    ) => {
      setLoading(true)
      setError(null)
      try {
        const page = options?.page ?? 1
        const pageSize = options?.pageSize ?? 10
        const query = options?.query
        const status = options?.status

        const result = await listApiConnectorOperations(connectorId, page, pageSize, query, status)
        setOperations(result.items)
        setOperationsTotal(result.total)
        setOperationsPage(result.page)
        setOperationsPageSize(result.page_size)
        setOperationsTotalPages(result.total_pages)
        return result
      } catch (err: any) {
        setError(getErrorMessage(err, 'Failed to fetch operations'))
        throw err
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const fetchOperationStats = useCallback(async (connectorId: number) => {
    setLoading(true)
    setError(null)
    try {
      const stats = await getApiConnectorOperationStats(connectorId)
      setOperationStats(stats)
      return stats
    } catch (err: any) {
      setError(getErrorMessage(err, 'Failed to fetch operation stats'))
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const addOperation = useCallback(async (connectorId: number, payload: ApiOperationCreateRequest) => {
    setLoading(true)
    try {
      const created = await createApiConnectorOperation(connectorId, payload)
      setOperations((prev) => [created, ...prev])
      return created
    } finally {
      setLoading(false)
    }
  }, [])

  const modifyOperation = useCallback(async (operationId: number, payload: ApiOperationUpdateRequest) => {
    setLoading(true)
    try {
      const updated = await updateApiConnectorOperation(operationId, payload)
      setOperations((prev) => prev.map((item) => (item.id === operationId ? updated : item)))
      return updated
    } finally {
      setLoading(false)
    }
  }, [])

  const setOperationStatus = useCallback(async (operationId: number, status: 'active' | 'disabled') => {
    setLoading(true)
    try {
      const updated = await updateApiConnectorOperationStatus(operationId, status)
      setOperations((prev) => prev.map((item) => (item.id === operationId ? updated : item)))
      return updated
    } finally {
      setLoading(false)
    }
  }, [])

  const removeOperation = useCallback(async (operationId: number) => {
    setLoading(true)
    try {
      await deleteApiConnectorOperation(operationId)
      setOperations((prev) => prev.filter((item) => item.id !== operationId))
    } finally {
      setLoading(false)
    }
  }, [])

  const executeOperation = useCallback(
    async (
      operationUid: string,
      parameters: Record<string, any>
    ): Promise<ApiOperationCallResponse> => {
      setLoading(true)
      try {
        return await callApiOperation(operationUid, parameters)
      } finally {
        setLoading(false)
      }
    },
    []
  )

  return {
    connectors,
    connectorsPage,
    connectorsPageSize,
    connectorsTotal,
    connectorsTotalPages,
    operations,
    operationsTotal,
    operationStats,
    operationsPage,
    operationsPageSize,
    operationsTotalPages,
    loading,
    error,
    fetchConnectors,
    addConnector,
    modifyConnector,
    removeConnector,
    syncSchema,
    fetchOperations,
    fetchOperationStats,
    addOperation,
    modifyOperation,
    setOperationStatus,
    removeOperation,
    executeOperation,
  }
}
