import { User, Paperclip } from 'lucide-react'
import { Message } from '@/types'
import { getMessageAttachedArtifacts } from '@/lib/messageAttachedArtifacts'
import ContextChip from './ContextChip'

interface HumanMessageProps {
  message: Message
}

export default function HumanMessage({ message }: HumanMessageProps) {
  const contextResources = getMessageAttachedArtifacts(message.message_metadata)

  return (
    <div className="flex items-start space-x-3 flex-row-reverse space-x-reverse">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <User className="h-4 w-4" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col items-end space-y-1">
        <div className="ml-auto w-fit min-w-[9rem] max-w-[min(92%,42rem)] rounded-lg bg-primary px-4 py-2 text-primary-foreground">
          {contextResources && contextResources.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {contextResources.map((resource) => (
                <ContextChip
                  key={`artifact-${resource.artifact_id ?? resource.resource_id}`}
                  resource={resource}
                  readOnly
                  variant="message"
                />
              ))}
            </div>
          )}
          {message.artifact && (
            <div className="flex items-center gap-1 text-xs mb-2 px-2 py-1 bg-primary-foreground/20 rounded-md w-fit">
              <Paperclip className="h-3 w-3" />
              <span className="font-medium">{message.artifact.title}</span>
            </div>
          )}
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          {message.timestamp && (
            <p className="mt-1 text-right text-xs tabular-nums text-primary-foreground/70">
              {new Date(message.timestamp).toLocaleTimeString()}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
