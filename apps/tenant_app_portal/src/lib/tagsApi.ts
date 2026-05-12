import api from './api'

export const TAG_RESOURCE_TYPES = {
  USER: 'user',
  DOCUMENT_COLLECTION: 'document_collection',
  API_CONNECTOR: 'api_connector',
  DATA_SOURCE: 'data_source',
} as const

export type ResourceType = (typeof TAG_RESOURCE_TYPES)[keyof typeof TAG_RESOURCE_TYPES]
export type TagValueMode = 'inclusive' | 'exclusive'

export interface TagKeyDTO {
  id: number
  tenant_id: number
  name: string
  description: string | null
  color: string | null
  status: 'active' | 'disabled'
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
}

export interface TagKeyCreateRequest {
  name: string
  description?: string | null
  color?: string | null
}

export interface TagKeyUpdateRequest {
  name?: string | null
  description?: string | null
  color?: string | null
}

export interface TagValueDTO {
  id: number
  tenant_id: number
  key_id: number
  value: string
  rank: number | null
  status: 'active' | 'disabled'
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
}

export interface TagValueCreateRequest {
  key_id: number
  value: string
  rank?: number | null
}

export interface TagValueUpdateRequest {
  value?: string | null
  rank?: number | null
}

export interface ResourceTagConfigDTO {
  id: number
  tenant_id: number
  resource_type: ResourceType
  tag_key_id: number
  value_mode: TagValueMode
  created_at: string
  created_by: number | null
}

export interface ResourceTagConfigCreateRequest {
  resource_type: ResourceType
  tag_key_id: number
  value_mode: TagValueMode
}

export interface ResourceTagConfigUpdateRequest {
  value_mode: TagValueMode
}

export interface TagBindingCreateRequest {
  tag_value_id: number
}

const resourceBasePath = (resourceType: ResourceType) => {
  switch (resourceType) {
    case TAG_RESOURCE_TYPES.USER:
      return '/users'
    case TAG_RESOURCE_TYPES.DOCUMENT_COLLECTION:
      return '/document-collections'
    case TAG_RESOURCE_TYPES.API_CONNECTOR:
      return '/api-connectors'
    case TAG_RESOURCE_TYPES.DATA_SOURCE:
      return '/data-sources'
    default:
      return '/data-sources'
  }
}

export async function listTagKeys(): Promise<TagKeyDTO[]> {
  const response = await api.get<TagKeyDTO[]>('/tags/keys')
  return response.data
}

export async function getTagKey(tagKeyId: number): Promise<TagKeyDTO> {
  const response = await api.get<TagKeyDTO>(`/tags/keys/${tagKeyId}`)
  return response.data
}

export async function createTagKey(payload: TagKeyCreateRequest): Promise<TagKeyDTO> {
  const response = await api.post<TagKeyDTO>('/tags/keys', payload)
  return response.data
}

export async function updateTagKey(
  tagKeyId: number,
  payload: TagKeyUpdateRequest
): Promise<TagKeyDTO> {
  const response = await api.patch<TagKeyDTO>(`/tags/keys/${tagKeyId}`, payload)
  return response.data
}

export async function disableTagKey(tagKeyId: number): Promise<TagKeyDTO> {
  const response = await api.patch<TagKeyDTO>(`/tags/keys/${tagKeyId}/disable`)
  return response.data
}

export async function enableTagKey(tagKeyId: number): Promise<TagKeyDTO> {
  const response = await api.patch<TagKeyDTO>(`/tags/keys/${tagKeyId}/enable`)
  return response.data
}

export async function deleteTagKey(tagKeyId: number): Promise<void> {
  await api.delete(`/tags/keys/${tagKeyId}`)
}

export async function listTagValues(keyId?: number): Promise<TagValueDTO[]> {
  const response = await api.get<TagValueDTO[]>('/tags/values', {
    params: keyId ? { key_id: keyId } : undefined,
  })
  return response.data
}

export async function getTagValue(tagValueId: number): Promise<TagValueDTO> {
  const response = await api.get<TagValueDTO>(`/tags/values/${tagValueId}`)
  return response.data
}

export async function createTagValue(payload: TagValueCreateRequest): Promise<TagValueDTO> {
  const response = await api.post<TagValueDTO>('/tags/values', payload)
  return response.data
}

export async function updateTagValue(
  tagValueId: number,
  payload: TagValueUpdateRequest
): Promise<TagValueDTO> {
  const response = await api.patch<TagValueDTO>(`/tags/values/${tagValueId}`, payload)
  return response.data
}

export async function disableTagValue(tagValueId: number): Promise<TagValueDTO> {
  const response = await api.patch<TagValueDTO>(`/tags/values/${tagValueId}/disable`)
  return response.data
}

export async function enableTagValue(tagValueId: number): Promise<TagValueDTO> {
  const response = await api.patch<TagValueDTO>(`/tags/values/${tagValueId}/enable`)
  return response.data
}

export async function deleteTagValue(tagValueId: number): Promise<void> {
  await api.delete(`/tags/values/${tagValueId}`)
}

export async function listResourceTagConfigs(
  resourceType?: ResourceType
): Promise<ResourceTagConfigDTO[]> {
  const response = await api.get<ResourceTagConfigDTO[]>('/resource-tag-configs', {
    params: resourceType ? { resource_type: resourceType } : undefined,
  })
  return response.data
}

export async function getResourceTagConfig(configId: number): Promise<ResourceTagConfigDTO> {
  const response = await api.get<ResourceTagConfigDTO>(`/resource-tag-configs/${configId}`)
  return response.data
}

export async function createResourceTagConfig(
  payload: ResourceTagConfigCreateRequest
): Promise<ResourceTagConfigDTO> {
  const response = await api.post<ResourceTagConfigDTO>('/resource-tag-configs', payload)
  return response.data
}

export async function updateResourceTagConfig(
  configId: number,
  payload: ResourceTagConfigUpdateRequest
): Promise<ResourceTagConfigDTO> {
  const response = await api.patch<ResourceTagConfigDTO>(
    `/resource-tag-configs/${configId}`,
    payload
  )
  return response.data
}

export async function deleteResourceTagConfig(configId: number): Promise<void> {
  await api.delete(`/resource-tag-configs/${configId}`)
}

export async function listTagsForResource(
  resourceType: ResourceType,
  resourceId: number
): Promise<TagValueDTO[]> {
  const response = await api.get<TagValueDTO[]>(
    `${resourceBasePath(resourceType)}/${resourceId}/tags`
  )
  return response.data
}

export async function listTagsForCurrentUser(): Promise<TagValueDTO[]> {
  const response = await api.get<TagValueDTO[]>('/auth/profile/tags')
  return response.data
}

export async function bindTagValueToResource(
  resourceType: ResourceType,
  resourceId: number,
  payload: TagBindingCreateRequest
): Promise<TagValueDTO> {
  const response = await api.post<TagValueDTO>(
    `${resourceBasePath(resourceType)}/${resourceId}/tags`,
    payload
  )
  return response.data
}

export async function unbindTagValueFromResource(
  resourceType: ResourceType,
  resourceId: number,
  tagValueId: number
): Promise<void> {
  await api.delete(`${resourceBasePath(resourceType)}/${resourceId}/tags/${tagValueId}`)
}
