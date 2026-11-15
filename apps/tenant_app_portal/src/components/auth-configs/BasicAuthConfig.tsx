import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'

i18n.addResourceBundle('en', 'translation', {
  components: {
    authConfigs: {
      basicUsernamePlaceholder: 'Enter username',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    authConfigs: {
      basicUsernamePlaceholder: '输入用户名',
    },
  },
}, true, true)

interface BasicAuthConfigProps {
  username: string
  passwordSecret: SecretCredentialFieldHandle
  maskedPreview?: string | null
  submitting: boolean
  usernameError?: string
  passwordError?: string
  onUsernameChange: (value: string) => void
  onPasswordDraftChange?: (value: string) => void
}

export function BasicAuthConfig({
  username,
  passwordSecret,
  maskedPreview,
  submitting,
  usernameError,
  passwordError,
  onUsernameChange,
  onPasswordDraftChange,
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
          placeholder={t('components.authConfigs.basicUsernamePlaceholder')}
          disabled={submitting}
          errorMsg={usernameError}
        />
      </div>
      <SensitiveCredentialField
        id="add-basic-password"
        label="Password"
        binding={passwordSecret}
        maskedPreview={maskedPreview}
        disabled={submitting}
        errorMsg={passwordError}
        onStartEdit={passwordSecret.startEdit}
        onCancelEdit={passwordSecret.cancelEdit}
        onDraftChange={onPasswordDraftChange ?? passwordSecret.setDraft}
      />
    </div>
  )
}