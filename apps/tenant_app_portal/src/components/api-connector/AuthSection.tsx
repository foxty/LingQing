import { useTranslation } from 'react-i18next'
import {
  ApiKeyAuthConfig,
  BasicAuthConfig,
  BearerAuthConfig,
  CustomAuthConfig,
  OAuth2AuthConfig,
} from '@/components/auth-configs'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import type {
  ApiConnectorAuthType,
  ApiKeyConfig,
  BasicConfig,
  CustomAuthFormConfig,
  FieldErrorKey,
  OAuth2FormConfig,
} from '@/components/api-connector/types'

interface AuthSectionProps {
  submitting: boolean
  packLocked: boolean
  isAuthConfigured: boolean
  authType: ApiConnectorAuthType
  maskedAuth: Record<string, unknown>
  apiKeyConfig: ApiKeyConfig
  basicConfig: BasicConfig
  customAuthConfig: CustomAuthFormConfig
  oauth2Config: OAuth2FormConfig
  oauthScopeSuggestions: readonly string[]
  fieldErrors: Partial<Record<FieldErrorKey, string>>
  apiKeyValueSecret: SecretCredentialFieldHandle
  bearerSecret: SecretCredentialFieldHandle
  basicPasswordSecret: SecretCredentialFieldHandle
  oauthClientSecret: SecretCredentialFieldHandle
  onAuthTypeChange: (value: ApiConnectorAuthType) => void
  onApiKeyConfigChange: (updater: (prev: ApiKeyConfig) => ApiKeyConfig) => void
  onBasicConfigChange: (updater: (prev: BasicConfig) => BasicConfig) => void
  onCustomAuthConfigChange: (next: CustomAuthFormConfig) => void
  onOauth2ConfigChange: (updater: (prev: OAuth2FormConfig) => OAuth2FormConfig) => void
  clearFieldError: (key: FieldErrorKey) => void
}

export function AuthSection({
  submitting,
  packLocked,
  isAuthConfigured,
  authType,
  maskedAuth,
  apiKeyConfig,
  basicConfig,
  customAuthConfig,
  oauth2Config,
  oauthScopeSuggestions,
  fieldErrors,
  apiKeyValueSecret,
  bearerSecret,
  basicPasswordSecret,
  oauthClientSecret,
  onAuthTypeChange,
  onApiKeyConfigChange,
  onBasicConfigChange,
  onCustomAuthConfigChange,
  onOauth2ConfigChange,
  clearFieldError,
}: AuthSectionProps) {
  const { t } = useTranslation()

  return (
    <section className="space-y-3 py-4">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold tracking-tight">
          {t('components.addApiConnectorDialog.authConfig')}
        </h3>
        {isAuthConfigured ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-xs font-medium text-success ring-1 ring-inset ring-success/20">
            ✓ {t('components.addApiConnectorDialog.configured')}
          </span>
        ) : null}
      </div>
      <div className="space-y-3 border-l-2 border-border pl-3">
        <div className="space-y-1">
          <Label>{t('components.addApiConnectorDialog.authType')}</Label>
          {packLocked ? (
            <p className="text-sm text-muted-foreground">{authType}</p>
          ) : (
            <Select
              value={authType}
              onValueChange={(value) => onAuthTypeChange(value as ApiConnectorAuthType)}
              disabled={submitting}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">none</SelectItem>
                <SelectItem value="api_key">api_key</SelectItem>
                <SelectItem value="bearer">bearer</SelectItem>
                <SelectItem value="basic">basic</SelectItem>
                <SelectItem value="custom">custom (session-based)</SelectItem>
                <SelectItem value="oauth2">oauth2</SelectItem>
              </SelectContent>
            </Select>
          )}
        </div>

        {authType === 'api_key' ? (
          <ApiKeyAuthConfig
            keyName={apiKeyConfig.keyName}
            keyValueSecret={apiKeyValueSecret}
            maskedPreview={
              typeof maskedAuth.key_value === 'string'
                ? maskedAuth.key_value
                : typeof maskedAuth.api_key === 'string'
                  ? maskedAuth.api_key
                  : null
            }
            submitting={submitting}
            keyValueError={fieldErrors.apiKeyValue}
            onKeyNameChange={(value) =>
              onApiKeyConfigChange((prev) => ({ ...prev, keyName: value }))
            }
            onKeyValueDraftChange={(value) => {
              apiKeyValueSecret.setDraft(value)
              clearFieldError('apiKeyValue')
            }}
          />
        ) : null}

        {authType === 'bearer' ? (
          <BearerAuthConfig
            secret={bearerSecret}
            maskedPreview={typeof maskedAuth.token === 'string' ? maskedAuth.token : null}
            submitting={submitting}
            tokenError={fieldErrors.bearerToken}
            onDraftChange={(value) => {
              bearerSecret.setDraft(value)
              clearFieldError('bearerToken')
            }}
          />
        ) : null}

        {authType === 'basic' ? (
          <BasicAuthConfig
            username={basicConfig.username}
            passwordSecret={basicPasswordSecret}
            maskedPreview={typeof maskedAuth.password === 'string' ? maskedAuth.password : null}
            submitting={submitting}
            usernameError={fieldErrors.basicUsername}
            passwordError={fieldErrors.basicPassword}
            onUsernameChange={(value) => {
              clearFieldError('basicUsername')
              onBasicConfigChange((prev) => ({ ...prev, username: value }))
            }}
            onPasswordDraftChange={(value) => {
              basicPasswordSecret.setDraft(value)
              clearFieldError('basicPassword')
            }}
          />
        ) : null}

        {authType === 'oauth2' ? (
          <OAuth2AuthConfig
            clientId={oauth2Config.clientId}
            redirectUri={oauth2Config.redirectUri}
            clientSecret={oauthClientSecret}
            maskedClientSecret={
              typeof maskedAuth.client_secret === 'string' ? maskedAuth.client_secret : null
            }
            authorizeUrl={oauth2Config.authorizeUrl}
            tokenUrl={oauth2Config.tokenUrl}
            scopes={oauth2Config.scopes}
            scopeSuggestions={oauthScopeSuggestions}
            scopeParam={oauth2Config.scopeParam}
            tokenAuthMethod={oauth2Config.tokenAuthMethod}
            tokenResponsePath={oauth2Config.tokenResponsePath}
            endpointsLocked={packLocked}
            submitting={submitting}
            clientIdError={fieldErrors.oauthClientId}
            authorizeUrlError={fieldErrors.oauthAuthorizeUrl}
            tokenUrlError={fieldErrors.oauthTokenUrl}
            clientSecretError={fieldErrors.oauthClientSecret}
            onClientIdChange={(value) => {
              clearFieldError('oauthClientId')
              onOauth2ConfigChange((prev) => ({ ...prev, clientId: value }))
            }}
            onRedirectUriChange={(value) =>
              onOauth2ConfigChange((prev) => ({ ...prev, redirectUri: value }))
            }
            onClientSecretDraftChange={(value) => {
              oauthClientSecret.setDraft(value)
              clearFieldError('oauthClientSecret')
            }}
            onAuthorizeUrlChange={(value) => {
              clearFieldError('oauthAuthorizeUrl')
              onOauth2ConfigChange((prev) => ({ ...prev, authorizeUrl: value }))
            }}
            onTokenUrlChange={(value) => {
              clearFieldError('oauthTokenUrl')
              onOauth2ConfigChange((prev) => ({ ...prev, tokenUrl: value }))
            }}
            onScopesChange={(nextScopes) =>
              onOauth2ConfigChange((prev) => ({ ...prev, scopes: nextScopes }))
            }
            onScopeParamChange={(value) =>
              onOauth2ConfigChange((prev) => ({ ...prev, scopeParam: value }))
            }
            onTokenAuthMethodChange={(value) =>
              onOauth2ConfigChange((prev) => ({ ...prev, tokenAuthMethod: value }))
            }
            onTokenResponsePathChange={(value) =>
              onOauth2ConfigChange((prev) => ({ ...prev, tokenResponsePath: value }))
            }
          />
        ) : null}

        {authType === 'custom' ? (
          <CustomAuthConfig
            config={customAuthConfig}
            submitting={submitting}
            fieldErrors={{
              loginEndpoint: fieldErrors.loginEndpoint,
              loginPayloadTemplate: fieldErrors.loginPayloadTemplate,
              tokenExtraction: fieldErrors.tokenExtraction,
              requestHeaders: fieldErrors.requestHeaders,
              extraConfig: fieldErrors.extraConfig,
            }}
            onChange={(next) => {
              onCustomAuthConfigChange(next)
              ;(
                [
                  'loginEndpoint',
                  'loginPayloadTemplate',
                  'tokenExtraction',
                  'requestHeaders',
                  'extraConfig',
                ] as const
              ).forEach((key) => clearFieldError(key))
            }}
          />
        ) : null}
      </div>
    </section>
  )
}
