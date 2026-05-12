import api from './api'

export type FirstLoginPolicy = 'jit_create' | 'pending_approval' | 'reject_unknown'
export type ProviderType = 'oidc'

export interface ProviderConfig {
  client_id: string
  client_secret?: string
  issuer: string
  scopes?: string[]
  extra_authorize_params?: Record<string, string>
  authorize_endpoint?: string | null
  token_endpoint?: string | null
  userinfo_endpoint?: string | null
  jwks_uri?: string | null
}

export interface ProviderConfigResponse {
  client_id: string
  client_secret_configured: boolean
  issuer: string
  scopes: string[]
  extra_authorize_params: Record<string, string>
  authorize_endpoint: string | null
  token_endpoint: string | null
  userinfo_endpoint: string | null
  jwks_uri: string | null
}

export interface AuthProvider {
  id: number
  tenant_id: number
  provider_type: ProviderType
  display_name: string
  enabled: boolean
  config: ProviderConfigResponse
  first_login_policy: FirstLoginPolicy
  callback_url: string
}

export interface CreateAuthProviderRequest {
  display_name: string
  provider_type?: ProviderType
  enabled?: boolean
  config: ProviderConfig
  first_login_policy?: FirstLoginPolicy
}

export interface UpdateAuthProviderRequest {
  display_name?: string
  enabled?: boolean
  config?: ProviderConfig
  first_login_policy?: FirstLoginPolicy
}

export interface LoginMethod {
  type: string
  provider_id?: number | null
  display_name?: string | null
  issuer?: string | null
}

export interface ResolveTenantMethodsResponse {
  tenant_id: number
  tenant_name: string
  tenant_slug: string
  login_methods: LoginMethod[]
  force_sso: boolean
  emergency_password_available: boolean
}

export interface SsoStartResponse {
  authorize_url: string
}

export interface SsoExchangeResponse {
  access_token: string
  token_type: string
  user_id: number
  username: string
  role: string
  tenant_id: number
  tenant_name: string
}

// Re-export identity admin types and APIs (deprecated paths in ssoApi)
export type {
  IdentitySource,
  IdentitySettings as SsoSettings,
  LoginDomain,
  PendingIdentity,
} from './identityApi'
export {
  listIdentitySources,
  updateIdentitySourceBindPolicy,
  listLoginDomains,
  addLoginDomains,
  removeLoginDomain,
  getIdentitySettings as getSsoSettings,
  updateIdentitySettings as updateSsoSettings,
  setUserBreakGlass,
  listPendingIdentities,
  approvePendingIdentity,
  rejectPendingIdentity,
} from './identityApi'

// ============ Provider CRUD ============

export async function listAuthProviders(): Promise<AuthProvider[]> {
  const res = await api.get<AuthProvider[]>('/tenants/auth-providers')
  return res.data
}

export async function createAuthProvider(payload: CreateAuthProviderRequest): Promise<AuthProvider> {
  const res = await api.post<AuthProvider>('/tenants/auth-providers', payload)
  return res.data
}

export async function updateAuthProvider(
  id: number,
  payload: UpdateAuthProviderRequest
): Promise<AuthProvider> {
  const res = await api.put<AuthProvider>(`/tenants/auth-providers/${id}`, payload)
  return res.data
}

export async function deleteAuthProvider(id: number): Promise<void> {
  await api.delete(`/tenants/auth-providers/${id}`)
}

export async function enableAuthProvider(id: number): Promise<AuthProvider> {
  const res = await api.post<AuthProvider>(`/tenants/auth-providers/${id}/enable`)
  return res.data
}

export async function disableAuthProvider(id: number): Promise<AuthProvider> {
  const res = await api.post<AuthProvider>(`/tenants/auth-providers/${id}/disable`)
  return res.data
}

// ============ Public login flow ============

export async function resolveTenantMethods(identifier: string): Promise<ResolveTenantMethodsResponse> {
  const res = await api.post<ResolveTenantMethodsResponse>('/auth/resolve-tenant-methods', { identifier })
  return res.data
}

export async function ssoStart(tenantId: number, providerId: number): Promise<SsoStartResponse> {
  const res = await api.get<SsoStartResponse>(`/auth/sso/${providerId}/start`, {
    params: { tenant_id: tenantId },
  })
  return res.data
}

export async function ssoExchange(ticket: string): Promise<SsoExchangeResponse> {
  const res = await api.post<SsoExchangeResponse>('/auth/sso/exchange', { ticket })
  return res.data
}
