import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

export function DeactivateUserButton({
  label,
  disabled,
  reason,
  onClick,
}: {
  label: string
  disabled: boolean
  reason: string | null
  onClick: () => void
}) {
  const button = (
    <Button size="sm" variant="outline" disabled={disabled} onClick={onClick}>
      {label}
    </Button>
  )
  if (!reason) {
    return button
  }
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex">{button}</span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-left">
          {reason}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
