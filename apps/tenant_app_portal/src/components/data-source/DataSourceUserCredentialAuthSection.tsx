import i18n from '@/i18n/config'
import type { OAuth2FormConfig } from '@/components/api-connector/types'
import DataSourceDatabricksOAuthForm from '@/components/data-source/DataSourceDatabricksOAuthForm'
import DataSourceFormSectionHeader from '@/components/data-source/DataSourceFormSectionHeader'
import {
  applyOidcUrlsFromHost,
  DATABRICKS_USER_AUTH_OAUTH2,
  DATABRICKS_USER_AUTH_PAT,
  type DatabricksUserCredentialAuthType,
} from '@/lib/dataSourceUserAuth'
import {
  dsFieldLabelClass,
  dsFieldRowClass,
  dsFieldRowStartClass,
  dsFormValueColumnInsetClass,
} from '@/components/data-source/formLayout'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import { KeyRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      dataSourceUserAuth: {
        sectionTitle: 'Per-user login',
        sectionHelp:
          'How each member authenticates when running queries. Catalog sync uses the login below.',
        loginMethod: 'Login method',
        databricksPat: 'Personal access token (PAT)',
        databricksOauth: 'OAuth 2.0',
        rdbmsPassword: 'Database username & password',
        rdbmsPasswordHelp: 'Members enter their own database username and password on Data Assets.',
        oauthAppHelp:
          'Client ID and secret from your Databricks OAuth app. OIDC URLs derive from the workspace URL; authorize scopes must match the OAuth app.',
      },
    },
  },
  true,
  true,
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    components: {
      dataSourceUserAuth: {
        sectionTitle: '按用户登录方式',
        sectionHelp: '成员执行查询时的认证方式。目录同步使用下方目录同步账号。',
        loginMethod: '登录方式',
        databricksPat: '个人访问令牌 (PAT)',
        databricksOauth: 'OAuth 2.0',
        rdbmsPassword: '数据库用户名和密码',
        rdbmsPasswordHelp: '成员在数据资产页填写自己的数据库账号与密码。',
        oauthAppHelp:
          '填写 OAuth 客户端 ID 与密钥；OIDC 地址由工作区 URL 推导；授权 scopes 须与 OAuth 应用一致。',
      },
    },
  },
  true,
  true,
)

export type DataSourceUserAuthFieldErrors = Partial<{
  oauthClientId: string
  oauthClientSecret: string
  oauthAuthorizeUrl: string
  oauthTokenUrl: string
  oauthScopes: string
}>

type DataSourceUserCredentialAuthSectionProps = {
  dataSourceType: 'postgres' | 'mysql' | 'databricks'
  disabled?: boolean
  host?: string
  userCredentialAuthType: DatabricksUserCredentialAuthType
  onUserCredentialAuthTypeChange: (value: DatabricksUserCredentialAuthType) => void
  oauth2Config: OAuth2FormConfig
  onOauth2ConfigChange: (updater: (prev: OAuth2FormConfig) => OAuth2FormConfig) => void
  oauthClientSecret: SecretCredentialFieldHandle
  maskedClientSecret?: string | null
  fieldErrors?: DataSourceUserAuthFieldErrors
  onClearFieldError?: (key: keyof DataSourceUserAuthFieldErrors) => void
}

export default function DataSourceUserCredentialAuthSection({
  dataSourceType,
  disabled = false,
  host = '',
  userCredentialAuthType,
  onUserCredentialAuthTypeChange,
  oauth2Config,
  onOauth2ConfigChange,
  oauthClientSecret,
  maskedClientSecret,
  fieldErrors,
  onClearFieldError,
}: DataSourceUserCredentialAuthSectionProps) {
  const { t } = useTranslation()
  const showOauthApp = dataSourceType === 'databricks' && userCredentialAuthType === DATABRICKS_USER_AUTH_OAUTH2

  if (dataSourceType !== 'databricks') {
    return (
      <div className="space-y-2.5 border-t border-border pt-4">
        <DataSourceFormSectionHeader
          icon={KeyRound}
          title={t('components.dataSourceUserAuth.sectionTitle')}
          description={t('components.dataSourceUserAuth.sectionHelp')}
        />
        <div className={dsFieldRowClass}>
          <Label className={dsFieldLabelClass}>{t('components.dataSourceUserAuth.loginMethod')}</Label>
          <p className="text-sm text-muted-foreground min-w-0">
            {t('components.dataSourceUserAuth.rdbmsPassword')}
          </p>
        </div>
        <p className={`text-xs text-muted-foreground leading-relaxed ${dsFormValueColumnInsetClass}`}>
          {t('components.dataSourceUserAuth.rdbmsPasswordHelp')}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2.5 border-t border-border pt-4">
      <DataSourceFormSectionHeader
        icon={KeyRound}
        title={t('components.dataSourceUserAuth.sectionTitle')}
        description={t('components.dataSourceUserAuth.sectionHelp')}
      />
      <div className={dsFieldRowStartClass}>
        <Label className={`${dsFieldLabelClass} pt-2`}>{t('components.dataSourceUserAuth.loginMethod')}</Label>
        <Select
          value={userCredentialAuthType}
          onValueChange={(value) => {
            const next = value as DatabricksUserCredentialAuthType
            onUserCredentialAuthTypeChange(next)
            if (next === DATABRICKS_USER_AUTH_OAUTH2) {
              onOauth2ConfigChange((prev) => applyOidcUrlsFromHost(prev, host))
            }
          }}
          disabled={disabled}
        >
          <SelectTrigger className="h-8 text-sm w-full min-w-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={DATABRICKS_USER_AUTH_PAT}>
              {t('components.dataSourceUserAuth.databricksPat')}
            </SelectItem>
            <SelectItem value={DATABRICKS_USER_AUTH_OAUTH2}>
              {t('components.dataSourceUserAuth.databricksOauth')}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {showOauthApp ? (
        <div className="space-y-2.5">
          <p className={`text-xs text-muted-foreground leading-relaxed ${dsFormValueColumnInsetClass}`}>
            {t('components.dataSourceUserAuth.oauthAppHelp')}
          </p>
          <DataSourceDatabricksOAuthForm
            host={host}
            oauth2Config={oauth2Config}
            onOauth2ConfigChange={onOauth2ConfigChange}
            oauthClientSecret={oauthClientSecret}
            maskedClientSecret={maskedClientSecret}
            disabled={disabled}
            fieldErrors={fieldErrors}
            onClearFieldError={onClearFieldError}
          />
        </div>
      ) : null}
    </div>
  )
}