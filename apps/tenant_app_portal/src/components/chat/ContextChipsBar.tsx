/**
 * Context Chips Bar Component
 * Displays selected resource chips in a flex-wrap row above the textarea.
 */

import ContextChip from './ContextChip'
import type { AttachedArtifact } from '@/types'

interface ContextChipsBarProps {
  resources: AttachedArtifact[]
  onRemove: (resource: AttachedArtifact) => void
}

export default function ContextChipsBar({ resources, onRemove }: ContextChipsBarProps) {
  if (resources.length === 0) return null

  return (
    <div className="flex flex-wrap gap-1.5 px-0.5">
      {resources.map((resource) => (
        <ContextChip
          key={`artifact-${resource.artifact_id}`}
          resource={resource}
          onRemove={() => onRemove(resource)}
        />
      ))}
    </div>
  )
}
