import api from './api'

export type ResourceType = 'user' | 'document_collection' | 'data_source' | 'api_connector'
export type AbacAction = 'read' | 'write'

export interface AbacPolicy {
  id: number
  tenant_id: number
  name: string
  description: string | null
  resource_type: ResourceType
  action: AbacAction
  expression: string
  status: 'active' | 'disabled'
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
}

export interface AbacPolicyCreatePayload {
  name: string
  description?: string | null
  resource_type: ResourceType
  action?: AbacAction
  expression: string
}

export interface AbacPolicyUpdatePayload {
  name?: string
  description?: string | null
  resource_type?: ResourceType
  action?: AbacAction
  expression?: string
}

export interface ValidateExpressionResponse {
  valid: boolean
  errors: string[]
  human_readable: string | null
}

export interface SimulatePolicyPayload {
  expression: string
  resource_type: ResourceType
  user_id: number
  resource_id: number
  user_role?: string | null
}

export interface SimulatePolicyResponse {
  allowed: boolean
  reason: string
}

export interface SeedPoliciesResponse {
  created: number
  skipped: number
}

const BASE = '/abac/policies'

export async function listPolicies(resourceType?: ResourceType): Promise<AbacPolicy[]> {
  const res = await api.get<AbacPolicy[]>(BASE, {
    params: resourceType ? { resource_type: resourceType } : {},
  })
  return res.data
}

export async function getPolicy(id: number): Promise<AbacPolicy> {
  const res = await api.get<AbacPolicy>(`${BASE}/${id}`)
  return res.data
}

export async function createPolicy(payload: AbacPolicyCreatePayload): Promise<AbacPolicy> {
  const res = await api.post<AbacPolicy>(BASE, payload)
  return res.data
}

export async function updatePolicy(
  id: number,
  payload: AbacPolicyUpdatePayload
): Promise<AbacPolicy> {
  const res = await api.patch<AbacPolicy>(`${BASE}/${id}`, payload)
  return res.data
}

export async function deletePolicy(id: number): Promise<void> {
  await api.delete(`${BASE}/${id}`)
}

export async function enablePolicy(id: number): Promise<AbacPolicy> {
  const res = await api.patch<AbacPolicy>(`${BASE}/${id}/enable`)
  return res.data
}

export async function disablePolicy(id: number): Promise<AbacPolicy> {
  const res = await api.patch<AbacPolicy>(`${BASE}/${id}/disable`)
  return res.data
}

export async function validateExpression(expression: string): Promise<ValidateExpressionResponse> {
  const res = await api.post<ValidateExpressionResponse>(`${BASE}/validate`, { expression })
  return res.data
}

export async function simulatePolicy(
  payload: SimulatePolicyPayload
): Promise<SimulatePolicyResponse> {
  const res = await api.post<SimulatePolicyResponse>(`${BASE}/simulate`, payload)
  return res.data
}

export async function seedPolicies(): Promise<SeedPoliciesResponse> {
  const res = await api.post<SeedPoliciesResponse>(`${BASE}/seed`)
  return res.data
}
