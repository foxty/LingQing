import { cn } from '@/lib/utils'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { modelsRegistryKey, registerModelsRegistryI18n } from './i18n'

export interface ConnectionTestFeedbackState {
  ok: boolean
  message: string
}

interface ConnectionTestFeedbackProps {
  result: ConnectionTestFeedbackState
  className?: string
}

/** Plain inline text beside Test connection — no banner chrome (DESIGN §5). */
export default function ConnectionTestFeedback({ result, className }: ConnectionTestFeedbackProps) {
  registerModelsRegistryI18n()
  const { t } = useTranslation()

  const text = result.message.trim() || (result.ok ? t(modelsRegistryKey('testSuccess')) : t(modelsRegistryKey('testFailed')))

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
        'inline-flex max-w-2xl basis-full items-start gap-1.5 text-sm text-destructive',
        className
      )}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{text}</span>
    </p>
  )
}
