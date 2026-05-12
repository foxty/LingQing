/**
 * ResizeHandle Component
 *
 * A reusable, accessible resize handle for adjustable panel boundaries.
 * Designed to work seamlessly with useResizable hook.
 *
 * Features:
 * - 🎯 Large hit area (2-3px) for easy grabbing
 * - 🎨 Visual feedback (hover, active states)
 * - ↔️  Supports all 4 directions (left/right/top/bottom)
 * - 🎭 Customizable styling via className
 * - 📱 Touch-action optimized for mobile
 *
 * @example
 * Basic usage with useResizable hook:
 * ```tsx
 * import { useResizable } from '@/hooks/useResizable'
 * import { ResizeHandle } from '@/components/ui/ResizeHandle'
 *
 * const { isDragging, handleMouseDown, containerRef } = useResizable(400)
 *
 * <div ref={containerRef} className="relative">
 *   <ResizeHandle
 *     onMouseDown={handleMouseDown}
 *     isDragging={isDragging}
 *     position="left" // For right-side panels
 *   />
 * </div>
 * ```
 *
 * @example
 * Custom styling:
 * ```tsx
 * <ResizeHandle
 *   onMouseDown={handleMouseDown}
 *   isDragging={isDragging}
 *   position="left"
 *   className="hover:bg-blue-500/20" // Custom hover color
 * />
 * ```
 *
 * @example
 * Different positions:
 * ```tsx
 * // Left side of panel (drag left/right)
 * <ResizeHandle position="left" {...props} />
 *
 * // Right side of panel (drag left/right)
 * <ResizeHandle position="right" {...props} />
 *
 * // Top of panel (drag up/down)
 * <ResizeHandle position="top" {...props} />
 *
 * // Bottom of panel (drag up/down)
 * <ResizeHandle position="bottom" {...props} />
 * ```
 */

import { cn } from '@/lib/utils'

interface ResizeHandleProps {
  /** Mouse down handler from useResizable hook */
  onMouseDown: (e: React.MouseEvent) => void
  /** Dragging state from useResizable hook */
  isDragging: boolean
  /**
   * Position of the handle relative to container (default: 'left')
   * - 'left': For right-side panels
   * - 'right': For left-side panels
   * - 'top': For bottom panels
   * - 'bottom': For top panels
   */
  position?: 'left' | 'right' | 'top' | 'bottom'
  /** Custom class name for additional styling */
  className?: string
}

export function ResizeHandle({
  onMouseDown,
  isDragging,
  position = 'left',
  className,
}: ResizeHandleProps) {
  const isHorizontal = position === 'left' || position === 'right'

  const baseClasses = cn(
    'absolute z-10 group',
    isHorizontal ? 'top-0 bottom-0 cursor-col-resize' : 'left-0 right-0 cursor-row-resize',
    className
  )

  const positionClasses = {
    left: 'left-0 w-2 hover:w-3 -ml-1',
    right: 'right-0 w-2 hover:w-3 -mr-1',
    top: 'top-0 h-2 hover:h-3 -mt-1',
    bottom: 'bottom-0 h-2 hover:h-3 -mb-1',
  }

  const indicatorClasses = {
    left: 'left-1 top-0 bottom-0 w-0.5',
    right: 'right-1 top-0 bottom-0 w-0.5',
    top: 'top-1 left-0 right-0 h-0.5',
    bottom: 'bottom-1 left-0 right-0 h-0.5',
  }

  return (
    <div
      onMouseDown={onMouseDown}
      className={cn(
        baseClasses,
        positionClasses[position],
        'bg-transparent hover:bg-primary/20 transition-all',
        isDragging && (isHorizontal ? 'w-3' : 'h-3'),
        isDragging && 'bg-primary/30'
      )}
      style={{ touchAction: 'none' }}
    >
      {/* Visible indicator line */}
      <div
        className={cn(
          'absolute transition-colors',
          indicatorClasses[position],
          'bg-border',
          isDragging && 'bg-primary'
        )}
      />
    </div>
  )
}
