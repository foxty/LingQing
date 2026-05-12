import api from './api'

export const ACL_SHARE_RESOURCE_TYPES = {
  DOCUMENT_COLLECTION: 'document_collection',
  API_CONNECTOR: 'api_connector',
  DATA_SOURCE: 'data_source',
  DASHBOARD: 'dashboard',
  REPORT: 'report',
  SCHEDULED_TASK: 'scheduled_task',
  APP: 'app',
  AGENT: 'agent',
} as const

export type AclShareResourceType =
  (typeof ACL_SHARE_RESOURCE_TYPES)[keyof typeof ACL_SHARE_RESOURCE_TYPES]
export type AclSharePermission = 'read' | 'write'

export interface AclShareRequest {
  user_id: number
  permission: AclSharePermission
}

export interface AclShareEntry {
  id: number
  resource_type: AclShareResourceType
  resource_id: number
  shared_with_user_id: number
  shared_with_username: string | null
  permission: AclSharePermission
  shared_by: number | null
  created_at: string
}

export interface AclShareListResponse {
  shares: AclShareEntry[]
  can_manage: boolean
}

export interface AclShareCandidate {
  id: number
  username: string
}

export async function shareAclResource(
  resourceType: AclShareResourceType,
  resourceId: number,
  payload: AclShareRequest
): Promise<AclShareEntry> {
  const response = await api.post<AclShareEntry>(
    `/acl-shares/${resourceType}/${resourceId}/shares`,
    payload
  )
  return response.data
}

export async function listAclResourceShares(
  resourceType: AclShareResourceType,
  resourceId: number
): Promise<AclShareListResponse> {
  const response = await api.get<AclShareListResponse>(
    `/acl-shares/${resourceType}/${resourceId}/shares`
  )
  return response.data
}

export async function listAclShareCandidates(
  resourceType: AclShareResourceType,
  resourceId: number,
  params: { q?: string; limit?: number } = {}
): Promise<AclShareCandidate[]> {
  const response = await api.get<AclShareCandidate[]>(
    `/acl-shares/${resourceType}/${resourceId}/candidates`,
    {
      params,
    }
  )
  return response.data
}

export async function revokeAclResourceShare(
  resourceType: AclShareResourceType,
  resourceId: number,
  userId: number
): Promise<void> {
  await api.delete(`/acl-shares/${resourceType}/${resourceId}/shares/${userId}`)
}
