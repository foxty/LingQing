import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { dsFieldLabelClass, dsFieldPairRowClass } from '@/components/data-source/formLayout'

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
    <div className={dsFieldPairRowClass}>
      <Label htmlFor="add-api-key-name" className={dsFieldLabelClass}>
        Key Name
      </Label>
      <Input
        id="add-api-key-name"
        value={keyName}
        onChange={(e) => onKeyNameChange(e.target.value)}
        placeholder="X-API-Key"
        disabled={submitting}
        className="h-8 text-sm w-full min-w-0"
      />
      <Label htmlFor="add-api-key-value" className={dsFieldLabelClass}>
        Key Value
      </Label>
      <SensitiveCredentialField
        id="add-api-key-value"
        hideLabel
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