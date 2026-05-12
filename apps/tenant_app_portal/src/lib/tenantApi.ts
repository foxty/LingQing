/**
 * Tenant management API functions
 */

import api from './api'

export interface TenantStats {
  total_documents: number
  total_assets: number
  total_agents: number
  total_storage_bytes: number
}

export async function getTenantStats(): Promise<TenantStats> {
  const response = await api.get<TenantStats>('/tenants/stats')
  return response.data
}

export interface TenantSettings {
  default_agent_model: string
  default_mini_agent_model: string
}

export interface TenantTokenSummary {
  tenant_id: number
  period_start: string
  period_end: string
  total_llm_calls: number
  total_llm_errors: number
  total_tool_calls: number
  total_tool_errors: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  unique_sessions: number
  unique_threads: number
  unique_users: number
  estimated_cost: number | null
}

export interface TokenUsageDailyPoint {
  date: string
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  llm_calls: number
  llm_errors: number
}

export interface TokenUsageEventRecord {
  event_id: string
  timestamp: string
  session_id: string
  thread_id: string | null
  user_id: number | null
  username: string | null
  agent_id: number | null
  agent_name: string | null
  model_key: string | null
  model_name: string | null
  model_label: string | null
  input_tokens: number
  output_tokens: number
  total_tokens: number
  duration_ms: number | null
  status: string
}

export interface TokenUsageEventsResponse {
  page: number
  page_size: number
  total: number
  total_pages: number
  rows: TokenUsageEventRecord[]
}

export interface ModelInfo {
  key: string
  name: string
  provider: string
  description?: string
}

export interface ModelProviderGroup {
  provider: string
  models: ModelInfo[]
}

/**
 * Get current tenant settings (admin only)
 */
export async function getTenantSettings(): Promise<TenantSettings> {
  const response = await api.get<TenantSettings>('/tenants/settings')
  return response.data
}

/**
 * Update tenant settings (admin only)
 */
export async function updateTenantSettings(settings: TenantSettings): Promise<TenantSettings> {
  const response = await api.put<TenantSettings>('/tenants/settings', settings)
  return response.data
}

/**
 * Get list of available models from registry (admin only)
 */
export async function getAvailableModels(): Promise<ModelProviderGroup[]> {
  const response = await api.get<ModelProviderGroup[]>('/tenants/models')
  return response.data
}

/**
 * Placeholder: Get tenant users (coming soon)
 */
export async function getTenantUsers(): Promise<{ message: string; feature: string }> {
  const response = await api.get('/tenants/users')
  return response.data
}

export interface TenantTokenFilterParams {
  days?: number
  user_id?: number
  agent_id?: number
}

export async function getTenantTokenSummary(
  params: TenantTokenFilterParams = {}
): Promise<TenantTokenSummary> {
  const response = await api.get<TenantTokenSummary>('/observability/tenant/token-summary', {
    params: { days: params.days ?? 30, user_id: params.user_id, agent_id: params.agent_id },
  })
  return response.data
}

export async function getTenantTokenDaily(
  params: TenantTokenFilterParams = {}
): Promise<TokenUsageDailyPoint[]> {
  const response = await api.get<TokenUsageDailyPoint[]>('/observability/tenant/token-daily', {
    params: { days: params.days ?? 30, user_id: params.user_id, agent_id: params.agent_id },
  })
  return response.data
}

export interface GetTenantUsageEventsParams {
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
  user_id?: number
  agent_id?: number
}

export async function getTenantUsageEvents(
  params: GetTenantUsageEventsParams = {}
): Promise<TokenUsageEventsResponse> {
  const response = await api.get<TokenUsageEventsResponse>('/observability/tenant/token-events', {
    params,
  })
  return response.data
}

/**
 * Placeholder: Get subscription info (coming soon)
 */
export async function getTenantSubscription(): Promise<{ message: string; feature: string }> {
  const response = await api.get('/tenants/subscription')
  return response.data
}

// ==================== LLM Config ====================

export interface LLMModelConfig {
  name: string
  type: string
  api_base: string
  api_key_masked?: string
  model_id: string
  params?: Record<string, unknown>
}

export interface LLMConfig {
  agent_model: LLMModelConfig
  mini_agent_model: LLMModelConfig
}

export interface TenantLLMConfigResponse {
  agent_model: LLMModelConfig
  mini_agent_model: LLMModelConfig
}

export interface UpdateLLMConfigRequest {
  agent_model: {
    name: string
    type: string
    api_base: string
    api_key: string
    model_id: string
    params?: Record<string, unknown>
  }
  mini_agent_model: {
    name: string
    type: string
    api_base: string
    api_key: string
    model_id: string
    params?: Record<string, unknown>
  }
}

export interface PresetModel {
  key: string
  name: string
  model_id: string
  default_params?: Record<string, unknown>
}

export interface PresetProvider {
  provider: string
  name: string
  type: string
  api_base?: string | null
  models: PresetModel[]
}

export function isEditableApiBase(apiBase?: string | null): boolean {
  return !apiBase || /<[^>]+>/.test(apiBase)
}

export function resolvePresetApiBase(
  providerBase: string | null | undefined,
  currentBase: string
): string {
  if (!providerBase) return currentBase
  if (
    isEditableApiBase(providerBase) &&
    currentBase &&
    !isEditableApiBase(currentBase) &&
    matchesApiBaseTemplate(providerBase, currentBase)
  ) {
    return currentBase
  }
  return providerBase
}

function matchesApiBaseTemplate(template: string, actual: string): boolean {
  const suffix = template.replace(/^https?:\/\/<[^>]+>[^/]*/, '')
  return !!suffix && actual.includes(suffix)
}

export function findPresetByModel(
  providers: PresetProvider[],
  modelId: string,
  apiBase: string
): { providerKey: string; modelKey: string } | null {
  for (const provider of providers) {
    const model = provider.models.find((m) => m.model_id === modelId)
    if (!model) continue
    if (!isEditableApiBase(provider.api_base) && provider.api_base !== apiBase) {
      continue
    }
    if (isEditableApiBase(provider.api_base) && !apiBase) {
      continue
    }
    return { providerKey: provider.provider, modelKey: model.key }
  }
  return null
}

/**
 * Get available preset providers and models
 */
export async function getLLMProviders(): Promise<PresetProvider[]> {
  const response = await api.get<PresetProvider[]>('/llm-config/providers')
  return response.data
}

/**
 * Get current LLM config for the tenant
 */
export async function getTenantLLMConfig(): Promise<TenantLLMConfigResponse | null> {
  const response = await api.get<TenantLLMConfigResponse>('/llm-config/config')
  return response.data
}

/**
 * Update LLM config for the tenant
 */
export async function updateTenantLLMConfig(
  config: UpdateLLMConfigRequest
): Promise<TenantLLMConfigResponse> {
  const response = await api.put<TenantLLMConfigResponse>('/llm-config/config', config)
  return response.data
}

/**
 * Test LLM connection with basic parameters
 */
export async function testLLMConnection(params: {
  api_base: string
  model_id: string
  api_key: string
}): Promise<{ status: string; message: string }> {
  const response = await api.post<{ status: string; message: string }>(
    '/llm-config/test-connection',
    params
  )
  return response.data
}

/**
 * Update only agent model config
 */
export async function updateAgentModelConfig(
  config: UpdateLLMConfigRequest['agent_model']
): Promise<TenantLLMConfigResponse> {
  const response = await api.put<TenantLLMConfigResponse>('/llm-config/agent-config', config)
  return response.data
}

/**
 * Update only mini agent model config
 */
export async function updateMiniAgentModelConfig(
  config: UpdateLLMConfigRequest['mini_agent_model']
): Promise<TenantLLMConfigResponse> {
  const response = await api.put<TenantLLMConfigResponse>('/llm-config/mini-agent-config', config)
  return response.data
}

/**
 * Copy agent model config to mini agent (including encrypted API key)
 */
export async function copyAgentToMini(): Promise<TenantLLMConfigResponse> {
  const response = await api.post<TenantLLMConfigResponse>('/llm-config/copy-agent-to-mini')
  return response.data
}

// ==================== Embedding Config ====================

export interface EmbeddingModelConfig {
  name: string
  type: string
  api_base: string
  api_key_masked?: string
  model_id: string
}

export interface TenantEmbeddingConfigResponse {
  embedding_model: EmbeddingModelConfig
}

export interface UpdateEmbeddingConfigRequest {
  embedding_model: {
    name: string
    type: string
    api_base: string
    api_key: string // Empty string = keep existing key
    model_id: string
  }
}

/**
 * Get current Embedding config for the tenant
 */
export async function getTenantEmbeddingConfig(): Promise<TenantEmbeddingConfigResponse | null> {
  const response = await api.get<TenantEmbeddingConfigResponse>('/llm-config/embedding-config')
  return response.data
}

/**
 * Update Embedding config for the tenant
 */
export async function updateTenantEmbeddingConfig(
  config: UpdateEmbeddingConfigRequest
): Promise<TenantEmbeddingConfigResponse> {
  const response = await api.put<TenantEmbeddingConfigResponse>('/llm-config/embedding-config', config)
  return response.data
}

/**
 * Test Embedding connection with basic parameters
 */
export async function testEmbeddingConnection(params: {
  api_base: string
  model_id: string
  api_key: string
}): Promise<{ status: string; message: string }> {
  const response = await api.post<{ status: string; message: string }>(
    '/llm-config/test-embedding-connection',
    params
  )
  return response.data
}

/**
 * Get available preset providers and models for embedding
 */
export async function getEmbeddingProviders(): Promise<PresetProvider[]> {
  const response = await api.get<PresetProvider[]>('/llm-config/providers/by-category?category=embedding')
  return response.data
}
