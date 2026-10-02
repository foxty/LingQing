import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import ContainerDetailHeader from '@/components/ContainerDetailHeader'
import ListDetailToolbar from '@/components/ListDetailToolbar'
import ApiOperationCallDialog from '@/components/ApiOperationCallDialog'
import ApiOperationTable from '@/components/ApiOperationTable'
import ImportOpenApiDialog from '@/components/ImportOpenApiDialog'
import ManualOperationDialog from '@/components/ManualOperationDialog'
import type { ManualOperationValues } from '@/components/ManualOperationDialog'
import OpenApiMetaPanel from '@/components/OpenApiMetaPanel'
import PageStatsActionBar from '@/components/PageStatsActionBar'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useApiConnectors } from '@/hooks/useApiConnectors'
import { useNotification } from '@/hooks/useNotification'
import type { ApiOperation, ApiOperationCallResponse } from '@/lib/apiConnectorApi'
import { Braces, Cable, Info, Plus, RefreshCw, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  apiConnectorDetail: {
    title: 'API Connector Detail',
    parentLabel: 'API Connectors',
    connectorTags: 'Connector Tags',
    back: 'Back',
    loadFailed: 'Failed to load connector',
    loadingConnector: 'Loading connector...',
    connectorNotExists: 'Connector does not exist',
    connectorNotFound: 'Connector not found',
    invalidConnectorId: 'Invalid connector ID',
    pathCount: 'Paths',
    apiTotal: 'Total APIs',
    viewApiDistribution: 'View API distribution',
    apiDistribution: 'API Distribution',
    byStatus: 'By Status',
    bySource: 'By Source',
    statusActive: 'Active',
    statusDisabled: 'Disabled',
    statusStale: 'Stale',
    sourceManual: 'Manual',
    sourceImported: 'Imported',
    share: 'Share',
    modify: 'Modify',
    addApi: 'Add API',
    searchOperations: 'Search operations...',
    importOpenApi: 'Import OpenAPI',
    syncSchema: 'Sync Schema',
    loadOperationsFailed: 'Failed to load operations',
    invalidJsonObject: 'must be a valid JSON object:',
    syncComplete: 'Sync complete. Added: {{added}}, Updated: {{updated}}, Stale: {{staled}}, Unchanged: {{unchanged}}',
    syncFailed: 'Schema sync failed',
    fillPathTemplate: 'Path template is required',
    manualOperationCreated: 'Manual operation created successfully',
    createManualOperationFailed: 'Failed to create manual operation',
    operationEnabled: 'Operation enabled',
    operationDisabled: 'Operation disabled',
    updateOperationStatusFailed: 'Failed to update operation status',
    manualOnlyEdit: 'Only manual operations can be edited',
    manualOnlyDelete: 'Only manual operations can be deleted',
    manualOperationUpdated: 'Manual operation updated',
    updateManualOperationFailed: 'Failed to update manual operation',
    manualOperationDeleted: 'Manual operation deleted',
    deleteManualOperationFailed: 'Failed to delete manual operation',
    selectOperation: 'Please select an operation',
    callParameters: 'Call Parameters',
    callFailed: 'Operation call failed',
    callSuccess: 'Operation call succeeded',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  apiConnectorDetail: {
    title: 'API连接器详情',
    parentLabel: 'API连接器',
    connectorTags: '连接器标签',
    back: '返回',
    loadFailed: '加载连接器失败',
    loadingConnector: '正在加载连接器...',
    connectorNotExists: '连接器不存在',
    connectorNotFound: '未找到连接器',
    invalidConnectorId: '无效的连接器ID',
    pathCount: '路径数',
    apiTotal: 'API总数',
    viewApiDistribution: '查看API分布',
    apiDistribution: 'API分布',
    byStatus: '按状态',
    bySource: '按来源',
    statusActive: '启用',
    statusDisabled: '停用',
    statusStale: '过期',
    sourceManual: '手动',
    sourceImported: '导入',
    share: '分享',
    modify: '修改',
    addApi: '添加API',
    searchOperations: '搜索操作...',
    importOpenApi: '导入OpenAPI',
    syncSchema: '同步模式',
    loadOperationsFailed: '加载操作失败',
    invalidJsonObject: '必须是有效的JSON对象：',
    syncComplete: '同步完成。新增：{{added}}，更新：{{updated}}，过期：{{staled}}，未变化：{{unchanged}}',
    syncFailed: '模式同步失败',
    fillPathTemplate: '路径模板不能为空',
    manualOperationCreated: '手动操作创建成功',
    createManualOperationFailed: '创建手动操作失败',
    operationEnabled: '操作已启用',
    operationDisabled: '操作已禁用',
    updateOperationStatusFailed: '更新操作状态失败',
    manualOnlyEdit: '仅可编辑手动操作',
    manualOnlyDelete: '仅可删除手动操作',
    manualOperationUpdated: '手动操作已更新',
    updateManualOperationFailed: '更新手动操作失败',
    manualOperationDeleted: '手动操作已删除',
    deleteManualOperationFailed: '删除手动操作失败',
    selectOperation: '请选择一个操作',
    callParameters: '调用参数',
    callFailed: '操作调用失败',
    callSuccess: '操作调用成功',
  }
}, true, true)

const EMPTY_JSON = '{\n  "path": {},\n  "query": {},\n  "header": {},\n  "body": null\n}'

export default function ApiConnectorDetailPage() {
  const { t } = useTranslation()
  const {
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
    syncSchema,
    fetchOperations,
    fetchOperationStats,
    addOperation,
    modifyOperation,
    setOperationStatus,
    removeOperation,
    executeOperation,
  } = useApiConnectors()
  const { showError, showSuccess } = useNotification()

  const { connectorId } = useParams<{ connectorId: string }>()
  const navigate = useNavigate()

  const [selectedOperation, setSelectedOperation] = useState<ApiOperation | null>(null)

  const [searchQuery, setSearchQuery] = useState('')
  const [appliedQuery, setAppliedQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [callParametersText, setCallParametersText] = useState(EMPTY_JSON)
  const [callResult, setCallResult] = useState<ApiOperationCallResponse | null>(null)
  const [addOperationDialogOpen, setAddOperationDialogOpen] = useState(false)
  const [editOperationDialogOpen, setEditOperationDialogOpen] = useState(false)
  const [importSchemaDialogOpen, setImportSchemaDialogOpen] = useState(false)
  const [callDialogOpen, setCallDialogOpen] = useState(false)

  const connectorIdNumber = Number(connectorId)
  const getErrorMessage = (err: any, fallback: string) =>
    err?.response?.data?.message || err?.response?.data?.detail || err?.message || fallback

  const selectedConnector = useMemo(
    () => connectors.find((item) => item.id === connectorIdNumber) || null,
    [connectors, connectorIdNumber]
  )

  useEffect(() => {
    fetchConnectors().catch((err: any) => {
      showError(getErrorMessage(err, t('apiConnectorDetail.loadFailed')))
    })
  }, [fetchConnectors, showError])

  useEffect(() => {
    if (!Number.isFinite(connectorIdNumber)) {
      return
    }
    setSearchQuery('')
    setAppliedQuery('')
    setCurrentPage(1)
  }, [connectorIdNumber])

  useEffect(() => {
    if (!Number.isFinite(connectorIdNumber)) {
      return
    }
    fetchOperations(connectorIdNumber, {
      page: currentPage,
      pageSize: operationsPageSize || 10,
      query: appliedQuery || undefined,
      status: undefined,
    })
      .then(() => fetchOperationStats(connectorIdNumber))
      .catch((err: any) => {
        showError(getErrorMessage(err, t('apiConnectorDetail.loadOperationsFailed')))
      })
  }, [
    connectorIdNumber,
    currentPage,
    operationsPageSize,
    appliedQuery,
    fetchOperations,
    fetchOperationStats,
    showError,
  ])

  const parseJsonInput = (value: string, fieldName: string): Record<string, any> => {
    try {
      const parsed = JSON.parse(value)
      if (parsed && typeof parsed === 'object') {
        return parsed
      }
      throw new Error('JSON must be an object')
    } catch (error: any) {
      throw new Error(`${fieldName} ${t('apiConnectorDetail.invalidJsonObject')} ${error.message}`)
    }
  }

  const handleSyncSchema = async (fileContent?: string) => {
    if (!selectedConnector) {
      showError(t('apiConnectorDetail.connectorNotExists'))
      return
    }
    try {
      const result = await syncSchema(selectedConnector.id, fileContent)
      await fetchOperations(selectedConnector.id, {
        page: currentPage,
        pageSize: operationsPageSize || 10,
        query: appliedQuery || undefined,
        status: undefined,
      })
      await fetchOperationStats(selectedConnector.id)
      showSuccess(
        t('apiConnectorDetail.syncComplete', { added: result.added, updated: result.updated, staled: result.staled, unchanged: result.unchanged })
      )
    } catch (err: any) {
      showError(getErrorMessage(err, t('apiConnectorDetail.syncFailed')))
      throw err
    }
  }

  const handleAddManualOperation = async (values: ManualOperationValues) => {
    if (!selectedConnector) {
      showError(t('apiConnectorDetail.connectorNotExists'))
      return
    }
    if (!values.pathTemplate.trim()) {
      showError(t('apiConnectorDetail.fillPathTemplate'))
      throw new Error(t('apiConnectorDetail.fillPathTemplate'))
    }
    const requestSchema = parseJsonInput(values.requestSchemaText, 'Request Schema')
    const responseSchema = parseJsonInput(values.responseSchemaText, 'Response Schema')
    try {
      const created = await addOperation(selectedConnector.id, {
        method: values.method,
        path_template: values.pathTemplate.trim(),
        operation_id: values.operationId.trim() || null,
        summary: values.summary.trim(),
        description: null,
        tags: [],
        request_schema: requestSchema,
        response_schema: responseSchema,
        auth_requirement: 'required',
        risk_level: 'medium',
      })
      showSuccess(t('apiConnectorDetail.manualOperationCreated'))
      setSelectedOperation(created)
      await fetchOperations(selectedConnector.id, {
        page: currentPage,
        pageSize: operationsPageSize || 10,
        query: appliedQuery || undefined,
        status: undefined,
      })
      await fetchOperationStats(selectedConnector.id)
    } catch (err: any) {
      showError(getErrorMessage(err, t('apiConnectorDetail.createManualOperationFailed')))
      throw err
    }
  }

  const handleSearchOperations = async () => {
    setCurrentPage(1)
    setAppliedQuery(searchQuery.trim())
  }

  const handleToggleOperationStatus = async (operation: ApiOperation) => {
    const nextStatus = operation.status === 'active' ? 'disabled' : 'active'
    try {
      const updated = await setOperationStatus(operation.id, nextStatus)
      if (selectedOperation?.operation_uid === operation.operation_uid) {
        setSelectedOperation(updated)
      }
      if (selectedConnector) {
        await fetchOperations(selectedConnector.id, {
          page: currentPage,
          pageSize: operationsPageSize || 10,
          query: appliedQuery || undefined,
          status: undefined,
        })
        await fetchOperationStats(selectedConnector.id)
      }
      showSuccess(nextStatus === 'active' ? t('apiConnectorDetail.operationEnabled') : t('apiConnectorDetail.operationDisabled'))
    } catch (err: any) {
      showError(getErrorMessage(err, t('apiConnectorDetail.updateOperationStatusFailed')))
    }
  }

  const handleSaveManualOperation = async (values: ManualOperationValues) => {
    if (!selectedOperation || selectedOperation.source !== 'manual') {
      showError(t('apiConnectorDetail.manualOnlyEdit'))
      throw new Error(t('apiConnectorDetail.manualOnlyEdit'))
    }
    if (!values.pathTemplate.trim()) {
      showError(t('apiConnectorDetail.fillPathTemplate'))
      throw new Error(t('apiConnectorDetail.fillPathTemplate'))
    }
    const requestSchema = parseJsonInput(values.requestSchemaText, 'Request Schema')
    const responseSchema = parseJsonInput(values.responseSchemaText, 'Response Schema')
    try {
      const updated = await modifyOperation(selectedOperation.id, {
        method: values.method,
        path_template: values.pathTemplate.trim(),
        operation_id: values.operationId.trim() || null,
        summary: values.summary.trim(),
        request_schema: requestSchema,
        response_schema: responseSchema,
      })
      setSelectedOperation(updated)
      if (selectedConnector) {
        await fetchOperations(selectedConnector.id, {
          page: currentPage,
          pageSize: operationsPageSize || 10,
          query: appliedQuery || undefined,
          status: undefined,
        })
        await fetchOperationStats(selectedConnector.id)
      }
      showSuccess(t('apiConnectorDetail.manualOperationUpdated'))
    } catch (err: any) {
      showError(getErrorMessage(err, t('apiConnectorDetail.updateManualOperationFailed')))
      throw err
    }
  }

  const handleStartEditManualOperation = (operation: ApiOperation) => {
    if (operation.source !== 'manual') {
      showError(t('apiConnectorDetail.manualOnlyEdit'))
      return
    }
    setSelectedOperation(operation)
    setEditOperationDialogOpen(true)
  }

  const handleDeleteManualOperationFromRow = async (operation: ApiOperation) => {
    if (operation.source !== 'manual') {
      showError(t('apiConnectorDetail.manualOnlyDelete'))
      return
    }
    try {
      await removeOperation(operation.id)
      if (selectedOperation?.operation_uid === operation.operation_uid) {
        setSelectedOperation(null)
      }
      if (selectedConnector) {
        await fetchOperations(selectedConnector.id, {
          page: currentPage,
          pageSize: operationsPageSize || 10,
          query: appliedQuery || undefined,
          status: undefined,
        })
        await fetchOperationStats(selectedConnector.id)
      }
      showSuccess(t('apiConnectorDetail.manualOperationDeleted'))
    } catch (err: any) {
      showError(getErrorMessage(err, t('apiConnectorDetail.deleteManualOperationFailed')))
    }
  }

  const handleCallOperation = async () => {
    if (!selectedOperation) {
      showError(t('apiConnectorDetail.selectOperation'))
      return
    }

    try {
      const params = parseJsonInput(callParametersText, t('apiConnectorDetail.callParameters'))
      const result = await executeOperation(selectedOperation.operation_uid, params)
      setCallResult(result)
      if (result.error) {
        showError(t('apiConnectorDetail.callFailed') + `: ${result.error}`)
        return
      }
      showSuccess(t('apiConnectorDetail.callSuccess'))
    } catch (err: any) {
      showError(getErrorMessage(err, t('apiConnectorDetail.callFailed')))
    }
  }

  const handleOpenOperationTest = (operation: ApiOperation) => {
    setSelectedOperation(operation)
    setCallResult(null)
    setCallDialogOpen(true)
  }

  const handleRefresh = async () => {
    if (!Number.isFinite(connectorIdNumber)) {
      return
    }
    try {
      await fetchConnectors()
      await fetchOperations(connectorIdNumber, {
        page: currentPage,
        pageSize: operationsPageSize || 10,
        query: appliedQuery || undefined,
        status: undefined,
      })
      await fetchOperationStats(connectorIdNumber)
    } catch (err: any) {
      showError(getErrorMessage(err, t('apiConnectorDetail.loadOperationsFailed')))
    }
  }

  const handleImportOpenApi = () => {
    setImportSchemaDialogOpen(true)
  }

  const handleSyncSchemaClick = () => {
    void handleSyncSchema()
  }

  if (!Number.isFinite(connectorIdNumber)) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{t('apiConnectorDetail.invalidConnectorId')}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-4">
      <ContainerDetailHeader
        parentLabel={t('apiConnectorDetail.parentLabel')}
        onParentNavigate={() => navigate('/api-connectors')}
        title={selectedConnector?.name ?? t('apiConnectorDetail.loadingConnector')}
        meta={
          selectedConnector ? (
            <span className="font-mono text-xs">{selectedConnector.base_url}</span>
          ) : null
        }
      />

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!selectedConnector ? (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>{t('apiConnectorDetail.connectorNotFound')}</AlertDescription>
        </Alert>
      ) : (
        <>
          <div className="space-y-4">
            <PageStatsActionBar
              stats={
                <>
                  <div className="flex items-center gap-2">
                    <Braces className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">{t('apiConnectorDetail.pathCount')}:</span>
                    <span className="text-lg font-semibold tabular-nums">{operationStats.path_count}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Cable className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground">{t('apiConnectorDetail.apiTotal')}:</span>
                        <Popover>
                          <PopoverTrigger asChild>
                            <button
                              type="button"
                              className="text-lg font-semibold tabular-nums underline decoration-dotted underline-offset-4"
                              title={t('apiConnectorDetail.viewApiDistribution')}
                            >
                              {operationStats.total}
                            </button>
                          </PopoverTrigger>
                          <PopoverContent className="w-64 p-3" align="start">
                            <div className="space-y-3 text-sm">
                              <div className="font-medium">{t('apiConnectorDetail.apiDistribution')}</div>
                              <div>
                                <div className="mb-1 text-xs text-muted-foreground">{t('apiConnectorDetail.byStatus')}</div>
                                <div className="space-y-1 text-xs">
                                  <div className="flex items-center justify-between">
                                    <span>{t('apiConnectorDetail.statusActive')}</span>
                                    <span className="font-medium">{operationStats.active}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span>{t('apiConnectorDetail.statusDisabled')}</span>
                                    <span className="font-medium">{operationStats.disabled}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span>{t('apiConnectorDetail.statusStale')}</span>
                                    <span className="font-medium">{operationStats.stale}</span>
                                  </div>
                                </div>
                              </div>
                              <div>
                                <div className="mb-1 text-xs text-muted-foreground">{t('apiConnectorDetail.bySource')}</div>
                                <div className="space-y-1 text-xs">
                                  <div className="flex items-center justify-between">
                                    <span>{t('apiConnectorDetail.sourceManual')}</span>
                                    <span className="font-medium">{operationStats.manual}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span>{t('apiConnectorDetail.sourceImported')}</span>
                                    <span className="font-medium">{operationStats.imported}</span>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </PopoverContent>
                        </Popover>
                      </div>
                    </div>
                  </div>
                </>
              }
              statsClassName="gap-4"
            />

            <OpenApiMetaPanel metadata={selectedConnector.schema_metadata ?? {}} />
            <ImportOpenApiDialog
              open={importSchemaDialogOpen}
              onOpenChange={setImportSchemaDialogOpen}
              disabled={loading}
              onImport={(content) => handleSyncSchema(content)}
            />
            <ListDetailToolbar
              searchQuery={searchQuery}
              searchPlaceholder={t('apiConnectorDetail.searchOperations')}
              onSearchQueryChange={setSearchQuery}
              onClearSearchQuery={() => {
                setSearchQuery('')
                setAppliedQuery('')
                setCurrentPage(1)
              }}
              onSearchSubmit={() => {
                void handleSearchOperations()
              }}
              primaryAction={{
                label: t('apiConnectorDetail.addApi'),
                onClick: () => setAddOperationDialogOpen(true),
                icon: Plus,
                disabled: loading,
              }}
              overflowItems={[
                {
                  label: t('common.refresh'),
                  icon: RefreshCw,
                  onClick: () => {
                    void handleRefresh()
                  },
                },
                selectedConnector.schema_source_type === 'openapi_upload'
                  ? {
                      label: t('apiConnectorDetail.importOpenApi'),
                      icon: Upload,
                      onClick: handleImportOpenApi,
                    }
                  : {
                      label: t('apiConnectorDetail.syncSchema'),
                      icon: RefreshCw,
                      onClick: handleSyncSchemaClick,
                    },
              ]}
            />
            <ManualOperationDialog
              mode="create"
              open={addOperationDialogOpen}
              onOpenChange={setAddOperationDialogOpen}
              disabled={loading}
              onSubmit={handleAddManualOperation}
            />
            <ApiOperationTable
              operations={operations}
              selectedOperationUid={selectedOperation?.operation_uid}
              onSelectOperation={setSelectedOperation}
              onTestOperation={handleOpenOperationTest}
              onToggleOperationStatus={(operation) => {
                void handleToggleOperationStatus(operation)
              }}
              onEditManualOperation={(operation) => {
                handleStartEditManualOperation(operation)
              }}
              onDeleteManualOperation={(operation) => {
                void handleDeleteManualOperationFromRow(operation)
              }}
              operationsPage={operationsPage}
              operationsPageSize={operationsPageSize}
              operationsTotal={operationsTotal}
              operationsTotalPages={operationsTotalPages}
              onPageChange={setCurrentPage}
            />

            {selectedOperation?.source === 'manual' && (
              <ManualOperationDialog
                mode="edit"
                open={editOperationDialogOpen}
                onOpenChange={setEditOperationDialogOpen}
                disabled={loading}
                initialValues={{
                  method: selectedOperation.method,
                  pathTemplate: selectedOperation.path_template,
                  summary: selectedOperation.summary ?? '',
                  operationId: selectedOperation.operation_id ?? '',
                  requestSchemaText: JSON.stringify(
                    selectedOperation.request_schema ?? {},
                    null,
                    2
                  ),
                  responseSchemaText: JSON.stringify(
                    selectedOperation.response_schema ?? {},
                    null,
                    2
                  ),
                }}
                onSubmit={handleSaveManualOperation}
              />
            )}

            <ApiOperationCallDialog
              open={callDialogOpen}
              onOpenChange={setCallDialogOpen}
              connectorName={selectedConnector.name}
              selectedOperation={selectedOperation}
              loading={loading}
              callParametersText={callParametersText}
              onCallParametersChange={setCallParametersText}
              callResult={callResult}
              onCallOperation={handleCallOperation}
            />
          </div>
        </>
      )}
    </div>
  )
}
