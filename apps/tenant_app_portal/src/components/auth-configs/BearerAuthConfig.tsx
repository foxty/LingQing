import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Label } from '@/components/ui/label'

i18n.addResourceBundle('en', 'translation', {
  components: {
    authConfigs: {
      bearerPlaceholder: 'Enter bearer token',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    authConfigs: {
      bearerPlaceholder: '输入 Bearer Token',
    },
  },
}, true, true)
import { Input } from '@/components/ui/input'

interface BearerAuthConfigProps {
  token: string
  isAuthConfigured: boolean
  submitting: boolean
  onTokenChange: (value: string) => void
}

/**
 * Bearer token authentication configuration form.
 * Simple single-field input for bearer token value.
 */
export function BearerAuthConfig({
  token,
  submitting,
  onTokenChange,
}: BearerAuthConfigProps) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2">
      <Label htmlFor="add-bearer-token">Bearer Token</Label>
      <Input
        id="add-bearer-token"
        type="password"
        value={token}
        onChange={(e) => onTokenChange(e.target.value)}
        placeholder={t('components.authConfigs.bearerPlaceholder')}
        disabled={submitting}
      />
    </div>
  )
}
