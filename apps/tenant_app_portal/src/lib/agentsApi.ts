import api, { getApiErrorMessage, mapFastApiValidationToFields } from './api'
import type {
  GetTenantUsageEventsParams,
  TenantTokenSummary,
  TokenUsageDailyPoint,
  TokenUsageEventsResponse,
} from './tenantApi'

export const SYSTEM_AGENT_ONE_ID = -1

/** Hydration key for agent settings; null while skill catalog is still loading. */
export function buildAgentSettingsHydrationKey(params: {
  agentId: number
  updatedAt: string | null | undefined
  formOptionsEnabled: boolean
  formOptionsLoading: boolean
  skillNames: readonly string[]
}): string | null {
  if (params.formOptionsEnabled && params.formOptionsLoading) {
    return null
  }
  const catalogPart = params.formOptionsEnabled
    ? [...params.skillNames].sort().join('\0')
    : 'options-idle'
  return `${params.agentId}:${params.updatedAt ?? ''}:${catalogPart}`
}

/** When undefined, agentConfigFromAgent keeps config.skills as stored (no catalog filter). */
export function skillNamesForAgentConfigMerge(
  formOptionsEnabled: boolean,
  formOptionsLoading: boolean,
  skills: readonly { name: string }[]
): Iterable<string> | undefined {
  if (!formOptionsEnabled || formOptionsLoading) {
    return undefined
  }
  return skills.map((s) => s.name)
}

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
  /** Effective value from GET; omit or null on write to inherit platform default. */
  max_loop_iterations?: number | null
}

/** Align with backend ``MAX_LOOP_ITERATIONS_UPPER``. */
export const AGENT_MAX_LOOP_ITERATIONS_MIN = 1
export const AGENT_MAX_LOOP_ITERATIONS_MAX = 200

export function formatAgentMaxLoopInputValue(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return ''
  }
  return String(value)
}

/**
 * Parse max-loop text input. Returns `null` for empty (inherit platform default).
 * Returns `undefined` when the raw string is not a valid integer in range (caller should ignore).
 */
export function parseAgentMaxLoopInputChange(
  raw: string
): number | null | undefined {
  const trimmed = raw.trim()
  if (!trimmed) {
    return null
  }
  const parsed = Number(trimmed)
  if (!Number.isInteger(parsed)) {
    return undefined
  }
  if (parsed < AGENT_MAX_LOOP_ITERATIONS_MIN || parsed > AGENT_MAX_LOOP_ITERATIONS_MAX) {
    return undefined
  }
  return parsed
}

export function validateAgentMaxLoopIterations(
  value: number | null | undefined,
  rangeMessage: string
): string | undefined {
  if (value === null || value === undefined) {
    return undefined
  }
  if (!Number.isInteger(value) || value < AGENT_MAX_LOOP_ITERATIONS_MIN || value > AGENT_MAX_LOOP_ITERATIONS_MAX) {
    return rangeMessage
  }
  return undefined
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
  maxLoopIterations?: string
}

const AGENT_WRITE_FIELD_LOC: Record<string, keyof AgentFormFieldErrors> = {
  name: 'name',
  system_prompt: 'systemPrompt',
  'config.max_loop_iterations': 'maxLoopIterations',
}

export function validateAgentFormFields(
  name: string,
  systemPrompt: string,
  messages: { nameRequired: string; promptRequired: string; maxLoopIterationsRange?: string },
  maxLoopIterations?: number | null
): AgentFormFieldErrors {
  const errors: AgentFormFieldErrors = {}
  if (!name.trim()) {
    errors.name = messages.nameRequired
  }
  if (!systemPrompt.trim()) {
    errors.systemPrompt = messages.promptRequired
  }
  if (messages.maxLoopIterationsRange) {
    const maxLoopError = validateAgentMaxLoopIterations(
      maxLoopIterations,
      messages.maxLoopIterationsRange
    )
    if (maxLoopError) {
      errors.maxLoopIterations = maxLoopError
    }
  }
  return errors
}

export function hasAgentFormFieldErrors(errors: AgentFormFieldErrors): boolean {
  return Boolean(errors.name || errors.systemPrompt || errors.maxLoopIterations)
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
  start_time?: string
  end_time?: string
  user_id?: number
}

function buildAgentUsageWindowParams(params: AgentUsageFilterParams) {
  const { start_time, end_time, user_id } = params
  if (!start_time || !end_time) {
    throw new Error('Agent usage queries require start_time and end_time')
  }
  return { start_time, end_time, user_id }
}

export async function getAgentUsageSummary(
  agentId: number,
  params: AgentUsageFilterParams = {}
): Promise<TenantTokenSummary> {
  const response = await api.get<TenantTokenSummary>(`/agents/${agentId}/usage/summary`, {
    params: buildAgentUsageWindowParams(params),
  })
  return response.data
}

export async function getAgentUsageDaily(
  agentId: number,
  params: AgentUsageFilterParams = {}
): Promise<TokenUsageDailyPoint[]> {
  const response = await api.get<TokenUsageDailyPoint[]>(`/agents/${agentId}/usage/daily`, {
    params: buildAgentUsageWindowParams(params),
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
