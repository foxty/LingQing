import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { SecretFieldBinding } from '@/lib/sensitiveCredential'
import { getSecretMaskedPreview } from '@/lib/maskedFields'
import { Pencil, X } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      sensitiveCredentialField: {
        savedGeneric: '••••••••',
        edit: 'Edit credential',
        cancelEdit: 'Cancel edit',
        placeholder: 'Enter new value',
        createPlaceholder: 'Required',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    components: {
      sensitiveCredentialField: {
        savedGeneric: '••••••••',
        edit: '修改凭证',
        cancelEdit: '取消修改',
        placeholder: '输入新值',
        createPlaceholder: '必填',
      },
    },
  },
  true,
  true
)

interface SensitiveCredentialFieldProps {
  id: string
  label: React.ReactNode
  binding: SecretFieldBinding
  /** Partial mask from GET (e.g. ``dapi••••xy``); falls back to generic bullets. */
  maskedPreview?: string | null
  /**
   * When true, render the value control only — label and row/column layout come from the parent
   * (e.g. ``dsFieldRowClass`` / ``dsFieldPairRowClass``).
   */
  hideLabel?: boolean
  disabled?: boolean
  errorMsg?: string
  onStartEdit?: () => void
  onCancelEdit?: () => void
  onDraftChange: (value: string) => void
}

const savedInputClass =
  'h-8 w-full min-w-0 cursor-default font-mono text-sm bg-muted/30 read-only:focus-visible:ring-0'

export function SensitiveCredentialField({
  id,
  label,
  binding,
  maskedPreview,
  hideLabel = false,
  disabled = false,
  errorMsg,
  onStartEdit,
  onCancelEdit,
  onDraftChange,
}: SensitiveCredentialFieldProps) {
  const { t } = useTranslation()
  const showStored = binding.mode === 'edit' && binding.stored && !binding.editing

  const displayMask = useMemo(() => {
    const fromProp = maskedPreview ? getSecretMaskedPreview(maskedPreview) : null
    if (fromProp) {
      return fromProp
    }
    return t('components.sensitiveCredentialField.savedGeneric')
  }, [maskedPreview, t])

  const fieldShellClass = hideLabel ? 'w-full min-w-0' : 'w-full min-w-0 space-y-2'

  const labelNode = hideLabel ? null : (
    <Label htmlFor={id} className="text-sm font-medium leading-tight">
      {label}
    </Label>
  )

  if (showStored) {
    const savedControl = (
      <div className="flex w-full max-w-full min-w-0 items-start gap-1">
        <div className="min-w-0 flex-1">
          <Input
            id={id}
            readOnly
            value={displayMask}
            title={displayMask}
            disabled={disabled}
            aria-readonly
            tabIndex={-1}
            className={savedInputClass}
          />
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          disabled={disabled}
          aria-label={t('components.sensitiveCredentialField.edit')}
          onClick={() => onStartEdit?.()}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      </div>
    )

    return (
      <div className={fieldShellClass}>
        {labelNode}
        <>
          {savedControl}
          {errorMsg ? <p className="mt-1 text-xs text-destructive">{errorMsg}</p> : null}
        </>
      </div>
    )
  }

  const showCancel = binding.mode === 'edit' && binding.stored && binding.editing

  const editControl = (
    <div className="flex w-full max-w-full min-w-0 items-start gap-1">
      <div className="min-w-0 flex-1">
        <Input
          id={id}
          type="password"
          value={binding.draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onInput={(e) => onDraftChange(e.currentTarget.value)}
          placeholder={
            binding.mode === 'create'
              ? t('components.sensitiveCredentialField.createPlaceholder')
              : t('components.sensitiveCredentialField.placeholder')
          }
          disabled={disabled}
          autoComplete="new-password"
          errorMsg={errorMsg}
          className="h-8 w-full min-w-0 text-sm"
        />
      </div>
      {showCancel ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          disabled={disabled}
          aria-label={t('components.sensitiveCredentialField.cancelEdit')}
          onClick={() => {
            onDraftChange('')
            onCancelEdit?.()
          }}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      ) : null}
    </div>
  )

  return (
    <div className={fieldShellClass}>
      {labelNode}
      {editControl}
    </div>
  )
}