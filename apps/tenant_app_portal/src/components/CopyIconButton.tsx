import { useCallback, useEffect, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { cn, copyToClipboard } from '@/lib/utils'

/** Clipboard action feedback for copy icon controls. */
export type CopyIconStatus = 'idle' | 'copied' | 'error'

export type CopyIconButtonVariant = 'default' | 'onPrimary'

export interface CopyIconButtonProps {
  /** Current copy feedback; button shows Check when `copied`. */
  status: CopyIconStatus
  onCopy: () => void
  /** `aria-label` / `title` when not in copied state. */
  label: string
  /** `aria-label` / `title` after successful copy (defaults to `label`). */
  copiedLabel?: string
  variant?: CopyIconButtonVariant
  className?: string
  disabled?: boolean
}

export interface CopyToClipboardIconButtonProps
  extends Pick<CopyIconButtonProps, 'label' | 'copiedLabel' | 'variant' | 'className' | 'disabled'> {
  /** String written to the clipboard on click. */
  text: string
  /** When this or `text` changes, copy feedback resets to idle. */
  resetKey?: string | number
}

const variantClasses: Record<CopyIconButtonVariant, string> = {
  default:
    'text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:ring-border',
  onPrimary:
    'text-primary-foreground/80 hover:bg-primary-foreground/15 hover:text-primary-foreground focus-visible:ring-primary-foreground/50',
}

export function useCopyToClipboard(text: string, resetKey?: string | number) {
  const [status, setStatus] = useState<CopyIconStatus>('idle')

  useEffect(() => {
    setStatus('idle')
  }, [resetKey, text])

  const copy = useCallback(async () => {
    const trimmed = text?.trim()
    if (!trimmed) {
      setStatus('error')
      return
    }
    const success = await copyToClipboard(trimmed)
    setStatus(success ? 'copied' : 'error')
  }, [text])

  return { status, copy }
}

/**
 * Compact icon-only copy control (Copy → Check). Pass localized `label` / `copiedLabel` from the caller.
 * Use when copy state is owned by a parent (e.g. footer fed from a turn container).
 */
export default function CopyIconButton({
  status,
  onCopy,
  label,
  copiedLabel,
  variant = 'default',
  className,
  disabled = false,
}: CopyIconButtonProps) {
  const accessibleName = status === 'copied' ? (copiedLabel ?? label) : label

  return (
    <button
      type="button"
      onClick={onCopy}
      disabled={disabled}
      className={cn(
        'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-sm transition-colors',
        'focus-visible:outline-none focus-visible:ring-1',
        variantClasses[variant],
        disabled && 'pointer-events-none opacity-50',
        className
      )}
      title={accessibleName}
      aria-label={accessibleName}
    >
      {status === 'copied' ? (
        <Check className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden />
      )}
    </button>
  )
}

/**
 * Icon copy button with built-in clipboard handling — one import for typical “copy this text” UI.
 */
export function CopyToClipboardIconButton({
  text,
  resetKey,
  label,
  copiedLabel,
  variant,
  className,
  disabled,
}: CopyToClipboardIconButtonProps) {
  const { status, copy } = useCopyToClipboard(text, resetKey)

  return (
    <CopyIconButton
      status={status}
      onCopy={() => void copy()}
      label={label}
      copiedLabel={copiedLabel}
      variant={variant}
      className={className}
      disabled={disabled}
    />
  )
}