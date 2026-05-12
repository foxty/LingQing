import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Label } from '@/components/ui/label'

i18n.addResourceBundle('en', 'translation', {
  components: {
    authConfigs: {
      basicUsernamePlaceholder: 'Enter username',
      basicPasswordPlaceholder: 'Enter password',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    authConfigs: {
      basicUsernamePlaceholder: '输入用户名',
      basicPasswordPlaceholder: '输入密码',
    },
  },
}, true, true)
import { Input } from '@/components/ui/input'

interface BasicAuthConfigProps {
  username: string
  password: string
  isAuthConfigured: boolean
  submitting: boolean
  onUsernameChange: (value: string) => void
  onPasswordChange: (value: string) => void
}

/**
 * HTTP Basic authentication configuration form.
 * Standard username/password authentication.
 */
export function BasicAuthConfig({
  username,
  password,
  isAuthConfigured,
  submitting,
  onUsernameChange,
  onPasswordChange,
}: BasicAuthConfigProps) {
  const { t } = useTranslation()
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="space-y-2">
        <Label htmlFor="add-basic-username">Username</Label>
        <Input
          id="add-basic-username"
          value={username}
          onChange={(e) => onUsernameChange(e.target.value)}
          placeholder={isAuthConfigured ? t('components.authConfigs.basicUsernamePlaceholder') : t('components.authConfigs.basicUsernamePlaceholder')}
          disabled={submitting}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="add-basic-password">Password</Label>
        <Input
          id="add-basic-password"
          type="password"
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          placeholder={isAuthConfigured ? t('components.authConfigs.basicPasswordPlaceholder') : t('components.authConfigs.basicPasswordPlaceholder')}
          disabled={submitting}
        />
      </div>
    </div>
  )
}
