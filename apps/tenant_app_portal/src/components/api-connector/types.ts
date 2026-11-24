import {
  getDefaultApiConnectorOAuthRedirectUri,
  type ApiConnector,
  type ApiConnectorAuthType,
  type ApiConnectorCreateRequest,
  type ApiConnectorSchemaSourceType,
  type ApiConnectorUpdateRequest,
} from '@/lib/apiConnectorApi'

export interface ApiConnectorFormDialogProps {
  open: boolean
  submitting?: boolean
  connector?: ApiConnector | null
  onOpenChange: (open: boolean) => void
  onCreate?: (payload: ApiConnectorCreateRequest) => Promise<ApiConnector>
  onUpdate?: (connectorId: number, payload: ApiConnectorUpdateRequest) => Promise<ApiConnector>
  onCreated?: (connector: ApiConnector) => void
  onUpdated?: (connector: ApiConnector) => void
}

export interface ApiKeyConfig {
  keyName: string
  keyValue: string
}

export interface BasicConfig {
  username: string
}

export interface CustomAuthFormConfig {
  loginEndpoint: string
  loginMethod: string
  loginPayloadTemplate: string
  tokenExtraction: string
  requestHeaders: string
  extraConfig: string
}

export interface OAuth2FormConfig {
  clientId: string
  redirectUri: string
  authorizeUrl: string
  tokenUrl: string
  scopes: string[]
  scopeParam: string
  tokenAuthMethod: string
  tokenResponsePath: string
}

export type FieldErrorKey =
  | 'name'
  | 'baseUrl'
  | 'apiKeyValue'
  | 'bearerToken'
  | 'basicUsername'
  | 'basicPassword'
  | 'loginEndpoint'
  | 'loginPayloadTemplate'
  | 'tokenExtraction'
  | 'requestHeaders'
  | 'extraConfig'
  | 'schemaSourceUrl'
  | 'oauthClientId'
  | 'oauthAuthorizeUrl'
  | 'oauthTokenUrl'
  | 'oauthClientSecret'

export const defaultApiKeyConfig: ApiKeyConfig = {
  keyName: 'X-API-Key',
  keyValue: '',
}

export const defaultBasicConfig: BasicConfig = {
  username: '',
}

export const defaultCustomAuthConfig: CustomAuthFormConfig = {
  loginEndpoint: '',
  loginMethod: 'POST',
  loginPayloadTemplate: '{}',
  tokenExtraction: '{}',
  requestHeaders: '{}',
  extraConfig: '{}',
}

export const defaultOAuth2Config: OAuth2FormConfig = {
  clientId: '',
  redirectUri: '',
  authorizeUrl: '',
  tokenUrl: '',
  scopes: [],
  scopeParam: 'scope',
  tokenAuthMethod: 'client_secret_post',
  tokenResponsePath: '',
}

export function createDefaultOAuth2Config(): OAuth2FormConfig {
  return {
    ...defaultOAuth2Config,
    redirectUri: getDefaultApiConnectorOAuthRedirectUri(),
  }
}

export function scopesToText(scopes: string[]): string {
  return scopes.join(' ')
}

export function textToScopes(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((scope) => scope.trim())
    .filter(Boolean)
}

export type { ApiConnectorAuthType, ApiConnectorSchemaSourceType }
