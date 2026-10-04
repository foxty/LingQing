import * as React from 'react'

import { cn } from '@/lib/utils'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  errorMsg?: string
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, errorMsg, ...props }, ref) => {
    const hasError = errorMsg && errorMsg.trim().length > 0

    return (
      <div className={cn('relative w-full', hasError && 'mb-5')}>
        <input
          type={type}
          className={cn(
            'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
            hasError && 'border-destructive focus-visible:ring-destructive',
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
Input.displayName = 'Input'

export { Input }
