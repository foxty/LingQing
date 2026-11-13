import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

const DEFAULT_MAX_CHARS = 56

type Props = {
  text: string | null | undefined
  emptyFallback?: string
  maxChars?: number
  className?: string
}

export default function TruncatedTextPopover({
  text,
  emptyFallback = '—',
  maxChars = DEFAULT_MAX_CHARS,
  className,
}: Props) {
  const value = text?.trim() || ''
  if (!value) {
    return <span className={cn('text-sm text-muted-foreground', className)}>{emptyFallback}</span>
  }

  const needsPopover = value.length > maxChars

  if (!needsPopover) {
    return <span className={cn('text-sm', className)}>{value}</span>
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'block max-w-full truncate text-left text-sm text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm',
            className
          )}
        >
          {value}
        </button>
      </PopoverTrigger>
      <PopoverContent className="max-w-sm whitespace-pre-wrap text-sm" align="start">
        {value}
      </PopoverContent>
    </Popover>
  )
}
