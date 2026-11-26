import i18n from '@/i18n/config'
import type { OAuth2FormConfig } from '@/components/api-connector/types'
import OAuthScopeChipField from '@/components/data-source/OAuthScopeChipField'
import {
  dsFieldLabelClass,
  dsFieldRowClass,
  dsFieldRowStartClass,
} from '@/components/data-source/formLayout'
import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import { SUGGESTED_DATABRICKS_OAUTH_SCOPES } from '@/lib/dataSourceUserAuth'
import { getDefaultIntegrationOAuthRedirectUri } from '@/lib/integrationOAuth'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      dataSourceDatabricksOAuth: {
        clientId: 'Client ID',
        clientSecret: 'Client secret',
        redirectUri: 'Redirect URI',
        redirectHelp:
          'Register this callback URL in your Databricks OAuth app (must match this deployment).',
        derivedHeading: 'OIDC endpoints',
        derivedHelp:
          'Authorize and token URLs are built from the workspace URL in the Server section. Change them only under Advanced if paths differ.',
        derivedMissingHost: 'Enter the workspace URL in the Server section first.',
        authorizeUrl: 'Authorize URL',
        tokenUrl: 'Token URL',
        scopesHelp: 'Must match scopes assigned to your Databricks OAuth app.',
        scopeExplicitPlaceholder: 'sql:read:restricted-query',
        overrideEndpoints: 'Override OIDC URLs',
        scopes: 'Authorize scopes',
        showAdvanced: 'Advanced OAuth settings',
        hideAdvanced: 'Hide advanced settings',
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
      dataSourceDatabricksOAuth: {
        clientId: '客户端 ID',
        clientSecret: '客户端密钥',
        redirectUri: '回调地址',
        redirectHelp: '在 Databricks OAuth 应用中注册此回调地址（须与本环境一致）。',
        derivedHeading: 'OIDC 端点',
        derivedHelp: '授权与令牌地址来自上方服务器的工作区 URL；路径不同时可在高级设置中覆盖。',
        derivedMissingHost: '请先在服务器分区填写工作区 URL。',
        authorizeUrl: '授权地址',
        tokenUrl: '令牌地址',
        scopesHelp: '须与 Databricks OAuth 应用上分配的 scopes 一致。',
        scopeExplicitPlaceholder: 'sql:read:restricted-query',
        overrideEndpoints: '覆盖 OIDC 地址',
        scopes: '授权 scopes',
        showAdvanced: '高级 OAuth 设置',
        hideAdvanced: '收起高级设置',
      },
    },
  },
  true,
  true,
)

export type DataSourceDatabricksOAuthFieldErrors = Partial<{
  oauthClientId: string
  oauthClientSecret: string
  oauthAuthorizeUrl: string
  oauthTokenUrl: string
  oauthScopes: string
}>

type DataSourceDatabricksOAuthFormProps = {
  host?: string
  oauth2Config: OAuth2FormConfig
  onOauth2ConfigChange: (updater: (prev: OAuth2FormConfig) => OAuth2FormConfig) => void
  oauthClientSecret: SecretCredentialFieldHandle
  maskedClientSecret?: string | null
  disabled?: boolean
  fieldErrors?: DataSourceDatabricksOAuthFieldErrors
  onClearFieldError?: (key: keyof DataSourceDatabricksOAuthFieldErrors) => void
}

export default function DataSourceDatabricksOAuthForm({
  host = '',
  oauth2Config,
  onOauth2ConfigChange,
  oauthClientSecret,
  maskedClientSecret,
  disabled = false,
  fieldErrors,
  onClearFieldError,
}: DataSourceDatabricksOAuthFormProps) {
  const { t } = useTranslation()
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const hostTrimmed = host.trim()
  return (
    <div className="space-y-2.5">
      <div className={dsFieldRowClass}>
        <Label htmlFor="ds-oauth-client-id" className={dsFieldLabelClass}>
          {t('components.dataSourceDatabricksOAuth.clientId')}{' '}
          <span className="text-destructive">*</span>
        </Label>
        <Input
          id="ds-oauth-client-id"
          value={oauth2Config.clientId}
          onChange={(event) => {
            onClearFieldError?.('oauthClientId')
            onOauth2ConfigChange((prev) => ({ ...prev, clientId: event.target.value }))
          }}
          disabled={disabled}
          className="h-8 text-sm w-full min-w-0"
          errorMsg={fieldErrors?.oauthClientId}
        />
      </div>

      <div className={dsFieldRowStartClass}>
        <Label htmlFor="ds-oauth-client-secret" className={`${dsFieldLabelClass} pt-2`}>
          {t('components.dataSourceDatabricksOAuth.clientSecret')}{' '}
          <span className="text-destructive">*</span>
        </Label>
        <SensitiveCredentialField
          id="ds-oauth-client-secret"
          hideLabel
          label={
            <>
              {t('components.dataSourceDatabricksOAuth.clientSecret')}{' '}
              <span className="text-destructive">*</span>
            </>
          }
          binding={oauthClientSecret}
          maskedPreview={maskedClientSecret}
          disabled={disabled}
          errorMsg={fieldErrors?.oauthClientSecret}
          onStartEdit={oauthClientSecret.startEdit}
          onCancelEdit={oauthClientSecret.cancelEdit}
          onDraftChange={(value) => {
            oauthClientSecret.setDraft(value)
            onClearFieldError?.('oauthClientSecret')
          }}
        />
      </div>

      <div className={dsFieldRowStartClass}>
        <Label htmlFor="ds-oauth-redirect" className={`${dsFieldLabelClass} pt-2`}>
          {t('components.dataSourceDatabricksOAuth.redirectUri')}
        </Label>
        <div className="min-w-0 space-y-1">
          <Input
            id="ds-oauth-redirect"
            value={oauth2Config.redirectUri}
            onChange={(event) =>
              onOauth2ConfigChange((prev) => ({ ...prev, redirectUri: event.target.value }))
            }
            disabled={disabled}
            className="h-8 w-full min-w-0 font-mono text-xs"
            placeholder={getDefaultIntegrationOAuthRedirectUri()}
          />
          <p className="text-xs text-muted-foreground leading-relaxed">
            {t('components.dataSourceDatabricksOAuth.redirectHelp')}
          </p>
        </div>
      </div>

      <div className={dsFieldRowStartClass}>
        <span className={`${dsFieldLabelClass} pt-1`}>{t('components.dataSourceDatabricksOAuth.derivedHeading')}</span>
        <p className="text-xs text-muted-foreground leading-relaxed min-w-0">
          {hostTrimmed
            ? t('components.dataSourceDatabricksOAuth.derivedHelp')
            : t('components.dataSourceDatabricksOAuth.derivedMissingHost')}
        </p>
      </div>
      {hostTrimmed ? (
        <>
          <div className={dsFieldRowClass}>
            <Label className={dsFieldLabelClass}>{t('components.dataSourceDatabricksOAuth.authorizeUrl')}</Label>
            <p className="min-w-0 break-all font-mono text-xs text-foreground/90 py-1.5">
              {oauth2Config.authorizeUrl || '—'}
            </p>
          </div>
          <div className={dsFieldRowClass}>
            <Label className={dsFieldLabelClass}>{t('components.dataSourceDatabricksOAuth.tokenUrl')}</Label>
            <p className="min-w-0 break-all font-mono text-xs text-foreground/90 py-1.5">
              {oauth2Config.tokenUrl || '—'}
            </p>
          </div>
        </>
      ) : null}

      <div className={dsFieldRowStartClass}>
        <Label htmlFor="ds-oauth-scopes-text" className={`${dsFieldLabelClass} pt-1.5`}>
          {t('components.dataSourceDatabricksOAuth.scopes')}{' '}
          <span className="text-destructive">*</span>
        </Label>
        <div className="min-w-0 space-y-1">
          <OAuthScopeChipField
            id="ds-oauth-scopes-text"
            scopes={oauth2Config.scopes}
            suggestions={SUGGESTED_DATABRICKS_OAUTH_SCOPES}
            disabled={disabled}
            errorMsg={fieldErrors?.oauthScopes}
            placeholder={t('components.dataSourceDatabricksOAuth.scopeExplicitPlaceholder')}
            onFocusInput={() => onClearFieldError?.('oauthScopes')}
            onChange={(scopes) => {
              onClearFieldError?.('oauthScopes')
              onOauth2ConfigChange((prev) => ({ ...prev, scopes }))
            }}
          />
          <p className="text-xs text-muted-foreground leading-relaxed">
            {t('components.dataSourceDatabricksOAuth.scopesHelp')}
          </p>
        </div>
      </div>

      <div className={dsFieldRowStartClass}>
        <span className={dsFieldLabelClass} />
        <AdvancedToggle
          advancedOpen={advancedOpen}
          disabled={disabled}
          onToggle={() => setAdvancedOpen((open) => !open)}
        />
      </div>

      {advancedOpen ? (
        <div className="space-y-2.5 border-t border-dashed border-border/70 pt-2.5">
          <div className={dsFieldRowStartClass}>
            <span className={`${dsFieldLabelClass} pt-0.5`}>
              {t('components.dataSourceDatabricksOAuth.overrideEndpoints')}
            </span>
            <p className="text-xs text-muted-foreground min-w-0">
              {t('components.dataSourceDatabricksOAuth.derivedHelp')}
            </p>
          </div>
          <div className={dsFieldRowClass}>
            <Label htmlFor="ds-oauth-authorize" className={dsFieldLabelClass}>
              {t('components.dataSourceDatabricksOAuth.authorizeUrl')}
            </Label>
            <Input
              id="ds-oauth-authorize"
              value={oauth2Config.authorizeUrl}
              onChange={(event) => {
                onClearFieldError?.('oauthAuthorizeUrl')
                onOauth2ConfigChange((prev) => ({ ...prev, authorizeUrl: event.target.value }))
              }}
              disabled={disabled}
              className="h-8 w-full min-w-0 font-mono text-xs"
              errorMsg={fieldErrors?.oauthAuthorizeUrl}
            />
          </div>
          <div className={dsFieldRowClass}>
            <Label htmlFor="ds-oauth-token" className={dsFieldLabelClass}>
              {t('components.dataSourceDatabricksOAuth.tokenUrl')}
            </Label>
            <Input
              id="ds-oauth-token"
              value={oauth2Config.tokenUrl}
              onChange={(event) => {
                onClearFieldError?.('oauthTokenUrl')
                onOauth2ConfigChange((prev) => ({ ...prev, tokenUrl: event.target.value }))
              }}
              disabled={disabled}
              className="h-8 w-full min-w-0 font-mono text-xs"
              errorMsg={fieldErrors?.oauthTokenUrl}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}

function AdvancedToggle({
  advancedOpen,
  disabled,
  onToggle,
}: {
  advancedOpen: boolean
  disabled?: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      disabled={disabled}
      className="h-8 px-2 text-xs text-muted-foreground hover:text-foreground"
      onClick={onToggle}
    >
      {advancedOpen ? (
        <ChevronUp className="mr-1 h-3.5 w-3.5" aria-hidden />
      ) : (
        <ChevronDown className="mr-1 h-3.5 w-3.5" aria-hidden />
      )}
      {advancedOpen
        ? t('components.dataSourceDatabricksOAuth.hideAdvanced')
        : t('components.dataSourceDatabricksOAuth.showAdvanced')}
    </Button>
  )
}