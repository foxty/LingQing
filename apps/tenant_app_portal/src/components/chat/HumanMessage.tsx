import { User, Paperclip } from 'lucide-react'
import { ContextResource, Message } from '@/types'
import ContextChip from './ContextChip'

interface HumanMessageProps {
  message: Message
}

export default function HumanMessage({ message }: HumanMessageProps) {
  const contextResources = message.message_metadata?.context_resources as
    | ContextResource[]
    | undefined

  return (
    <div className="flex items-start space-x-3 flex-row-reverse space-x-reverse">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <User className="h-4 w-4" />
      </div>
      <div className="flex-1 space-y-1 items-end">
        <div className="relative rounded-lg px-4 py-2 pb-6 max-w-[80%] bg-primary text-primary-foreground ml-auto">
          {contextResources && contextResources.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {contextResources.map((resource) => (
                <ContextChip
                  key={`${resource.resource_type}-${resource.resource_id}`}
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
            <p className="absolute bottom-1 right-2 text-xs text-primary-foreground/70">
              {new Date(message.timestamp).toLocaleTimeString()}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
