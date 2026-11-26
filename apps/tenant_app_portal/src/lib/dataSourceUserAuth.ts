import type { SecretFieldBinding } from '@/lib/sensitiveCredential'
import { applyNestedSecretKey } from '@/lib/sensitiveCredential'
import { createDefaultOAuth2Config, textToScopes, type OAuth2FormConfig } from '@/components/api-connector/types'

export const DATABRICKS_USER_AUTH_PAT = 'pat'
export const DATABRICKS_USER_AUTH_OAUTH2 = 'oauth2'

export type DatabricksUserCredentialAuthType = typeof DATABRICKS_USER_AUTH_PAT | typeof DATABRICKS_USER_AUTH_OAUTH2

/** Suggested authorize scopes (must match the Databricks OAuth app assignment). */
export const SUGGESTED_DATABRICKS_OAUTH_SCOPES = [
  'sql',
  'offline_access',
  'sql:read:restricted-query',
  'sql:restricted-query',
] as const

/** Merge workspace OIDC URLs into OAuth form state (shown in UI and saved on submit). */
export function applyOidcUrlsFromHost(config: OAuth2FormConfig, host: string): OAuth2FormConfig {
  const { authorizeUrl, tokenUrl } = databricksOidcUrls(host)
  if (!authorizeUrl && !tokenUrl) {
    return config
  }
  return {
    ...config,
    authorizeUrl,
    tokenUrl,
  }
}

export function databricksOidcUrls(host: string): { authorizeUrl: string; tokenUrl: string } {
  const trimmed = host.trim()
  if (!trimmed) {
    return { authorizeUrl: '', tokenUrl: '' }
  }
  const base = trimmed.startsWith('http://') || trimmed.startsWith('https://')
    ? trimmed.replace(/\/$/, '')
    : `https://${trimmed.replace(/\/$/, '')}`
  return {
    authorizeUrl: `${base}/oidc/v1/authorize`,
    tokenUrl: `${base}/oidc/v1/token`,
  }
}

export function defaultDatabricksOAuth2Config(host?: string): OAuth2FormConfig {
  const urls = databricksOidcUrls(host ?? '')
  return {
    clientId: '',
    redirectUri: '',
    authorizeUrl: urls.authorizeUrl,
    tokenUrl: urls.tokenUrl,
    scopes: [],
    scopeParam: 'scope',
    tokenAuthMethod: 'client_secret_post',
    tokenResponsePath: '',
  }
}

export function oauth2ConfigFromDataSourceConfig(
  config: Record<string, unknown> | undefined,
  host?: string,
): OAuth2FormConfig {
  const defaults = {
    ...defaultDatabricksOAuth2Config(host),
    redirectUri: createDefaultOAuth2Config().redirectUri,
  }
  const block = config?.user_oauth
  if (!block || typeof block !== 'object') {
    return defaults
  }
  const raw = block as Record<string, unknown>
  const scopes = Array.isArray(raw.scopes) ? raw.scopes.map(String).filter(Boolean) : []
  return {
    clientId: typeof raw.client_id === 'string' ? raw.client_id : '',
    redirectUri:
      typeof raw.redirect_uri === 'string' && raw.redirect_uri.trim()
        ? raw.redirect_uri
        : createDefaultOAuth2Config().redirectUri,
    authorizeUrl: typeof raw.authorize_url === 'string' && raw.authorize_url.trim()
      ? raw.authorize_url
      : defaults.authorizeUrl,
    tokenUrl: typeof raw.token_url === 'string' && raw.token_url.trim() ? raw.token_url : defaults.tokenUrl,
    scopes,
    scopeParam: typeof raw.scope_param === 'string' && raw.scope_param.trim() ? raw.scope_param : 'scope',
    tokenAuthMethod:
      typeof raw.token_auth_method === 'string' && raw.token_auth_method.trim()
        ? raw.token_auth_method
        : 'client_secret_post',
    tokenResponsePath:
      typeof raw.token_response_path === 'string' ? raw.token_response_path : '',
  }
}

export function attachDatabricksUserCredentialAuth(
  config: Record<string, unknown>,
  options: {
    userCredentialAuthType: DatabricksUserCredentialAuthType
    oauth2Config: OAuth2FormConfig
    clientSecret: SecretFieldBinding
  },
): Record<string, unknown> {
  const next: Record<string, unknown> = {
    ...config,
    user_credential_auth_type: options.userCredentialAuthType,
  }
  if (options.userCredentialAuthType !== DATABRICKS_USER_AUTH_OAUTH2) {
    return next
  }
  const block: Record<string, unknown> = {
    client_id: options.oauth2Config.clientId.trim(),
    scope_param: options.oauth2Config.scopeParam.trim() || 'scope',
    token_auth_method: options.oauth2Config.tokenAuthMethod || 'client_secret_post',
    scopes: textToScopes(options.oauth2Config.scopes.join(' ')),
  }
  const authorize = options.oauth2Config.authorizeUrl.trim()
  const tokenUrl = options.oauth2Config.tokenUrl.trim()
  if (authorize) {
    block.authorize_url = authorize
  }
  if (tokenUrl) {
    block.token_url = tokenUrl
  }
  const redirect = options.oauth2Config.redirectUri.trim()
  if (redirect) {
    block.redirect_uri = redirect
  }
  const tokenPath = options.oauth2Config.tokenResponsePath.trim()
  if (tokenPath) {
    block.token_response_path = tokenPath
  }
  const merged = { ...next, user_oauth: block }
  return applyNestedSecretKey(merged, 'user_oauth', 'client_secret', options.clientSecret) as Record<
    string,
    unknown
  >
}