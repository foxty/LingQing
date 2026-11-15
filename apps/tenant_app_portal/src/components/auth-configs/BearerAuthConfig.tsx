import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'

interface BearerAuthConfigProps {
  secret: SecretCredentialFieldHandle
  maskedPreview?: string | null
  submitting: boolean
  tokenError?: string
  onDraftChange?: (value: string) => void
}

export function BearerAuthConfig({
  secret,
  maskedPreview,
  submitting,
  tokenError,
  onDraftChange,
}: BearerAuthConfigProps) {
  return (
    <SensitiveCredentialField
      id="add-bearer-token"
      label="Bearer Token"
      binding={secret}
      maskedPreview={maskedPreview}
      disabled={submitting}
      errorMsg={tokenError}
      onStartEdit={secret.startEdit}
      onCancelEdit={secret.cancelEdit}
      onDraftChange={onDraftChange ?? secret.setDraft}
    />
  )
}