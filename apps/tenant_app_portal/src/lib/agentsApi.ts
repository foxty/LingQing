import api, { getApiErrorMessage, mapFastApiValidationToFields } from './api'
import type {
  GetTenantUsageEventsParams,
  TenantTokenSummary,
  TokenUsageDailyPoint,
  TokenUsageEventsResponse,
} from './tenantApi'

export const SYSTEM_AGENT_ONE_ID = -1

/** Keep only catalog skill ids (drops stale entries hidden from the multi-select UI). */
export function filterAgentSkillIds(
  skills: string[],
  available: ReadonlySet<string>
): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const name of skills) {
    if (!available.has(name) || seen.has(name)) {
      continue
    }
    seen.add(name)
    out.push(name)
  }
  return out
}

export interface AgentCapabilityConfig {
  default_tools: string[]
  skills: string[]
  knowledge_base_ids: number[]
  data_source_ids: number[]
  api_connector_ids: number[]
  platform_capabilities: string[]
  model_profile_id?: number | null
}

export interface AgentAttachmentAccessItem {
  resource_type: string
  resource_id: number
  name: string
  can_read: boolean
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
  attachment_access: AgentAttachmentAccessItem[]
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

export type AgentFormFieldErrors = {
  name?: string
  systemPrompt?: string
}

const AGENT_WRITE_FIELD_LOC: Record<string, keyof AgentFormFieldErrors> = {
  name: 'name',
  system_prompt: 'systemPrompt',
}

export function validateAgentFormFields(
  name: string,
  systemPrompt: string,
  messages: { nameRequired: string; promptRequired: string }
): AgentFormFieldErrors {
  const errors: AgentFormFieldErrors = {}
  if (!name.trim()) {
    errors.name = messages.nameRequired
  }
  if (!systemPrompt.trim()) {
    errors.systemPrompt = messages.promptRequired
  }
  return errors
}

export function hasAgentFormFieldErrors(errors: AgentFormFieldErrors): boolean {
  return Boolean(errors.name || errors.systemPrompt)
}

export function getAgentFormFieldErrors(err: unknown): AgentFormFieldErrors {
  const data = (err as { response?: { data?: { validation_errors?: unknown; detail?: unknown } } })
    ?.response?.data
  const detail = data?.validation_errors ?? data?.detail
  return mapFastApiValidationToFields(detail, AGENT_WRITE_FIELD_LOC) as AgentFormFieldErrors
}

export function agentApiErrorMessage(err: unknown, fallback: string): string {
  return getApiErrorMessage(err, fallback)
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

export async function listPlatformCapabilities(): Promise<string[]> {
  const response = await api.get<string[]>('/agents/catalog/platform-capabilities')
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
