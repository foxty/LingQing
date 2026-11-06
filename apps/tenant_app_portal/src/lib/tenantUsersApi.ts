import api from './api'
import type { PaginatedListResponse } from '@/lib/paginatedList'

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

export interface TenantUserListParams {
  page?: number
  page_size?: number
  /** Search by username (substring, case-insensitive) or exact numeric user id */
  query?: string
}

/** User list uses the shared paginated envelope plus tenant-wide aggregates. */
export type TenantUserListResponse = PaginatedListResponse<TenantUser> & {
  total_tenant_members: number
  active_admin_count: number
}

export async function listTenantUsers(params?: TenantUserListParams): Promise<TenantUserListResponse> {
  const response = await api.get<TenantUserListResponse>('/tenants/users', { params })
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
