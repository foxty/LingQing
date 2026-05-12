/**
 * Artifacts Panel Component
 * Right sidebar for displaying artifacts with adjustable width
 * Supports list view (collapsed) and detail view (expanded)
 */

import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import ArtifactRenderer from './ArtifactRenderer'

i18n.addResourceBundle('en', 'translation', {
  components: {
    artifactsPanel: {
      collapse: 'Collapse panel',
      backToList: 'Back to list',
      share: 'Share',
      title: 'Artifacts',
      loading: 'Loading...',
      empty: 'No artifacts in this conversation',
      noneSelected: 'No artifact selected',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    artifactsPanel: {
      collapse: '收起面板',
      backToList: '返回列表',
      share: '共享',
      title: '产物',
      loading: '加载中...',
      empty: '此对话暂无产物',
      noneSelected: '未选择产物',
    },
  },
}, true, true)
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import { Button } from '@/components/ui/button'
import { ResizeHandle } from '@/components/ui/ResizeHandle'
import { useResizable } from '@/hooks/useResizable'
import type { AclShareResourceType } from '@/lib/aclSharesApi'
import { formatDate } from '@/lib/dateTime'
import { Artifact } from '@/types'
import { ChevronLeft, Share2, X } from 'lucide-react'
import { useState } from 'react'

interface ArtifactsPanelProps {
  /** All artifacts for the thread */
  artifacts: Artifact[]
  /** Currently selected artifact (controls detail view) */
  selectedArtifact?: Artifact | null
  /** Callback to update selected artifact */
  onArtifactSelect: (artifact: Artifact) => void
  /** Callback when user wants to go back to list (clear selection) */
  onClearSelection?: () => void
  /** Callback to collapse the panel */
  onCollapse: () => void
  /** Whether artifacts are loading */
  loading?: boolean
  /** Width of the panel in pixels */
  width: number
  /** Callback to update width */
  onWidthChange: (width: number) => void
  /** Shared session title shown in the pane header */
  sessionTitle?: string
}

type ViewMode = 'list' | 'detail'

const SHAREABLE_ARTIFACT_TYPES: Record<string, AclShareResourceType> = {
  dashboard: 'dashboard',
  report: 'report',
  scheduled_task: 'scheduled_task',
  app: 'app',
}

function parseResourceIdFromUrl(url?: string | null): number | null {
  if (!url) {
    return null
  }
  const patterns = [
    /\/dashboards\/(\d+)/,
    /\/reports\/(\d+)/,
    /\/scheduled-tasks\/(\d+)/,
    /\/apps\/(\d+)/,
  ]
  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match) {
      const parsed = Number(match[1])
      if (Number.isFinite(parsed)) {
        return parsed
      }
    }
  }
  return null
}

function getArtifactShareTarget(
  artifact: Artifact
): { resourceType: AclShareResourceType; resourceId: number } | null {
  const resourceType = SHAREABLE_ARTIFACT_TYPES[artifact.artifact_type]
  if (!resourceType) {
    return null
  }
  const resourceId =
    typeof artifact.resource_id === 'number'
      ? artifact.resource_id
      : parseResourceIdFromUrl(artifact.url)
  if (resourceId === null) {
    return null
  }
  return { resourceType, resourceId }
}

export default function ArtifactsPanel({
  artifacts,
  selectedArtifact,
  onArtifactSelect,
  onClearSelection,
  onCollapse,
  loading = false,
  width,
  onWidthChange,
  sessionTitle,
}: ArtifactsPanelProps) {
  const { t } = useTranslation()
  const [shareDialogOpen, setShareDialogOpen] = useState(false)

  // View mode is derived from selectedArtifact state
  const viewMode: ViewMode = selectedArtifact ? 'detail' : 'list'
  const currentArtifact = selectedArtifact
  const shareTarget = currentArtifact ? getArtifactShareTarget(currentArtifact) : null

  // Use resizable hook for drag-to-resize functionality
  const { isDragging, handleMouseDown, containerRef } = useResizable(width, {
    minWidth: 200,
    maxWidth: 1000,
    onWidthChange,
    direction: 'left',
  })

  return (
    <div
      ref={containerRef}
      className="flex flex-col bg-background border-l h-full select-none relative"
      style={{
        width: `${width}px`,
        willChange: isDragging ? 'width' : 'auto',
        contain: 'layout style paint',
      }}
    >
      {/* List View */}
      {viewMode === 'list' && (
        <>
          {/* Header */}
          <div className="flex items-center justify-between border-b p-3 shrink-0">
            <div className="min-w-0">
              <h3 className="font-semibold text-sm truncate">
                {sessionTitle || t('components.artifactsPanel.title')}
              </h3>
              <p className="text-xs text-muted-foreground">
                {t('components.artifactsPanel.title')} · {artifacts.length}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onCollapse}
              className="h-6 w-6 p-0"
              title={t('components.artifactsPanel.collapse')}
            >
              <X className="w-4 h-4" />
            </Button>
          </div>

          {/* Artifacts List */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                {t('components.artifactsPanel.loading')}
              </div>
            ) : artifacts.length > 0 ? (
              <div className="divide-y">
                {artifacts.map((artifact) => (
                  <button
                    key={artifact.id}
                    onClick={() => onArtifactSelect(artifact)}
                    className="w-full px-4 py-3 text-left hover:bg-muted transition-colors border-none text-sm"
                  >
                    <div className="font-medium truncate">{artifact.title}</div>
                    <div className="text-xs text-muted-foreground truncate">
                      {artifact.artifact_type}
                    </div>
                    {artifact.created_at && (
                      <div className="text-xs text-muted-foreground">
                        {formatDate(artifact.created_at)}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                {t('components.artifactsPanel.empty')}
              </div>
            )}
          </div>
        </>
      )}

      {/* Detail View */}
      {viewMode === 'detail' && (
        <>
          {/* Header with Back Button */}
          <div className="flex items-center justify-between border-b p-3 shrink-0 gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearSelection}
              className="h-6 w-6 p-0 flex-shrink-0"
              title={t('components.artifactsPanel.backToList')}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold text-sm truncate">{currentArtifact?.title}</h3>
              {sessionTitle ? (
                <p className="text-xs text-muted-foreground truncate">{sessionTitle}</p>
              ) : null}
            </div>
            {currentArtifact && shareTarget && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShareDialogOpen(true)}
                className="h-7 px-2 flex-shrink-0"
                title={t('components.artifactsPanel.share')}
              >
                <Share2 className="w-3.5 h-3.5 mr-1" />
                {t('components.artifactsPanel.share')}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={onCollapse}
              className="h-6 w-6 p-0 flex-shrink-0"
              title={t('components.artifactsPanel.collapse')}
            >
              <X className="w-4 h-4" />
            </Button>
          </div>

          {/* Artifact Content - Full screen */}
          <div className="flex-1 overflow-hidden relative">
            {currentArtifact ? (
              <ArtifactRenderer artifact={currentArtifact} isDragging={isDragging} />
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                {t('components.artifactsPanel.noneSelected')}
              </div>
            )}
            {isDragging && <div className="absolute inset-0 bg-primary/5 pointer-events-none" />}
          </div>
        </>
      )}

      {/* Resize Handle */}
      <ResizeHandle onMouseDown={handleMouseDown} isDragging={isDragging} position="left" />

      {currentArtifact && shareTarget && (
        <ResourceAclShareDialog
          open={shareDialogOpen}
          onOpenChange={setShareDialogOpen}
          resourceType={shareTarget.resourceType}
          resourceId={shareTarget.resourceId}
          resourceTitle={currentArtifact.title}
        />
      )}
    </div>
  )
}
