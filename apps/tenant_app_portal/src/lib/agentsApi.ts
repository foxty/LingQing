import api from './api'
import type {
  GetTenantUsageEventsParams,
  TenantTokenSummary,
  TokenUsageDailyPoint,
  TokenUsageEventsResponse,
} from './tenantApi'

export const SYSTEM_AGENT_ONE_ID = -1

export const PLATFORM_CAPABILITY_SCHEDULING = 'scheduling'
export const PLATFORM_CAPABILITY_REPORTS = 'reports'

export const PLATFORM_CAPABILITIES = [
  PLATFORM_CAPABILITY_SCHEDULING,
  PLATFORM_CAPABILITY_REPORTS,
] as const

export type PlatformCapability = (typeof PLATFORM_CAPABILITIES)[number]

export interface AgentCapabilityConfig {
  default_tools: string[]
  skills: string[]
  knowledge_base_ids: number[]
  data_source_ids: number[]
  api_connector_ids: number[]
  platform_capabilities: PlatformCapability[]
  model_profile_id?: number | null
}

export interface CatalogAgent {
  id: number
  name: string
  description: string | null
  system_prompt: string
  config: AgentCapabilityConfig
  tags: string[]
  example_questions: string[]
  status: string
  owner_id: number | null
  is_system: boolean
  created_at: string | null
  updated_at: string | null
  can_write: boolean
  can_manage: boolean
}

export interface AgentWritePayload {
  name: string
  description?: string | null
  system_prompt: string
  config: AgentCapabilityConfig
  tags?: string[]
  example_questions?: string[]
}

export interface AgentSkillCatalogItem {
  name: string
  description: string
  scope: string
  tools: string[]
}

export function agentApiErrorMessage(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: { message?: unknown; detail?: unknown } } })?.response
    ?.data
  if (typeof data?.message === 'string' && data.message.trim()) {
    return data.message
  }
  if (typeof data?.detail === 'string' && data.detail.trim()) {
    return data.detail
  }
  const message = err instanceof Error ? err.message : ''
  return message || fallback
}

export async function listCatalogAgents(): Promise<CatalogAgent[]> {
  const response = await api.get<CatalogAgent[]>('/agents')
  return response.data
}

export async function getCatalogAgent(agentId: number): Promise<CatalogAgent> {
  const response = await api.get<CatalogAgent>(`/agents/${agentId}`)
  return response.data
}

export async function createCatalogAgent(payload: AgentWritePayload): Promise<CatalogAgent> {
  const response = await api.post<CatalogAgent>('/agents', payload)
  return response.data
}

export async function updateCatalogAgent(
  agentId: number,
  payload: Partial<AgentWritePayload>
): Promise<CatalogAgent> {
  const response = await api.put<CatalogAgent>(`/agents/${agentId}`, payload)
  return response.data
}

export async function deleteCatalogAgent(agentId: number): Promise<void> {
  await api.delete(`/agents/${agentId}`)
}

export async function listAgentSkillCatalog(): Promise<AgentSkillCatalogItem[]> {
  const response = await api.get<AgentSkillCatalogItem[]>('/agents/catalog/skills')
  return response.data
}

export type {
  GetTenantUsageEventsParams as GetAgentUsageEventsParams,
  TenantTokenSummary as AgentUsageSummary,
  TokenUsageDailyPoint,
  TokenUsageEventsResponse,
} from './tenantApi'

export type AgentUsageFilterParams = {
  days?: number
  user_id?: number
}

export async function getAgentUsageSummary(
  agentId: number,
  params: AgentUsageFilterParams = {}
): Promise<TenantTokenSummary> {
  const response = await api.get<TenantTokenSummary>(`/agents/${agentId}/usage/summary`, {
    params: { days: params.days ?? 30, user_id: params.user_id },
  })
  return response.data
}

export async function getAgentUsageDaily(
  agentId: number,
  params: AgentUsageFilterParams = {}
): Promise<TokenUsageDailyPoint[]> {
  const response = await api.get<TokenUsageDailyPoint[]>(`/agents/${agentId}/usage/daily`, {
    params: { days: params.days ?? 30, user_id: params.user_id },
  })
  return response.data
}

export async function getAgentUsageEvents(
  agentId: number,
  params: GetTenantUsageEventsParams = {}
): Promise<TokenUsageEventsResponse> {
  const response = await api.get<TokenUsageEventsResponse>(`/agents/${agentId}/usage/events`, {
    params,
  })
  return response.data
}
