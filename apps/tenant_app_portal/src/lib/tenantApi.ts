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
