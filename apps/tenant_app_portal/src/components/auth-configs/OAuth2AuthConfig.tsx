import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import { getDefaultIntegrationOAuthRedirectUri } from '@/lib/integrationOAuth'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      authConfigs: {
        oauthClientId: 'OAuth client ID',
        oauthClientSecret: 'OAuth client secret',
        oauthRedirectUri: 'OAuth redirect URI',
        oauthRedirectHelp:
          'Pre-filled with this deployment\'s API callback. Register the same URL in your OAuth app; change only if the API is reached via a different public URL.',
        oauthAuthorizeUrl: 'Authorize URL',
        oauthTokenUrl: 'Token URL',
        oauthScopes: 'Scopes',
        oauthScopesHelp: 'Space- or comma-separated scopes requested at authorize time.',
        oauthScopeParam: 'Scope query param',
        oauthTokenAuthMethod: 'Token auth method',
        oauthTokenResponsePath: 'Token response path',
        oauthTokenResponsePathHelp:
          'Optional nested path to the token object (e.g. authed_user for Slack user tokens).',
        oauthPackEndpoints: 'Pack endpoints',
        oauthUserModeHint: 'OAuth2 connectors always use per-user (BYOT) credentials.',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    components: {
      authConfigs: {
        oauthClientId: 'OAuth 客户端 ID',
        oauthClientSecret: 'OAuth 客户端密钥',
        oauthRedirectUri: 'OAuth 回调地址',
        oauthRedirectHelp:
          '已预填当前环境的 API 回调地址。请在 OAuth 应用中注册相同 URL；仅当 API 通过其他公网地址访问时再修改。',
        oauthAuthorizeUrl: '授权地址',
        oauthTokenUrl: '令牌地址',
        oauthScopes: 'Scopes',
        oauthScopesHelp: '授权时请求的 scope，可用空格或逗号分隔。',
        oauthScopeParam: 'Scope 查询参数名',
        oauthTokenAuthMethod: '令牌鉴权方式',
        oauthTokenResponsePath: '令牌响应路径',
        oauthTokenResponsePathHelp: '可选嵌套路径（例如 Slack 用户令牌用 authed_user）。',
        oauthPackEndpoints: '模板端点',
        oauthUserModeHint: 'OAuth2 连接器固定使用按用户（BYOT）凭证。',
      },
    },
  },
  true,
  true
)

export interface OAuth2AuthConfigProps {
  clientId: string
  redirectUri: string
  clientSecret: SecretCredentialFieldHandle
  maskedClientSecret?: string | null
  authorizeUrl: string
  tokenUrl: string
  scopesText: string
  scopeParam: string
  tokenAuthMethod: string
  tokenResponsePath: string
  /** When true, authorize/token (and related pack fields) are read-only. */
  endpointsLocked?: boolean
  submitting: boolean
  clientIdError?: string
  authorizeUrlError?: string
  tokenUrlError?: string
  clientSecretError?: string
  onClientIdChange: (value: string) => void
  onRedirectUriChange: (value: string) => void
  onClientSecretDraftChange?: (value: string) => void
  onAuthorizeUrlChange: (value: string) => void
  onTokenUrlChange: (value: string) => void
  onScopesTextChange: (value: string) => void
  onScopeParamChange: (value: string) => void
  onTokenAuthMethodChange: (value: string) => void
  onTokenResponsePathChange: (value: string) => void
}

export function OAuth2AuthConfig({
  clientId,
  redirectUri,
  clientSecret,
  maskedClientSecret,
  authorizeUrl,
  tokenUrl,
  scopesText,
  scopeParam,
  tokenAuthMethod,
  tokenResponsePath,
  endpointsLocked = false,
  submitting,
  clientIdError,
  authorizeUrlError,
  tokenUrlError,
  clientSecretError,
  onClientIdChange,
  onRedirectUriChange,
  onClientSecretDraftChange,
  onAuthorizeUrlChange,
  onTokenUrlChange,
  onScopesTextChange,
  onScopeParamChange,
  onTokenAuthMethodChange,
  onTokenResponsePathChange,
}: OAuth2AuthConfigProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {t('components.authConfigs.oauthUserModeHint')}
      </p>

      <div className="space-y-1">
        <Label htmlFor="oauth2-client-id">{t('components.authConfigs.oauthClientId')}</Label>
        <Input
          id="oauth2-client-id"
          value={clientId}
          onChange={(event) => onClientIdChange(event.target.value)}
          disabled={submitting}
          errorMsg={clientIdError}
        />
      </div>
      <SensitiveCredentialField
        id="oauth2-client-secret"
        label={t('components.authConfigs.oauthClientSecret')}
        binding={clientSecret}
        maskedPreview={maskedClientSecret}
        disabled={submitting}
        errorMsg={clientSecretError}
        onStartEdit={clientSecret.startEdit}
        onCancelEdit={clientSecret.cancelEdit}
        onDraftChange={onClientSecretDraftChange ?? clientSecret.setDraft}
      />
      <div className="space-y-1">
        <Label htmlFor="oauth2-redirect-uri">{t('components.authConfigs.oauthRedirectUri')}</Label>
        <Input
          id="oauth2-redirect-uri"
          value={redirectUri}
          onChange={(event) => onRedirectUriChange(event.target.value)}
          disabled={submitting}
          placeholder={getDefaultIntegrationOAuthRedirectUri()}
        />
        <p className="text-xs text-muted-foreground">
          {t('components.authConfigs.oauthRedirectHelp')}
        </p>
      </div>

      {endpointsLocked ? (
        <dl className="space-y-1 text-xs text-muted-foreground">
          <div className="font-medium text-foreground/80">
            {t('components.authConfigs.oauthPackEndpoints')}
          </div>
          {authorizeUrl ? (
            <div className="grid gap-0.5 sm:grid-cols-[7rem_1fr]">
              <dt>{t('components.authConfigs.oauthAuthorizeUrl')}</dt>
              <dd className="break-all font-mono">{authorizeUrl}</dd>
            </div>
          ) : null}
          {tokenUrl ? (
            <div className="grid gap-0.5 sm:grid-cols-[7rem_1fr]">
              <dt>{t('components.authConfigs.oauthTokenUrl')}</dt>
              <dd className="break-all font-mono">{tokenUrl}</dd>
            </div>
          ) : null}
          {scopesText ? (
            <div className="grid gap-0.5 sm:grid-cols-[7rem_1fr]">
              <dt>{t('components.authConfigs.oauthScopes')}</dt>
              <dd className="break-all font-mono">{scopesText}</dd>
            </div>
          ) : null}
        </dl>
      ) : (
        <>
          <div className="space-y-1">
            <Label htmlFor="oauth2-authorize-url">
              {t('components.authConfigs.oauthAuthorizeUrl')}
            </Label>
            <Input
              id="oauth2-authorize-url"
              value={authorizeUrl}
              onChange={(event) => onAuthorizeUrlChange(event.target.value)}
              disabled={submitting}
              placeholder="https://provider.example/oauth/authorize"
              errorMsg={authorizeUrlError}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="oauth2-token-url">{t('components.authConfigs.oauthTokenUrl')}</Label>
            <Input
              id="oauth2-token-url"
              value={tokenUrl}
              onChange={(event) => onTokenUrlChange(event.target.value)}
              disabled={submitting}
              placeholder="https://provider.example/oauth/token"
              errorMsg={tokenUrlError}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="oauth2-scopes">{t('components.authConfigs.oauthScopes')}</Label>
            <Input
              id="oauth2-scopes"
              value={scopesText}
              onChange={(event) => onScopesTextChange(event.target.value)}
              disabled={submitting}
              placeholder="search:read channels:history"
            />
            <p className="text-xs text-muted-foreground">
              {t('components.authConfigs.oauthScopesHelp')}
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="oauth2-scope-param">
                {t('components.authConfigs.oauthScopeParam')}
              </Label>
              <Input
                id="oauth2-scope-param"
                value={scopeParam}
                onChange={(event) => onScopeParamChange(event.target.value)}
                disabled={submitting}
                placeholder="scope"
              />
            </div>
            <div className="space-y-1">
              <Label>{t('components.authConfigs.oauthTokenAuthMethod')}</Label>
              <Select
                value={tokenAuthMethod}
                onValueChange={onTokenAuthMethodChange}
                disabled={submitting}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="client_secret_post">client_secret_post</SelectItem>
                  <SelectItem value="client_secret_basic">client_secret_basic</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="oauth2-token-response-path">
              {t('components.authConfigs.oauthTokenResponsePath')}
            </Label>
            <Input
              id="oauth2-token-response-path"
              value={tokenResponsePath}
              onChange={(event) => onTokenResponsePathChange(event.target.value)}
              disabled={submitting}
              placeholder="authed_user"
            />
            <p className="text-xs text-muted-foreground">
              {t('components.authConfigs.oauthTokenResponsePathHelp')}
            </p>
          </div>
        </>
      )}
    </div>
  )
}
