import { useMemo, useRef, useCallback, useState } from 'react'
import type { CSSProperties } from 'react'
import GridLayout, { type Layout } from 'react-grid-layout'
import { WidthProvider } from 'react-grid-layout'

import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

import WidgetRenderer from './WidgetRenderer'
import { resolveLayoutRightFirst } from '@/lib/dashboardLayout'
import type { DashboardFilter, DashboardWidget } from '@/lib/dashboardApi'

const Grid = WidthProvider(GridLayout)

export interface DashboardGridConfig {
  cols: number
  rows: number
  gap: number
  rowHeight: number
}

interface DashboardGridProps {
  widgets: DashboardWidget[]
  filters?: DashboardFilter[]
  config: DashboardGridConfig
  dashboardId: number
  isEditing: boolean
  selectedWidgetId: string | null
  isDragging: boolean
  onWidgetSelect: (widgetId: string) => void
  onWidgetsChange: (widgets: DashboardWidget[], updatedRows?: number) => Promise<void>
  onDragStateChange: (isDragging: boolean) => void
}

export default function DashboardGrid({
  widgets,
  filters = [],
  config,
  dashboardId,
  isEditing,
  selectedWidgetId,
  isDragging,
  onWidgetSelect,
  onWidgetsChange,
  onDragStateChange,
}: DashboardGridProps) {
  const originalLayoutRef = useRef<Layout[] | null>(null)
  const activeDragIdRef = useRef<string | null>(null)
  const baseRowsRef = useRef<number | null>(null)
  const [interactiveRows, setInteractiveRows] = useState<number | null>(null)

  const gridLayout = useMemo<Layout[]>(
    () =>
      widgets.map((widget) => ({
        i: widget.id,
        x: widget.position?.x ?? 0,
        y: widget.position?.y ?? 0,
        w: widget.position?.w ?? 6,
        h: Math.max(1, widget.position?.h ?? 1),
      })),
    [widgets]
  )

  const actualRows = useMemo(() => {
    if (gridLayout.length === 0) {
      return 1
    }
    return Math.max(1, ...gridLayout.map((item) => Math.max(1, item.y + Math.max(1, item.h))))
  }, [gridLayout])

  const effectiveRows = useMemo(() => {
    const baseRows = baseRowsRef.current ?? actualRows
    const liveRows = interactiveRows ?? baseRows
    return Math.max(config.rows, liveRows)
  }, [actualRows, config.rows, interactiveRows])

  const colMarkers = useMemo(
    () => Array.from({ length: config.cols }, (_, index) => index + 1),
    [config.cols]
  )
  const rowMarkers = useMemo(
    () => Array.from({ length: effectiveRows }, (_, index) => index + 1),
    [effectiveRows]
  )

  const applyLayoutToWidgets = useCallback(
    (nextLayout: Layout[]) => {
      // This is handled by parent, but we return the updated widgets for UI sync
      return widgets.map((widget) => {
        const item = nextLayout.find((entry) => entry.i === widget.id)
        if (!item) {
          return widget
        }

        return {
          ...widget,
          position: {
            x: item.x,
            y: item.y,
            w: item.w,
            h: item.h,
          },
        }
      })
    },
    [widgets]
  )

  const handleDragStop = useCallback(
    async (nextLayout: Layout[]) => {
      const baseLayout = originalLayoutRef.current ?? gridLayout
      const resolvedLayout = resolveLayoutRightFirst(
        baseLayout,
        nextLayout,
        config.cols,
        activeDragIdRef.current
      )
      const nextWidgets = applyLayoutToWidgets(resolvedLayout)
      const requiredRows = Math.max(
        1,
        ...resolvedLayout.map((item) => item.y + Math.max(1, item.h))
      )
      await onWidgetsChange(nextWidgets, requiredRows)
      originalLayoutRef.current = null
      activeDragIdRef.current = null
      baseRowsRef.current = null
      setInteractiveRows(null)
      onDragStateChange(false)
    },
    [gridLayout, config.cols, applyLayoutToWidgets, onWidgetsChange, onDragStateChange]
  )

  const handleResizeStop = useCallback(
    async (nextLayout: Layout[]) => {
      const baseLayout = originalLayoutRef.current ?? gridLayout
      const resolvedLayout = resolveLayoutRightFirst(
        baseLayout,
        nextLayout,
        config.cols,
        activeDragIdRef.current
      )
      const nextWidgets = applyLayoutToWidgets(resolvedLayout)
      const requiredRows = Math.max(
        1,
        ...resolvedLayout.map((item) => item.y + Math.max(1, item.h))
      )
      await onWidgetsChange(nextWidgets, requiredRows)
      originalLayoutRef.current = null
      activeDragIdRef.current = null
      baseRowsRef.current = null
      setInteractiveRows(null)
      onDragStateChange(false)
    },
    [gridLayout, config.cols, applyLayoutToWidgets, onWidgetsChange, onDragStateChange]
  )

  const gridOverlayStyle = useMemo<CSSProperties>(() => {
    const cols = config.cols
    const rowHeight = config.rowHeight
    const lineAlpha = isDragging ? 0.35 : 0.12

    return {
      backgroundImage:
        `linear-gradient(rgba(204, 204, 204, ${lineAlpha}) 1px, transparent 1px), ` +
        `linear-gradient(90deg, rgba(204, 204, 204, ${lineAlpha}) 1px, transparent 1px)`,
      backgroundSize: `calc(100% / ${cols}) ${rowHeight}px`,
    }
  }, [isDragging, config.cols, config.rowHeight])

  if (widgets.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-2 text-muted-foreground">
          <p>No widgets in this dashboard</p>
        </div>
      </div>
    )
  }

  return (
    <div
      className="relative bg-background"
      style={{
        ...gridOverlayStyle,
        minHeight: effectiveRows * config.rowHeight,
      }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-6">
        {colMarkers.map((col, index) => (
          <div
            key={col}
            className="absolute top-0 text-[10px] text-gray-200"
            style={{
              left: `calc(${(index / config.cols) * 100}% + 4px)`,
              top: -16,
            }}
          >
            {col}
          </div>
        ))}
      </div>
      <div className="pointer-events-none absolute inset-y-0 left-0 w-6">
        {rowMarkers.map((row, index) => (
          <div
            key={row}
            className="absolute left-0 text-[10px] text-gray-200"
            style={{
              top: index * config.rowHeight + 4,
              left: -10,
            }}
          >
            {row}
          </div>
        ))}
      </div>
      <Grid
        className="layout"
        cols={config.cols}
        rowHeight={config.rowHeight}
        margin={[0, 0]}
        containerPadding={[0, 0]}
        compactType={null}
        autoSize={false}
        resizeHandles={['se']}
        draggableHandle=".widget-drag-area"
        draggableCancel=".widget-action-button"
        layout={gridLayout}
        isDraggable={isEditing}
        isResizable={isEditing}
        onDragStart={(_layout, _oldItem, newItem) => {
          originalLayoutRef.current = gridLayout
          activeDragIdRef.current = newItem?.i ?? null
          baseRowsRef.current = actualRows
          setInteractiveRows(actualRows)
          onDragStateChange(true)
        }}
        onDrag={(nextLayout: Layout[]) => {
          const nextRows = Math.max(1, ...nextLayout.map((item) => item.y + Math.max(1, item.h)))
          setInteractiveRows(Math.max(config.rows, nextRows))
        }}
        onDragStop={(nextLayout: Layout[]) => {
          handleDragStop(nextLayout)
        }}
        onResizeStart={(_layout, _oldItem, newItem) => {
          originalLayoutRef.current = gridLayout
          activeDragIdRef.current = newItem?.i ?? null
          baseRowsRef.current = actualRows
          setInteractiveRows(actualRows)
          onDragStateChange(true)
        }}
        onResize={(nextLayout: Layout[]) => {
          const nextRows = Math.max(1, ...nextLayout.map((item) => item.y + Math.max(1, item.h)))
          setInteractiveRows(Math.max(config.rows, nextRows))
        }}
        onResizeStop={(nextLayout: Layout[]) => {
          handleResizeStop(nextLayout)
        }}
      >
        {widgets.map((widget) => (
          <div key={widget.id} className="h-full w-full" style={{ padding: config.gap / 2 }}>
            <WidgetRenderer
              dashboardId={dashboardId}
              widget={widget}
              filters={filters}
              isEditing={isEditing}
              isDragging={isDragging}
              isSelected={selectedWidgetId === widget.id}
              onEdit={(widgetId) => {
                onWidgetSelect(widgetId)
              }}
            />
          </div>
        ))}
      </Grid>
    </div>
  )
}
