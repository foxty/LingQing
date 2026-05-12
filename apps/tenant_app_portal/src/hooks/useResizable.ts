/**
 * useResizable Hook
 *
 * Provides drag-to-resize functionality with performance optimizations.
 * Uses requestAnimationFrame for smooth updates and supports customizable constraints.
 *
 * Features:
 * - 🎯 Smooth resizing with RAF throttling
 * - 📏 Configurable min/max width constraints
 * - ↔️  Bidirectional support (left/right)
 * - 🎨 Built-in drag state management
 * - 🧹 Automatic cleanup of listeners and animations
 *
 * @param initialWidth - Initial width in pixels
 * @param options - Configuration options (see UseResizableOptions)
 * @returns Resizing state and handlers (see UseResizableReturn)
 *
 * @example
 * Basic usage with ResizeHandle component:
 * ```tsx
 * import { useResizable } from '@/hooks/useResizable'
 * import { ResizeHandle } from '@/components/ui/ResizeHandle'
 *
 * function MyPanel() {
 *   const { width, isDragging, handleMouseDown, containerRef } = useResizable(400, {
 *     minWidth: 200,
 *     maxWidth: 800,
 *   })
 *
 *   return (
 *     <div ref={containerRef} style={{ width: `${width}px` }} className="relative">
 *       <div>Panel Content</div>
 *       <ResizeHandle onMouseDown={handleMouseDown} isDragging={isDragging} position="left" />
 *     </div>
 *   )
 * }
 * ```
 *
 * @example
 * With external state synchronization:
 * ```tsx
 * function MyPanel() {
 *   const [panelWidth, setPanelWidth] = useState(400)
 *
 *   const { isDragging, handleMouseDown, containerRef } = useResizable(panelWidth, {
 *     minWidth: 200,
 *     maxWidth: 1000,
 *     onWidthChange: setPanelWidth, // Sync to parent state
 *   })
 *
 *   return (
 *     <div ref={containerRef} style={{ width: `${panelWidth}px` }}>
 *       <p>Current width: {panelWidth}px</p>
 *       <ResizeHandle onMouseDown={handleMouseDown} isDragging={isDragging} />
 *     </div>
 *   )
 * }
 * ```
 *
 * @example
 * Right-side resize (drag from left to right increases width):
 * ```tsx
 * const { width, handleMouseDown, containerRef } = useResizable(400, {
 *   direction: 'right', // Default is 'left'
 * })
 *
 * <div ref={containerRef} style={{ width }}>
 *   <ResizeHandle onMouseDown={handleMouseDown} position="right" />
 * </div>
 * ```
 *
 * @example
 * Custom resize handle (without ResizeHandle component):
 * ```tsx
 * const { width, isDragging, handleMouseDown, containerRef } = useResizable(400)
 *
 * <div ref={containerRef} style={{ width }}>
 *   <div
 *     onMouseDown={handleMouseDown}
 *     className={`resize-handle ${isDragging ? 'active' : ''}`}
 *   >
 *     ⋮⋮
 *   </div>
 * </div>
 * ```
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Configuration options for useResizable hook
 */
export interface UseResizableOptions {
  /** Minimum width in pixels (default: 200) */
  minWidth?: number
  /** Maximum width in pixels (default: 1000) */
  maxWidth?: number
  /**
   * Callback invoked when width changes during drag.
   * Useful for syncing with external state or localStorage.
   */
  onWidthChange?: (width: number) => void
  /**
   * Direction of resize calculation (default: 'left')
   * - 'left': Dragging left increases width (for right-side panels)
   * - 'right': Dragging right increases width (for left-side panels)
   */
  direction?: 'left' | 'right'
  /**
   * Minimum change in pixels to trigger update (default: 1)
   * Higher values reduce update frequency but may feel less responsive
   */
  threshold?: number
  /**
   * Sync mode for onWidthChange callback (default: 'throttle')
   * - 'realtime': Call onWidthChange on every update (may cause lag)
   * - 'throttle': Throttle onWidthChange to every 50ms (recommended)
   * - 'onEnd': Only call onWidthChange when drag ends (smoothest)
   */
  syncMode?: 'realtime' | 'throttle' | 'onEnd'
  /**
   * Throttle interval in milliseconds (default: 50)
   * Only used when syncMode is 'throttle'
   */
  throttleMs?: number
}

/**
 * Return value from useResizable hook
 */
export interface UseResizableReturn {
  /** Current width in pixels */
  width: number
  /** Whether currently dragging */
  isDragging: boolean
  /** Mouse down handler - pass to resize handle element */
  handleMouseDown: (e: React.MouseEvent) => void
  /** Ref for the resizable container - must attach to resizing element */
  containerRef: React.RefObject<HTMLDivElement>
  /** Programmatically set width (respects min/max constraints) */
  setWidth: (width: number) => void
}

export function useResizable(
  initialWidth: number,
  options: UseResizableOptions = {}
): UseResizableReturn {
  const {
    minWidth = 200,
    maxWidth = 1000,
    onWidthChange,
    direction = 'left',
    threshold = 1,
    syncMode = 'throttle',
    throttleMs = 50,
  } = options

  const [width, setWidthState] = useState(initialWidth)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const rafIdRef = useRef<number | null>(null)
  const lastWidthRef = useRef(initialWidth)
  const lastSyncTimeRef = useRef(0)
  const pendingWidthRef = useRef<number | null>(null)
  const startXRef = useRef(0)
  const startWidthRef = useRef(0)

  // Use refs to avoid recreating effect on option changes
  const optionsRef = useRef({
    minWidth,
    maxWidth,
    onWidthChange,
    direction,
    threshold,
    syncMode,
    throttleMs,
  })
  optionsRef.current = {
    minWidth,
    maxWidth,
    onWidthChange,
    direction,
    threshold,
    syncMode,
    throttleMs,
  }

  const setWidth = useCallback(
    (newWidth: number, forceSync = false) => {
      const clampedWidth = Math.max(minWidth, Math.min(maxWidth, newWidth))
      setWidthState(clampedWidth)
      lastWidthRef.current = clampedWidth

      // Handle different sync modes
      if (syncMode === 'onEnd' && !forceSync) {
        // Store for later sync on drag end
        pendingWidthRef.current = clampedWidth
      } else if (syncMode === 'throttle' && !forceSync) {
        // Throttle updates
        const now = Date.now()
        if (now - lastSyncTimeRef.current >= throttleMs) {
          lastSyncTimeRef.current = now
          onWidthChange?.(clampedWidth)
        } else {
          // Store for later sync
          pendingWidthRef.current = clampedWidth
        }
      } else {
        // Realtime mode or forced sync
        onWidthChange?.(clampedWidth)
        pendingWidthRef.current = null
      }
    },
    [minWidth, maxWidth, onWidthChange, syncMode, throttleMs]
  )

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    // Record initial state for delta-based calculation
    startXRef.current = e.clientX
    startWidthRef.current = lastWidthRef.current
  }, [])

  useEffect(() => {
    if (!isDragging) return

    const handleGlobalMouseMove = (e: MouseEvent) => {
      e.preventDefault()

      // Cancel any pending animation frame
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current)
      }

      // Use requestAnimationFrame for smooth updates
      rafIdRef.current = requestAnimationFrame(() => {
        const { minWidth, maxWidth, onWidthChange, direction, threshold, syncMode, throttleMs } =
          optionsRef.current

        // Calculate width change based on mouse movement delta
        const deltaX = e.clientX - startXRef.current
        const newWidth = Math.round(
          direction === 'left' ? startWidthRef.current - deltaX : startWidthRef.current + deltaX
        )

        // Check constraints and threshold
        if (
          newWidth >= minWidth &&
          newWidth <= maxWidth &&
          Math.abs(newWidth - lastWidthRef.current) > threshold
        ) {
          const clampedWidth = Math.max(minWidth, Math.min(maxWidth, newWidth))
          setWidthState(clampedWidth)
          lastWidthRef.current = clampedWidth

          // Handle different sync modes
          if (syncMode === 'onEnd') {
            // Store for later sync on drag end
            pendingWidthRef.current = clampedWidth
          } else if (syncMode === 'throttle') {
            // Throttle updates
            const now = Date.now()
            if (now - lastSyncTimeRef.current >= throttleMs) {
              lastSyncTimeRef.current = now
              onWidthChange?.(clampedWidth)
            } else {
              // Store for later sync
              pendingWidthRef.current = clampedWidth
            }
          } else {
            // Realtime mode
            onWidthChange?.(clampedWidth)
            pendingWidthRef.current = null
          }
        }
      })
    }

    const handleGlobalMouseUp = () => {
      setIsDragging(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''

      // Cancel any pending animation frame
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current)
        rafIdRef.current = null
      }

      // Ensure final width is synced (for throttle/onEnd modes)
      if (pendingWidthRef.current !== null) {
        optionsRef.current.onWidthChange?.(pendingWidthRef.current)
        pendingWidthRef.current = null
      }
    }

    document.addEventListener('mousemove', handleGlobalMouseMove, { passive: false })
    document.addEventListener('mouseup', handleGlobalMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleGlobalMouseMove)
      document.removeEventListener('mouseup', handleGlobalMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''

      // Clean up animation frame on unmount
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current)
      }
    }
  }, [isDragging])

  return {
    width,
    isDragging,
    handleMouseDown,
    containerRef,
    setWidth,
  }
}
