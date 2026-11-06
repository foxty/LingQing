import * as React from 'react'
import { AlertCircle } from 'lucide-react'

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
            hasError && 'border-destructive pr-9 focus-visible:ring-destructive',
            className
          )}
          ref={ref}
          aria-invalid={hasError ? true : undefined}
          {...props}
        />
        {hasError && (
          <>
            <span
              className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-destructive"
              aria-hidden
            >
              <AlertCircle className="h-4 w-4" />
            </span>
            <span className="absolute bottom-0 left-0 mt-1.5 translate-y-full text-xs text-destructive">
              {errorMsg}
            </span>
          </>
        )}
      </div>
    )
  }
)
Input.displayName = 'Input'

export { Input }
