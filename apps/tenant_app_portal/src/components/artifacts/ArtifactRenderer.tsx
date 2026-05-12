import { Artifact } from '@/types'

interface ArtifactRendererProps {
  artifact: Artifact
  /** Disable pointer events during drag to avoid iframe capturing mouse events */
  isDragging?: boolean
}

export default function ArtifactRenderer({ artifact, isDragging = false }: ArtifactRendererProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {artifact.url ? (
          <iframe
            src={artifact.url}
            className={`w-full h-full border-0 ${isDragging ? 'pointer-events-none' : ''}`}
            title={artifact.title}
            sandbox="allow-scripts allow-same-origin allow-forms"
          />
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <p className="text-sm">No preview available for this artifact</p>
          </div>
        )}
      </div>
    </div>
  )
}
