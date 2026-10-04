import api from './api'

export type ModelProfileCategory = 'llm' | 'embedding'

export interface CatalogModel {
  key: string
  name: string
  model_id: string
  default_params?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
  category?: string | null
}

export interface CatalogProvider {
  key?: string | null
  provider: string
  name: string
  type: string
  api_base?: string | null
  api_base_env?: string | null
  models: CatalogModel[]
}

export interface LLMProvider {
  id: number
  display_name: string
  preset_key: string | null
  type: string
  api_base: string
  embedding_api_base: string | null
  api_key_masked: string
  status: string
}

export interface LLMModelProfile {
  id: number
  provider_id: number
  name: string
  category: ModelProfileCategory
  model_id: string
  params: Record<string, unknown> | null
  catalog_model_key: string | null
  source: string
}

export interface LLMDefaults {
  agent_profile_id: number | null
  mini_agent_profile_id: number | null
  embedding_profile_id: number | null
}

export interface CreateLLMProviderRequest {
  display_name: string
  preset_key?: string | null
  type?: string
  api_base: string
  embedding_api_base?: string | null
  api_key?: string
}

export interface UpdateLLMProviderRequest {
  display_name?: string
  preset_key?: string | null
  type?: string
  api_base?: string
  embedding_api_base?: string | null
  api_key?: string
  status?: string
}

export interface CreateLLMModelProfileRequest {
  provider_id: number
  name: string
  category: ModelProfileCategory
  model_id: string
  params?: Record<string, unknown> | null
  catalog_model_key?: string | null
  source?: string
}

export interface UpdateLLMModelProfileRequest {
  name?: string
  model_id?: string
  params?: Record<string, unknown> | null
  catalog_model_key?: string | null
  source?: string
}

export interface UpdateLLMDefaultsRequest {
  agent_profile_id?: number | null
  mini_agent_profile_id?: number | null
  embedding_profile_id?: number | null
}

export const CUSTOM_CATALOG_MODEL_KEY = '__custom__'

/** Map tenant provider credentials to a platform catalog preset key. */
export function inferCatalogPresetKey(
  provider: Pick<LLMProvider, 'preset_key' | 'api_base'>,
  catalog: CatalogProvider[]
): string | null {
  if (provider.preset_key) {
    return provider.preset_key
  }

  const apiBase = provider.api_base.toLowerCase()

  if (apiBase.includes('databricks.com') && apiBase.includes('/ai-gateway/')) {
    return 'databricks-ai-gateway'
  }
  if (apiBase.includes('coding.dashscope.aliyuncs.com')) {
    return 'bailian-coding-plan'
  }
  if (apiBase.includes('dashscope.aliyuncs.com')) {
    return 'bailian'
  }
  if (apiBase.includes('api.deepseek.com')) {
    return 'deepseek'
  }
  if (apiBase.includes('api.lkeap.cloud.tencent.com')) {
    return 'tencent-cloud'
  }
  if (apiBase.includes('qianfan.baidubce.com')) {
    return apiBase.includes('/coding') ? 'baidu-qianfan-coding-plan' : 'baidu-qianfan'
  }
  if (apiBase.includes('api.opencode.go')) {
    return 'opencode-go'
  }
  if (apiBase.includes('api.mimo.xiaomi.com')) {
    return 'xiaomi-mimo'
  }
  if (apiBase.includes('token-plan-cn.xiaomimimo.com')) {
    return 'xiaomi-mimo-coding-plan'
  }

  const exact = catalog.find((item) => item.api_base && item.api_base === provider.api_base)
  return exact?.key || exact?.provider || null
}

export function catalogModelsForProvider(
  provider: LLMProvider,
  catalog: CatalogProvider[],
  category: ModelProfileCategory
): CatalogModel[] {
  const presetKey = inferCatalogPresetKey(provider, catalog)
  if (!presetKey) {
    return []
  }
  const preset = catalog.find((item) => item.key === presetKey || item.provider === presetKey)
  if (!preset) {
    return []
  }
  return preset.models.filter((model) =>
    category === 'embedding' ? model.category === 'embedding' : model.category !== 'embedding'
  )
}

export async function listCatalogProviders(): Promise<CatalogProvider[]> {
  const response = await api.get<CatalogProvider[]>('/llm-config/providers')
  return response.data
}

export async function listCatalogModels(
  category: ModelProfileCategory,
  providerKey?: string | null
): Promise<CatalogModel[]> {
  const params = new URLSearchParams({ category })
  if (providerKey) {
    params.set('provider', providerKey)
  }
  const response = await api.get<CatalogModel[]>(`/llm-config/models?${params.toString()}`)
  return response.data
}

export async function listRegistryProviders(): Promise<LLMProvider[]> {
  const response = await api.get<LLMProvider[]>('/llm-config/registry/providers')
  return response.data
}

export async function createRegistryProvider(payload: CreateLLMProviderRequest): Promise<LLMProvider> {
  const response = await api.post<LLMProvider>('/llm-config/registry/providers', payload)
  return response.data
}

export async function updateRegistryProvider(
  providerId: number,
  payload: UpdateLLMProviderRequest
): Promise<LLMProvider> {
  const response = await api.put<LLMProvider>(`/llm-config/registry/providers/${providerId}`, payload)
  return response.data
}

export async function deleteRegistryProvider(providerId: number): Promise<void> {
  await api.delete(`/llm-config/registry/providers/${providerId}`)
}

export async function testRegistryProviderConnection(
  providerId: number,
  payload: {
    api_base?: string
    model_id?: string
    api_key?: string
    category?: ModelProfileCategory
  } = {}
): Promise<{ status: string; message: string }> {
  const response = await api.post<{ status: string; message: string }>(
    `/llm-config/registry/providers/${providerId}/test`,
    payload
  )
  return response.data
}

export async function listRegistryProfiles(category?: ModelProfileCategory): Promise<LLMModelProfile[]> {
  const query = category ? `?category=${category}` : ''
  const response = await api.get<LLMModelProfile[]>(`/llm-config/registry/profiles${query}`)
  return response.data
}

export async function createRegistryProfile(payload: CreateLLMModelProfileRequest): Promise<LLMModelProfile> {
  const response = await api.post<LLMModelProfile>('/llm-config/registry/profiles', payload)
  return response.data
}

export async function updateRegistryProfile(
  profileId: number,
  payload: UpdateLLMModelProfileRequest
): Promise<LLMModelProfile> {
  const response = await api.put<LLMModelProfile>(`/llm-config/registry/profiles/${profileId}`, payload)
  return response.data
}

export async function deleteRegistryProfile(profileId: number): Promise<void> {
  await api.delete(`/llm-config/registry/profiles/${profileId}`)
}

export async function testRegistryProfileConnection(
  profileId: number,
  apiKey = ''
): Promise<{ status: string; message: string }> {
  const response = await api.post<{ status: string; message: string }>(
    `/llm-config/registry/profiles/${profileId}/test`,
    { api_key: apiKey }
  )
  return response.data
}

export async function getRegistryDefaults(): Promise<LLMDefaults> {
  const response = await api.get<LLMDefaults>('/llm-config/registry/defaults')
  return response.data
}

export async function updateRegistryDefaults(payload: UpdateLLMDefaultsRequest): Promise<LLMDefaults> {
  const response = await api.put<LLMDefaults>('/llm-config/registry/defaults', payload)
  return response.data
}
