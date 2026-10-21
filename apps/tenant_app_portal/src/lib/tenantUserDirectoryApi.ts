import api from './api'

export interface TenantUserDirectoryEntry {
  user_id: number
  username: string
}

export async function searchTenantUserDirectory(params: {
  q?: string
  limit?: number
  exclude_user_ids?: number[]
}): Promise<TenantUserDirectoryEntry[]> {
  const response = await api.get<TenantUserDirectoryEntry[]>('/tenants/user-directory', {
    params,
  })
  return response.data
}
