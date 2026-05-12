import { useCallback, useState } from 'react'

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

export function useApiConnectors() {
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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchConnectors = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await listApiConnectors()
      setConnectors(rows)
      return rows
    } catch (err: any) {
      const message = getErrorMessage(err, 'Failed to fetch API connectors')
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const addConnector = useCallback(async (payload: ApiConnectorCreateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const created = await createApiConnector(payload)
      setConnectors((prev) => [created, ...prev])
      return created
    } catch (err: any) {
      const message = getErrorMessage(err, 'Failed to create API connector')
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const removeConnector = useCallback(async (connectorId: number) => {
    setLoading(true)
    setError(null)
    try {
      await deleteApiConnector(connectorId)
      setConnectors((prev) => prev.filter((item) => item.id !== connectorId))
      setOperations((prev) => prev.filter((item) => item.connector_id !== connectorId))
    } catch (err: any) {
      const message = getErrorMessage(err, 'Failed to delete API connector')
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const modifyConnector = useCallback(
    async (connectorId: number, payload: ApiConnectorUpdateRequest) => {
      setLoading(true)
      setError(null)
      try {
        const updated = await updateApiConnector(connectorId, payload)
        setConnectors((prev) => prev.map((item) => (item.id === connectorId ? updated : item)))
        return updated
      } catch (err: any) {
        const message = getErrorMessage(err, 'Failed to update API connector')
        setError(message)
        throw err
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const syncSchema = useCallback(async (connectorId: number, fileContent?: string) => {
    setLoading(true)
    setError(null)
    try {
      return await syncApiConnectorSchema(connectorId, fileContent)
    } catch (err: any) {
      const message = getErrorMessage(err, 'Failed to sync schema')
      setError(message)
      throw err
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
        const message = getErrorMessage(err, 'Failed to fetch operations')
        setError(message)
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
      const message = getErrorMessage(err, 'Failed to fetch operation stats')
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const addOperation = useCallback(
    async (connectorId: number, payload: ApiOperationCreateRequest) => {
      setLoading(true)
      setError(null)
      try {
        const created = await createApiConnectorOperation(connectorId, payload)
        setOperations((prev) => [created, ...prev])
        return created
      } catch (err: any) {
        const message = getErrorMessage(err, 'Failed to create operation')
        setError(message)
        throw err
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const modifyOperation = useCallback(
    async (operationId: number, payload: ApiOperationUpdateRequest) => {
      setLoading(true)
      setError(null)
      try {
        const updated = await updateApiConnectorOperation(operationId, payload)
        setOperations((prev) => prev.map((item) => (item.id === operationId ? updated : item)))
        return updated
      } catch (err: any) {
        const message = getErrorMessage(err, 'Failed to update operation')
        setError(message)
        throw err
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const setOperationStatus = useCallback(
    async (operationId: number, status: 'active' | 'disabled') => {
      setLoading(true)
      setError(null)
      try {
        const updated = await updateApiConnectorOperationStatus(operationId, status)
        setOperations((prev) => prev.map((item) => (item.id === operationId ? updated : item)))
        return updated
      } catch (err: any) {
        const message = getErrorMessage(err, 'Failed to update operation status')
        setError(message)
        throw err
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const removeOperation = useCallback(async (operationId: number) => {
    setLoading(true)
    setError(null)
    try {
      await deleteApiConnectorOperation(operationId)
      setOperations((prev) => prev.filter((item) => item.id !== operationId))
    } catch (err: any) {
      const message = getErrorMessage(err, 'Failed to delete operation')
      setError(message)
      throw err
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
      setError(null)
      try {
        return await callApiOperation(operationUid, parameters)
      } catch (err: any) {
        const message = getErrorMessage(err, 'Failed to call operation')
        setError(message)
        throw err
      } finally {
        setLoading(false)
      }
    },
    []
  )

  return {
    connectors,
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
