import { cn } from '@/lib/utils'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface ConnectionTestResult {
  ok: boolean
  message: string
}

interface ConnectionTestFeedbackProps {
  result: ConnectionTestResult
  className?: string
  /** When true, failed results wrap to the next row in a flex toolbar (e.g. beside Test). */
  errorOnNewLine?: boolean
  successFallback?: string
  failureFallback?: string
}

/** Plain inline pass/fail text for connection diagnostics (DESIGN §5). */
export default function ConnectionTestFeedback({
  result,
  className,
  errorOnNewLine = false,
  successFallback,
  failureFallback,
}: ConnectionTestFeedbackProps) {
  const { t } = useTranslation()

  const text =
    result.message.trim() ||
    (result.ok
      ? (successFallback ?? t('common.connectionTestSuccess'))
      : (failureFallback ?? t('common.connectionTestFailed')))

  if (result.ok) {
    return (
      <p role="status" className={cn('inline-flex max-w-full items-center gap-1.5 text-sm text-success', className)}>
        <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden />
        <span>{text}</span>
      </p>
    )
  }

  return (
    <p
      role="alert"
      className={cn(
        'inline-flex max-w-2xl items-start gap-1.5 text-sm text-destructive',
        errorOnNewLine && 'basis-full',
        className
      )}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{text}</span>
    </p>
  )
}
