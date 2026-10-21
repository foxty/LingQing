/**
 * Artifact picker popover (+ attach context).
 *
 * User-accessible artifacts (any thread), filterable by title via standalone search.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from 'react'
import { useTranslation } from 'react-i18next'
import type { AttachedArtifact } from '@/types'
import './workbenchChatI18n'
import { searchArtifactsForMention } from '@/lib/artifactContextApi'
import { filterUnselectedMentionResults, reduceMentionPickerKeyDown } from '@/lib/chatMention'
import { Input } from '@/components/ui/input'
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
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (resource: AttachedArtifact) => void
  selectedIds: Set<string>
  /** When set, search is driven by the + attach picker instead of @ in the textarea. */
  standaloneSearch?: string
  onStandaloneSearchChange?: (value: string) => void
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

const ARTIFACT_TYPE_LABEL_KEYS: Record<string, string> = {
  dashboard: 'workbench.artifactTypeDashboard',
  chart: 'workbench.artifactTypeChart',
  report: 'workbench.artifactTypeReport',
  scheduled_task: 'workbench.artifactTypeScheduledTask',
  app: 'workbench.artifactTypeApp',
  code: 'workbench.artifactTypeCode',
  iframe: 'workbench.artifactTypeIframe',
  data_preview: 'workbench.artifactTypeDataPreview',
}

function artifactToAttachedArtifact(artifact: {
  id: number
  artifact_type: string
  title: string
  owner_username?: string | null
}): AttachedArtifact {
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
  { open, onOpenChange, onSelect, selectedIds, standaloneSearch = '', onStandaloneSearchChange },
  ref
) {
  const { t } = useTranslation()
  const [results, setResults] = useState<AttachedArtifact[]>([])
  const [loading, setLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  const artifactTypeLabels = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(ARTIFACT_TYPE_LABEL_KEYS).map(([type, key]) => [type, t(key)])
      ),
    [t]
  )

  const searchTerm = standaloneSearch

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
        const mapped = filterUnselectedMentionResults(
          artifacts.map(artifactToAttachedArtifact),
          selectedIds
        )
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
    (resource: AttachedArtifact) => {
      onSelect(resource)
      onOpenChange(false)
    },
    [onSelect, onOpenChange]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const action = reduceMentionPickerKeyDown({
        open,
        resultCount: results.length,
        activeIndex,
        key: e.key,
      })

      if (action.type === 'none') {
        return false
      }

      e.preventDefault()

      if (action.type === 'close') {
        onOpenChange(false)
        return true
      }

      if (action.type === 'move') {
        setActiveIndex(action.nextIndex)
        return true
      }

      if (action.type === 'select' && results[action.index]) {
        handleSelect(results[action.index])
        return true
      }

      return false
    },
    [open, results, activeIndex, onOpenChange, handleSelect]
  )

  useImperativeHandle(ref, () => ({ handleKeyDown }), [handleKeyDown])

  if (!open) return null

  const groupedResults = results.reduce<Record<string, AttachedArtifact[]>>(
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
  const flatItems: { resource: AttachedArtifact; globalIndex: number }[] = []
  typeOrder.forEach((type) => {
    groupedResults[type].forEach((resource) => {
      flatItems.push({ resource, globalIndex: flatItems.length })
    })
  })

  return (
    <div
      role="listbox"
      aria-label="Attach artifact"
      className="absolute bottom-full left-2 right-2 z-50 mb-2 max-h-72 overflow-y-auto rounded-md border bg-popover text-popover-foreground shadow-lg"
    >
      <div className="space-y-2 border-b px-3 py-2">
        {onStandaloneSearchChange ? (
          <Input
            value={standaloneSearch}
            onChange={(e) => onStandaloneSearchChange(e.target.value)}
            placeholder={t('workbench.mentionPickerHint')}
            className="h-8 text-sm"
            autoFocus
          />
        ) : (
          <div className="text-xs text-muted-foreground">{t('workbench.mentionPickerHint')}</div>
        )}
      </div>
      <div className="max-h-60 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : results.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            {t('workbench.mentionPickerEmpty')}
          </div>
        ) : (
          <div className="py-1">
            {typeOrder.map((type) => (
              <div key={type}>
                <div className="flex items-center gap-1.5 bg-muted/50 px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  {ARTIFACT_TYPE_ICONS[type] ?? <AppWindow className="w-3.5 h-3.5" />}
                  {artifactTypeLabels[type] || type}
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
