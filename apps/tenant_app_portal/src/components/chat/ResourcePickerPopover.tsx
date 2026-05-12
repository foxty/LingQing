/**
 * Resource Picker Popover Component
 *
 * Triggers when the user types @ in the textarea.
 * Shows a searchable list of context resources grouped by type.
 * Supports keyboard navigation (↑↓ Enter) and click selection.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useState,
} from 'react'
import { ContextResource } from '@/types'
import { searchContextResources } from '@/lib/contextResourcesApi'
import {
  FileText,
  BarChart3,
  FileSpreadsheet,
  Clock,
  AppWindow,
  Database,
  Loader2,
} from 'lucide-react'

interface ResourcePickerPopoverProps {
  /** Current textarea value */
  inputValue: string
  /** Whether the picker should be open */
  open: boolean
  /** Called when the picker should close */
  onOpenChange: (open: boolean) => void
  /** Called when a resource is selected */
  onSelect: (resource: ContextResource) => void
  /** Already-selected resource IDs to exclude from results */
  selectedIds: Set<string>
}

export interface ResourcePickerPopoverHandle {
  handleKeyDown: (e: React.KeyboardEvent) => boolean
}

const RESOURCE_TYPE_ICONS: Record<string, React.ReactNode> = {
  document: <FileText className="w-3.5 h-3.5" />,
  dashboard: <BarChart3 className="w-3.5 h-3.5" />,
  report: <FileSpreadsheet className="w-3.5 h-3.5" />,
  scheduled_task: <Clock className="w-3.5 h-3.5" />,
  app: <AppWindow className="w-3.5 h-3.5" />,
  asset: <Database className="w-3.5 h-3.5" />,
}

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  document: '文档',
  dashboard: '看板',
  report: '报告',
  scheduled_task: '定时任务',
  app: '应用',
  asset: '数据资产',
}

const ResourcePickerPopover = forwardRef<
  ResourcePickerPopoverHandle,
  ResourcePickerPopoverProps
>(function ResourcePickerPopover(
  { inputValue, open, onOpenChange, onSelect, selectedIds },
  ref
) {
  const [results, setResults] = useState<ContextResource[]>([])
  const [loading, setLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  const extractSearchTerm = useCallback((value: string): string | null => {
    const match = value.match(/@([^\s]*)$/)
    return match ? match[1] : null
  }, [])

  const searchTerm = extractSearchTerm(inputValue) ?? ''

  useEffect(() => {
    if (!open) {
      setResults([])
      setActiveIndex(0)
      return
    }

    const fetchResults = async () => {
      setLoading(true)
      try {
        const response = await searchContextResources(searchTerm, 8)
        const filtered = response.items.filter(
          (item) =>
            !selectedIds.has(`${item.resource_type}-${item.resource_id}`)
        )
        setResults(filtered)
        setActiveIndex(0)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }

    fetchResults()
  }, [open, searchTerm, selectedIds])

  const handleSelect = useCallback(
    (resource: ContextResource) => {
      onSelect(resource)
      onOpenChange(false)
    },
    [onSelect, onOpenChange]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!open) return false

      if (e.key === 'Escape') {
        e.preventDefault()
        onOpenChange(false)
        return true
      }

      if (results.length === 0) return false

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIndex((prev) => (prev + 1) % results.length)
        return true
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex((prev) => (prev - 1 + results.length) % results.length)
        return true
      }

      if (e.key === 'Enter') {
        e.preventDefault()
        if (results[activeIndex]) {
          handleSelect(results[activeIndex])
        }
        return true
      }

      return false
    },
    [open, results, activeIndex, onOpenChange, handleSelect]
  )

  useImperativeHandle(ref, () => ({ handleKeyDown }), [handleKeyDown])

  if (!open) return null

  const groupedResults = results.reduce<Record<string, ContextResource[]>>(
    (acc, item) => {
      if (!acc[item.resource_type]) {
        acc[item.resource_type] = []
      }
      acc[item.resource_type].push(item)
      return acc
    },
    {}
  )

  const typeOrder = Object.keys(groupedResults)
  const flatItems: { resource: ContextResource; globalIndex: number }[] = []
  typeOrder.forEach((type) => {
    groupedResults[type].forEach((resource) => {
      flatItems.push({ resource, globalIndex: flatItems.length })
    })
  })

  return (
    <div
      className="absolute bottom-full left-0 z-50 mb-2 w-full max-w-sm overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md"
      role="listbox"
      aria-label="选择引用资源"
    >
      <div className="border-b bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
        <span className="font-mono text-foreground">@{searchTerm || '…'}</span>
        <span className="ml-1.5">
          {searchTerm ? '搜索匹配资源' : '输入关键词筛选，或从列表选择'}
        </span>
      </div>

      <div className="max-h-64 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            搜索中...
          </div>
        ) : results.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            未找到匹配的资源
          </div>
        ) : (
          <div className="py-1">
            {typeOrder.map((type) => (
              <div key={type}>
                <div className="flex items-center gap-1.5 bg-muted/50 px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  {RESOURCE_TYPE_ICONS[type]}
                  {RESOURCE_TYPE_LABELS[type] || type}
                </div>
                {groupedResults[type].map((resource) => {
                  const item = flatItems.find(
                    (i) =>
                      i.resource.resource_type === resource.resource_type &&
                      i.resource.resource_id === resource.resource_id
                  )
                  const isActive = item?.globalIndex === activeIndex
                  return (
                    <button
                      key={`${resource.resource_type}-${resource.resource_id}`}
                      type="button"
                      role="option"
                      aria-selected={isActive}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-accent ${
                        isActive ? 'bg-accent' : ''
                      }`}
                      onClick={() => handleSelect(resource)}
                      onMouseEnter={() => {
                        if (item) setActiveIndex(item.globalIndex)
                      }}
                    >
                      {RESOURCE_TYPE_ICONS[resource.resource_type]}
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">
                          {resource.title}
                        </div>
                        {resource.subtitle && (
                          <div className="truncate text-xs text-muted-foreground">
                            {resource.subtitle}
                          </div>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
})

export default ResourcePickerPopover
