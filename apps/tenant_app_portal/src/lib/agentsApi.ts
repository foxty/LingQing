import api from './api'

export const SYSTEM_AGENT_ONE_ID = -1

export interface AgentCapabilityConfig {
  default_tools: string[]
  skills: string[]
  knowledge_base_ids: number[]
  data_source_ids: number[]
  api_connector_ids: number[]
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
