import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'

interface ApiKeyAuthConfigProps {
  keyName: string
  keyValueSecret: SecretCredentialFieldHandle
  maskedPreview?: string | null
  submitting: boolean
  keyValueError?: string
  onKeyNameChange: (value: string) => void
  onKeyValueDraftChange: (value: string) => void
}

export function ApiKeyAuthConfig({
  keyName,
  keyValueSecret,
  maskedPreview,
  submitting,
  keyValueError,
  onKeyNameChange,
  onKeyValueDraftChange,
}: ApiKeyAuthConfigProps) {
  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <Label htmlFor="add-api-key-name">Key Name</Label>
        <Input
          id="add-api-key-name"
          value={keyName}
          onChange={(e) => onKeyNameChange(e.target.value)}
          placeholder="X-API-Key"
          disabled={submitting}
        />
      </div>
      <SensitiveCredentialField
        id="add-api-key-value"
        label="Key Value"
        binding={keyValueSecret}
        maskedPreview={maskedPreview}
        disabled={submitting}
        errorMsg={keyValueError}
        onStartEdit={keyValueSecret.startEdit}
        onCancelEdit={keyValueSecret.cancelEdit}
        onDraftChange={onKeyValueDraftChange}
      />
    </div>
  )
}
