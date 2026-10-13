/**
 * Artifact Picker Popover (@mention)
 *
 * Artifact @mention picker — user-accessible artifacts (any thread), filterable by title.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useState,
} from 'react'
import { ContextResource } from '@/types'
import { searchArtifactsForMention } from '@/lib/artifactContextApi'
import {
  BarChart3,
  FileSpreadsheet,
  Clock,
  AppWindow,
  Loader2,
  LineChart,
  Code2,
  Globe,
  Table2,
} from 'lucide-react'

interface ResourcePickerPopoverProps {
  inputValue: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (resource: ContextResource) => void
  selectedIds: Set<string>
}

export interface ResourcePickerPopoverHandle {
  handleKeyDown: (e: React.KeyboardEvent) => boolean
}

const ARTIFACT_TYPE_ICONS: Record<string, React.ReactNode> = {
  dashboard: <BarChart3 className="w-3.5 h-3.5" />,
  chart: <LineChart className="w-3.5 h-3.5" />,
  report: <FileSpreadsheet className="w-3.5 h-3.5" />,
  scheduled_task: <Clock className="w-3.5 h-3.5" />,
  app: <AppWindow className="w-3.5 h-3.5" />,
  code: <Code2 className="w-3.5 h-3.5" />,
  iframe: <Globe className="w-3.5 h-3.5" />,
  data_preview: <Table2 className="w-3.5 h-3.5" />,
}

const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  dashboard: '看板',
  chart: '图表',
  report: '报告',
  scheduled_task: '定时任务',
  app: '应用',
  code: '代码',
  iframe: '嵌入页',
  data_preview: '数据预览',
}

function artifactToContextResource(artifact: {
  id: number
  artifact_type: string
  title: string
  owner_username?: string | null
}): ContextResource {
  return {
    artifact_id: artifact.id,
    artifact_type: artifact.artifact_type,
    title: artifact.title,
    resource_type: artifact.artifact_type,
    resource_id: artifact.id,
    subtitle: artifact.owner_username ?? null,
  }
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
        const artifacts = await searchArtifactsForMention(searchTerm, 20)
        const mapped = artifacts
          .map(artifactToContextResource)
          .filter((item) => !selectedIds.has(`artifact-${item.artifact_id}`))
        setResults(mapped)
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
      const type = item.artifact_type
      if (!acc[type]) {
        acc[type] = []
      }
      acc[type].push(item)
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
    <div className="absolute bottom-full left-0 right-0 mb-1 z-50 rounded-md border bg-popover text-popover-foreground shadow-md max-h-72 overflow-y-auto">
      <div className="px-3 py-2 text-xs text-muted-foreground border-b">
        输入关键词筛选产物，或从列表选择
      </div>
      <div className="max-h-60 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : results.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            暂无可附加的产物
          </div>
        ) : (
          <div className="py-1">
            {typeOrder.map((type) => (
              <div key={type}>
                <div className="flex items-center gap-1.5 bg-muted/50 px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  {ARTIFACT_TYPE_ICONS[type] ?? <AppWindow className="w-3.5 h-3.5" />}
                  {ARTIFACT_TYPE_LABELS[type] || type}
                </div>
                {groupedResults[type].map((resource) => {
                  const item = flatItems.find(
                    (i) => i.resource.artifact_id === resource.artifact_id
                  )
                  const isActive = item?.globalIndex === activeIndex
                  return (
                    <button
                      key={`artifact-${resource.artifact_id}`}
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
                      {ARTIFACT_TYPE_ICONS[resource.artifact_type] ?? (
                        <AppWindow className="w-3.5 h-3.5" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{resource.title}</div>
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
