import api from './api'
import type { FirstLoginPolicy } from './ssoApi'

export interface LoginDomain {
  id: number
  tenant_id: number
  domain: string
}

export interface IdentitySettings {
  force_sso: boolean
  break_glass_admin_count: number
}

export interface IdentitySource {
  id: number
  tenant_id: number
  source_kind: string
  source_key: string
  display_name: string
  bind_policy: FirstLoginPolicy
  linked_auth_provider_id: number | null
  linked_slack_endpoint_count: number
}

export interface PendingIdentity {
  id: number
  tenant_id: number
  provider_id: number
  provider_display_name: string
  external_subject: string
  email: string | null
  display_name: string | null
  status: string
  created_at: string
}

export async function listIdentitySources(): Promise<IdentitySource[]> {
  const res = await api.get<IdentitySource[]>('/tenants/identity-sources')
  return res.data
}

export async function updateIdentitySourceBindPolicy(
  sourceId: number,
  bind_policy: FirstLoginPolicy
): Promise<IdentitySource> {
  const res = await api.patch<IdentitySource>(`/tenants/identity-sources/${sourceId}`, {
    bind_policy,
  })
  return res.data
}

export async function listLoginDomains(): Promise<LoginDomain[]> {
  const res = await api.get<LoginDomain[]>('/tenants/identity/domains')
  return res.data
}

export async function addLoginDomains(domains: string[]): Promise<LoginDomain[]> {
  const res = await api.post<LoginDomain[]>('/tenants/identity/domains', { domains })
  return res.data
}

export async function removeLoginDomain(domainId: number): Promise<void> {
  await api.delete(`/tenants/identity/domains/${domainId}`)
}

export async function getIdentitySettings(): Promise<IdentitySettings> {
  const res = await api.get<IdentitySettings>('/tenants/identity/settings')
  return res.data
}

export async function updateIdentitySettings(force_sso: boolean): Promise<IdentitySettings> {
  const res = await api.put<IdentitySettings>('/tenants/identity/settings', { force_sso })
  return res.data
}

export async function setUserBreakGlass(
  userId: number,
  is_break_glass: boolean
): Promise<IdentitySettings> {
  const res = await api.put<IdentitySettings>(`/tenants/users/${userId}/break-glass`, {
    is_break_glass,
  })
  return res.data
}

export async function listPendingIdentities(): Promise<PendingIdentity[]> {
  const res = await api.get<PendingIdentity[]>('/tenants/identity/pending')
  return res.data
}

export async function approvePendingIdentity(id: number): Promise<PendingIdentity> {
  const res = await api.post<PendingIdentity>(`/tenants/identity/pending/${id}/approve`)
  return res.data
}

export async function rejectPendingIdentity(id: number): Promise<PendingIdentity> {
  const res = await api.post<PendingIdentity>(`/tenants/identity/pending/${id}/reject`)
  return res.data
}
