import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import { useSecretCredentialField } from '@/hooks/useSecretCredentialField'
import type { SecretFieldBinding, SecretFieldMode } from '@/lib/sensitiveCredential'
import { getSecretMaskedPreview } from '@/lib/maskedFields'
import { useEffect } from 'react'

interface IntegrationSecretFieldProps {
  fieldKey: string
  label: string
  mode: SecretFieldMode
  stored: boolean
  resetKey: string | number
  maskedPreview?: string | null
  disabled?: boolean
  errorMsg?: string
  onBindingChange: (key: string, binding: SecretFieldBinding) => void
  onUserEdit?: () => void
}

export function IntegrationSecretField({
  fieldKey,
  label,
  mode,
  stored,
  resetKey,
  maskedPreview,
  disabled,
  errorMsg,
  onBindingChange,
  onUserEdit,
}: IntegrationSecretFieldProps) {
  const secret = useSecretCredentialField(mode, stored, `${resetKey}-${fieldKey}`)

  useEffect(() => {
    onBindingChange(fieldKey, secret)
  }, [fieldKey, secret, onBindingChange])

  return (
    <SensitiveCredentialField
      id={`integration-secret-${fieldKey}`}
      label={label}
      binding={secret}
      maskedPreview={maskedPreview ? getSecretMaskedPreview(maskedPreview) ?? undefined : undefined}
      disabled={disabled}
      errorMsg={errorMsg}
      onStartEdit={() => {
        secret.startEdit()
        onUserEdit?.()
      }}
      onCancelEdit={() => {
        secret.cancelEdit()
        onUserEdit?.()
      }}
      onDraftChange={(value) => {
        secret.setDraft(value)
        onUserEdit?.()
      }}
    />
  )
}