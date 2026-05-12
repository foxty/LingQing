/**
 * Context Chips Bar Component
 * Displays selected resource chips in a flex-wrap row above the textarea.
 */

import ContextChip from './ContextChip'
import { ContextResource } from '@/types'

interface ContextChipsBarProps {
  resources: ContextResource[]
  onRemove: (resource: ContextResource) => void
}

export default function ContextChipsBar({ resources, onRemove }: ContextChipsBarProps) {
  if (resources.length === 0) return null

  return (
    <div className="flex flex-wrap gap-1.5 px-3 pt-2 pb-1 border-b">
      {resources.map((resource) => (
        <ContextChip
          key={`${resource.resource_type}-${resource.resource_id}`}
          resource={resource}
          onRemove={() => onRemove(resource)}
        />
      ))}
    </div>
  )
}
