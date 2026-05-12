import * as React from 'react'

import { cn } from '@/lib/utils'

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  errorMsg?: string
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, errorMsg, ...props }, ref) => {
    const hasError = errorMsg && errorMsg.trim().length > 0

    return (
      <div className={cn('relative w-full', hasError && 'mb-5')}>
        <textarea
          className={cn(
            'flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
            hasError && 'border-red-500 focus-visible:ring-red-500',
            className
          )}
          ref={ref}
          {...props}
        />
        {hasError && (
          <span className="absolute bottom-0 left-0 translate-y-full text-xs text-destructive mt-1.5">
            {errorMsg}
          </span>
        )}
      </div>
    )
  }
)
Textarea.displayName = 'Textarea'

export { Textarea }
