import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Label } from '@/components/ui/label'

i18n.addResourceBundle('en', 'translation', {
  components: {
    authConfigs: {
      apiKeyPlaceholder: 'Enter API key value',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    authConfigs: {
      apiKeyPlaceholder: '输入 API 密钥值',
    },
  },
}, true, true)
import { Input } from '@/components/ui/input'

interface ApiKeyAuthConfigProps {
  keyName: string
  keyValue: string
  isAuthConfigured: boolean
  submitting: boolean
  onKeyNameChange: (value: string) => void
  onKeyValueChange: (value: string) => void
}

/**
 * API Key authentication configuration form.
 * Allows users to specify custom header name and API key value.
 */
export function ApiKeyAuthConfig({
  keyName,
  keyValue,
  submitting,
  onKeyNameChange,
  onKeyValueChange,
}: ApiKeyAuthConfigProps) {
  const { t } = useTranslation()
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="space-y-2">
        <Label htmlFor="add-api-key-name">Key Name</Label>
        <Input
          id="add-api-key-name"
          value={keyName}
          onChange={(e) => onKeyNameChange(e.target.value)}
          placeholder="X-API-Key"
          disabled={submitting}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="add-api-key-value">Key Value</Label>
        <Input
          id="add-api-key-value"
          type="password"
          value={keyValue}
          onChange={(e) => onKeyValueChange(e.target.value)}
          placeholder={t('components.authConfigs.apiKeyPlaceholder')}
          disabled={submitting}
        />
      </div>
    </div>
  )
}
