import api from './api'

export type TenantUserRole = 'admin' | 'member' | 'viewer'

export interface TenantUser {
  id: number
  username: string
  role: TenantUserRole
  tenant_id: number
  tenant_name: string
  membership_status: string
  is_break_glass?: boolean
}

export interface TenantUserCreateRequest {
  username: string
  password: string
  role: TenantUserRole
  email?: string
}

export interface TenantUserResetPasswordRequest {
  new_password: string
}

export interface TenantUserUpdateRequest {
  role: TenantUserRole
}

export async function listTenantUsers(): Promise<TenantUser[]> {
  const response = await api.get<TenantUser[]>('/tenants/users')
  return response.data
}

export async function createTenantUser(payload: TenantUserCreateRequest): Promise<TenantUser> {
  const response = await api.post<TenantUser>('/tenants/users', payload)
  return response.data
}

export async function deactivateTenantUser(userId: number): Promise<void> {
  await api.post(`/tenants/users/${userId}/deactivate`)
}

export async function recoverTenantUser(userId: number): Promise<void> {
  await api.post(`/tenants/users/${userId}/recover`)
}

export async function resetTenantUserPassword(
  userId: number,
  payload: TenantUserResetPasswordRequest
): Promise<void> {
  await api.post(`/tenants/users/${userId}/reset-password`, payload)
}

export async function updateTenantUserRole(
  userId: number,
  payload: TenantUserUpdateRequest
): Promise<TenantUser> {
  const response = await api.put<TenantUser>(`/tenants/users/${userId}`, payload)
  return response.data
}
