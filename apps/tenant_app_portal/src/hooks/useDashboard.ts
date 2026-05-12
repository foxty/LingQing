import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  collectValueOnlyFilterUpdates,
  FILTER_VALUE_PERSIST_DEBOUNCE_MS,
  getWidgetFilterSignature,
  toFilterValueOverrides,
} from '@/lib/dashboardFilterUpdates'

import type {
  Dashboard,
  DashboardBaseUpdatePayload,
  DashboardConfig,
  DashboardFilter,
  DashboardFilterCreatePayload,
  DashboardFilterUpdatePayload,
  DashboardWidget,
  DashboardWidgetCreatePayload,
  DashboardWidgetUpdatePayload,
} from '@/lib/dashboardApi'
import {
  createDashboardFilter,
  createDashboardWidget,
  deleteDashboard,
  getDashboard,
  listDashboards,
  queryDashboardSqlPreview,
  queryWidgetData,
  queryWidgetPreview,
  removeDashboardFilter,
  removeDashboardWidget,
  updateDashboard,
  updateDashboardFilter,
  updateDashboardWidget,
} from '@/lib/dashboardApi'

const WIDGET_DATA_STALE_TIME_MS = 30_000

type DashboardMutationOptions = {
  invalidateDashboard?: boolean
  invalidateWidgetData?: boolean
}

export function useDashboard(dashboardId: number, refetchInterval?: number) {
  return useQuery({
    queryKey: ['dashboards', dashboardId],
    queryFn: () => getDashboard(dashboardId),
    enabled: Number.isFinite(dashboardId),
    refetchInterval,
  })
}

export function useDashboards() {
  return useQuery({
    queryKey: ['dashboards'],
    queryFn: () => listDashboards(),
  })
}

export function useDashboardWidgetData(
  dashboardId: number,
  widgetId: string,
  options?: {
    refetchInterval?: number
    filters?: DashboardFilter[]
    query?: string
  }
) {
  const filters = options?.filters ?? []
  const filterSignature = getWidgetFilterSignature({ query: options?.query }, filters)
  return useQuery({
    queryKey: ['dashboard-data', dashboardId, widgetId, filterSignature],
    queryFn: () =>
      queryWidgetData(dashboardId, widgetId, {
        filters: toFilterValueOverrides(filters),
      }),
    enabled: Number.isFinite(dashboardId) && Boolean(widgetId),
    staleTime: WIDGET_DATA_STALE_TIME_MS,
    refetchInterval: options?.refetchInterval,
  })
}

export function useDashboardSqlPreview(
  dashboardId: number,
  options: {
    dataSourceId: number
    query: string
    limit?: number
  }
) {
  const limit = options.limit ?? 50
  return useQuery({
    queryKey: ['dashboard-sql-preview', dashboardId, options.dataSourceId, limit, options.query],
    queryFn: () =>
      queryDashboardSqlPreview(dashboardId, {
        dataSourceId: options.dataSourceId,
        query: options.query,
        limit,
      }),
    enabled: false,
  })
}

export function useDashboardWidgetPreview(
  dashboardId: number,
  widgetId: string,
  options?: {
    limit?: number
    query?: string | null
    dataSourceId?: number | null
  }
) {
  const limit = options?.limit ?? 50
  const query = options?.query ?? null
  const dataSourceId = options?.dataSourceId ?? null

  return useQuery({
    queryKey: ['dashboard-preview', dashboardId, widgetId, limit, query, dataSourceId],
    queryFn: () =>
      queryWidgetPreview(dashboardId, widgetId, {
        limit,
        query,
        dataSourceId,
      }),
    enabled: false,
  })
}

export function useUpdateDashboard() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number
      payload: DashboardBaseUpdatePayload
    } & DashboardMutationOptions) => updateDashboard(id, payload),
    onSuccess: (updated, variables) => {
      queryClient.invalidateQueries({ queryKey: ['dashboards', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['dashboards'] })
      if (variables?.invalidateWidgetData !== false) {
        queryClient.invalidateQueries({ queryKey: ['dashboard-data', updated.id] })
      }
    },
  })
}

export function useDeleteDashboard() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: number) => deleteDashboard(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboards'] })
    },
  })
}

export function useCreateDashboardWidget() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: DashboardWidgetCreatePayload }) =>
      createDashboardWidget(id, payload),
    onSuccess: (_created, variables) => {
      queryClient.invalidateQueries({ queryKey: ['dashboards', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['dashboards'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-data', variables.id] })
    },
  })
}

export function useUpdateDashboardWidget() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      id,
      widgetId,
      payload,
    }: {
      id: number
      widgetId: string
      payload: DashboardWidgetUpdatePayload
    } & DashboardMutationOptions) => updateDashboardWidget(id, widgetId, payload),
    onSuccess: (_updated, variables) => {
      queryClient.invalidateQueries({ queryKey: ['dashboards', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['dashboards'] })
      if (variables.invalidateWidgetData !== false) {
        queryClient.invalidateQueries({ queryKey: ['dashboard-data', variables.id] })
      }
    },
  })
}

export function useRemoveDashboardWidget() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, widgetId }: { id: number; widgetId: string }) =>
      removeDashboardWidget(id, widgetId),
    onSuccess: (_updated, variables) => {
      queryClient.invalidateQueries({ queryKey: ['dashboards', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['dashboards'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-data', variables.id] })
    },
  })
}

export function useCreateDashboardFilter() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: DashboardFilterCreatePayload }) =>
      createDashboardFilter(id, payload),
    onSuccess: (_created, variables) => {
      queryClient.invalidateQueries({ queryKey: ['dashboards', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['dashboards'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-data', variables.id] })
    },
  })
}

export function useUpdateDashboardFilter() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      id,
      filterId,
      payload,
    }: {
      id: number
      filterId: string
      payload: DashboardFilterUpdatePayload
    } & DashboardMutationOptions) => updateDashboardFilter(id, filterId, payload),
    onSuccess: (_updated, variables) => {
      if (variables.invalidateDashboard !== false) {
        queryClient.invalidateQueries({ queryKey: ['dashboards', variables.id] })
        queryClient.invalidateQueries({ queryKey: ['dashboards'] })
      }
      if (variables.invalidateWidgetData !== false) {
        queryClient.invalidateQueries({ queryKey: ['dashboard-data', variables.id] })
      }
    },
  })
}

export function useRemoveDashboardFilter() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, filterId }: { id: number; filterId: string }) =>
      removeDashboardFilter(id, filterId),
    onSuccess: (_updated, variables) => {
      queryClient.invalidateQueries({ queryKey: ['dashboards', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['dashboards'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-data', variables.id] })
    },
  })
}

interface UseDashboardEditorParams {
  dashboardId: number
  dashboard: Dashboard | undefined
  draftConfig: DashboardConfig | null
  layout: { cols: number; rows: number; gap: number; rowHeight: number }
  widgets: DashboardWidget[]
  filters: DashboardFilter[]
  selectedWidgetId: string | null
  selectedFilterId: string | null
  selectedFilter: DashboardFilter | null
  selectedFilterDraft: DashboardFilter | null
  newFilterId: string | null
  setDraftConfig: Dispatch<SetStateAction<DashboardConfig | null>>
  setSelectedWidgetId: Dispatch<SetStateAction<string | null>>
  setSelectedFilterId: Dispatch<SetStateAction<string | null>>
  setSelectedFilterDraft: Dispatch<SetStateAction<DashboardFilter | null>>
  setNewFilterId: Dispatch<SetStateAction<string | null>>
  updateDashboardBase: (args: {
    id: number
    payload: {
      layout?: DashboardConfig['layout']
      title?: string
      description?: string
    }
    invalidateWidgetData?: boolean
  }) => Promise<unknown>
  updateDashboardWidget: (args: {
    id: number
    widgetId: string
    payload: {
      chartType?: DashboardWidget['chartType']
      position?: DashboardWidget['position']
      dataSourceId?: number
      query?: string
      fieldMapping?: DashboardWidget['fieldMapping']
      displayConfig?: DashboardWidget['displayConfig']
    }
    invalidateWidgetData?: boolean
  }) => Promise<unknown>
  removeDashboardWidget: (args: { id: number; widgetId: string }) => Promise<unknown>
  createDashboardFilter: (args: {
    id: number
    payload: {
      name: string
      type: DashboardFilter['type']
      paramKey?: string
      value?: any
      dataSourceId?: number
      optionsQuery?: string
      options?: DashboardFilter['options']
      allowMultiple?: boolean
      timePrecision?: DashboardFilter['timePrecision']
      description?: string
      required?: boolean
    }
  }) => Promise<DashboardFilter>
  updateDashboardFilter: (args: {
    id: number
    filterId: string
    payload: {
      name?: string
      type?: DashboardFilter['type']
      paramKey?: string
      value?: any
      dataSourceId?: number
      optionsQuery?: string
      options?: DashboardFilter['options']
      allowMultiple?: boolean
      timePrecision?: DashboardFilter['timePrecision']
      description?: string
      required?: boolean
    }
    invalidateDashboard?: boolean
    invalidateWidgetData?: boolean
  }) => Promise<DashboardFilter>
  removeDashboardFilter: (args: { id: number; filterId: string }) => Promise<unknown>
}

export function useDashboardEditor({
  dashboardId,
  dashboard,
  draftConfig,
  layout,
  widgets,
  filters,
  selectedWidgetId,
  selectedFilterId,
  selectedFilter,
  selectedFilterDraft,
  newFilterId,
  setDraftConfig,
  setSelectedWidgetId,
  setSelectedFilterId,
  setSelectedFilterDraft,
  setNewFilterId,
  updateDashboardBase,
  updateDashboardWidget,
  removeDashboardWidget,
  createDashboardFilter,
  updateDashboardFilter,
  removeDashboardFilter,
}: UseDashboardEditorParams) {
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingValueUpdatesRef = useRef<Map<string, DashboardFilter['value']>>(new Map())

  const flushPendingFilterValues = async () => {
    const pending = Array.from(pendingValueUpdatesRef.current.entries())
    pendingValueUpdatesRef.current.clear()
    if (pending.length === 0) {
      return
    }

    await Promise.all(
      pending.map(([filterId, value]) =>
        updateDashboardFilter({
          id: dashboardId,
          filterId,
          payload: { value },
          invalidateDashboard: false,
          invalidateWidgetData: false,
        })
      )
    )
  }

  const scheduleFilterValuePersist = (updates: Array<{ id: string; value: DashboardFilter['value'] }>) => {
    for (const update of updates) {
      pendingValueUpdatesRef.current.set(update.id, update.value)
    }
    if (persistTimerRef.current) {
      clearTimeout(persistTimerRef.current)
    }
    persistTimerRef.current = setTimeout(() => {
      persistTimerRef.current = null
      void flushPendingFilterValues()
    }, FILTER_VALUE_PERSIST_DEBOUNCE_MS)
  }

  useEffect(() => {
    return () => {
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current)
      }
    }
  }, [])

  const handleWidgetsChange = async (nextWidgets: DashboardWidget[], updatedRows?: number) => {
    if (!dashboard || !draftConfig) {
      return
    }

    const layoutConfig = {
      type: 'grid',
      cols: layout.cols,
      rows: updatedRows ?? layout.rows,
      gap: layout.gap,
      rowHeight: layout.rowHeight,
    }

    setDraftConfig((prev) =>
      prev
        ? {
            ...prev,
            layout: layoutConfig,
            widgets: nextWidgets,
          }
        : prev
    )

    await updateDashboardBase({
      id: dashboardId,
      payload: {
        layout: layoutConfig,
      },
      invalidateWidgetData: false,
    })

    const changedWidgets = nextWidgets.filter((nextWidget) => {
      const previousWidget = widgets.find((widget) => widget.id === nextWidget.id)
      if (!previousWidget) {
        return false
      }
      return (
        previousWidget.position.x !== nextWidget.position.x ||
        previousWidget.position.y !== nextWidget.position.y ||
        previousWidget.position.w !== nextWidget.position.w ||
        previousWidget.position.h !== nextWidget.position.h
      )
    })

    await Promise.all(
      changedWidgets.map((widget) =>
        updateDashboardWidget({
          id: dashboardId,
          widgetId: widget.id,
          payload: {
            position: widget.position,
          },
          invalidateWidgetData: false,
        })
      )
    )
  }

  const handleWidgetFieldChange = (
    field: 'query' | 'displayConfig' | 'fieldMapping' | 'dataSourceId',
    value: any
  ) => {
    setDraftConfig((prev) => {
      if (!prev || !selectedWidgetId) return prev

      const nextWidgets = prev.widgets.map((widget) => {
        if (widget.id !== selectedWidgetId) return widget
        if (field === 'query') {
          return { ...widget, query: value }
        }
        if (field === 'displayConfig') {
          return { ...widget, displayConfig: value ?? undefined }
        }
        if (field === 'fieldMapping') {
          return { ...widget, fieldMapping: value ?? undefined }
        }
        if (field === 'dataSourceId') {
          return { ...widget, dataSourceId: value }
        }
        return widget
      })

      return {
        ...prev,
        widgets: nextWidgets,
      }
    })
  }

  const handleSaveWidget = async () => {
    if (!dashboard || !draftConfig || !selectedWidgetId) return
    const widget = draftConfig.widgets.find((item) => item.id === selectedWidgetId)
    if (!widget) {
      return
    }

    await updateDashboardWidget({
      id: dashboardId,
      payload: {
        chartType: widget.chartType,
        position: widget.position,
        dataSourceId: widget.dataSourceId,
        query: widget.query,
        fieldMapping: widget.fieldMapping,
        displayConfig: widget.displayConfig,
      },
      widgetId: widget.id,
    })
  }

  const handleRemoveWidget = async () => {
    if (!dashboard || !draftConfig || !selectedWidgetId) return
    const nextWidgets = draftConfig.widgets.filter((widget) => widget.id !== selectedWidgetId)
    const nextConfig = {
      ...draftConfig,
      widgets: nextWidgets,
    }
    setDraftConfig(nextConfig)
    setSelectedWidgetId(null)
    await removeDashboardWidget({ id: dashboardId, widgetId: selectedWidgetId })
  }

  const handleFiltersChange = async (nextFilters: DashboardFilter[], persist = true) => {
    if (!dashboard || !draftConfig) {
      return
    }

    const previousFilters = filters
    const valueUpdates = persist
      ? collectValueOnlyFilterUpdates(previousFilters, nextFilters, newFilterId)
      : []
    setDraftConfig({
      ...draftConfig,
      filters: nextFilters,
    })

    if (valueUpdates.length > 0) {
      scheduleFilterValuePersist(valueUpdates)
    }
  }

  const handleFilterUpdate = (patch: Partial<DashboardFilter>) => {
    if (!selectedFilterId) return
    const nextFilters = filters.map((filter) =>
      filter.id === selectedFilterId ? { ...filter, ...patch } : filter
    )
    const nextDraft =
      (selectedFilterDraft ?? selectedFilter)?.id === selectedFilterId
        ? { ...(selectedFilterDraft ?? (selectedFilter as DashboardFilter)), ...patch }
        : null
    if (nextDraft) {
      setSelectedFilterDraft(nextDraft)
    }
    void handleFiltersChange(nextFilters, false)
  }

  const handleSaveFilter = async (updatedWidgets?: DashboardWidget[]) => {
    if (!dashboard || !draftConfig || !selectedFilterId) return

    const targetFilter = filters.find((filter) => filter.id === selectedFilterId)
    if (!targetFilter) {
      return
    }

    if (newFilterId && selectedFilterId === newFilterId) {
      const created = await createDashboardFilter({
        id: dashboardId,
        payload: {
          name: targetFilter.name,
          type: targetFilter.type,
          paramKey: targetFilter.paramKey,
          value: targetFilter.value,
          dataSourceId: targetFilter.dataSourceId,
          optionsQuery: targetFilter.optionsQuery,
          options: targetFilter.options,
          allowMultiple: targetFilter.allowMultiple,
          timePrecision: targetFilter.timePrecision,
          description: targetFilter.description,
          required: targetFilter.required,
        },
      })

      setDraftConfig((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          filters: (prev.filters ?? []).map((filter) =>
            filter.id === selectedFilterId ? created : filter
          ),
        }
      })
      setSelectedFilterId(created.id)
      setSelectedFilterDraft(created)
      setNewFilterId(null)
    } else {
      const updated = await updateDashboardFilter({
        id: dashboardId,
        filterId: targetFilter.id,
        payload: {
          name: targetFilter.name,
          type: targetFilter.type,
          paramKey: targetFilter.paramKey,
          value: targetFilter.value,
          dataSourceId: targetFilter.dataSourceId,
          optionsQuery: targetFilter.optionsQuery,
          options: targetFilter.options,
          allowMultiple: targetFilter.allowMultiple,
          timePrecision: targetFilter.timePrecision,
          description: targetFilter.description,
          required: targetFilter.required,
        },
      })

      setDraftConfig((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          filters: (prev.filters ?? []).map((filter) =>
            filter.id === targetFilter.id ? updated : filter
          ),
        }
      })
      setSelectedFilterDraft(updated)
    }

    if (updatedWidgets && updatedWidgets.length > 0) {
      await Promise.all(
        updatedWidgets.map((widget) =>
          updateDashboardWidget({
            id: dashboardId,
            widgetId: widget.id,
            payload: {
              query: widget.query,
            },
          })
        )
      )

      setDraftConfig((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          widgets: prev.widgets.map((widget) => {
            const updated = updatedWidgets.find((w) => w.id === widget.id)
            return updated || widget
          }),
        }
      })
    }
  }

  const handleRemoveFilter = async () => {
    if (!selectedFilterId) return
    const nextFilters = filters.filter((filter) => filter.id !== selectedFilterId)
    const isUnsavedNewFilter = newFilterId === selectedFilterId
    if (!isUnsavedNewFilter) {
      await removeDashboardFilter({ id: dashboardId, filterId: selectedFilterId })
    }
    if (newFilterId === selectedFilterId) {
      setNewFilterId(null)
    }
    setSelectedFilterId(null)
    setSelectedFilterDraft(null)
    await handleFiltersChange(nextFilters, false)
  }

  return {
    handleWidgetsChange,
    handleWidgetFieldChange,
    handleSaveWidget,
    handleRemoveWidget,
    handleFiltersChange,
    handleFilterUpdate,
    handleSaveFilter,
    handleRemoveFilter,
  }
}
