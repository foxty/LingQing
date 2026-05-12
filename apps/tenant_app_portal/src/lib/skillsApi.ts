import api from './api'
import type { ApiSkill } from '@/types'

export interface SkillListResponse {
  items: ApiSkill[]
  total: number
}

export interface EnvVarResponse {
  env_vars: Record<string, string>
}

// GET /skills?type=builtin|tenant|personal
export async function getSkills(type?: string) {
  const params: Record<string, string | number> = {}
  if (type) params.type = type
  const response = await api.get<SkillListResponse>('/skills', { params })
  return response.data
}

// GET /skills/{name}
export async function getSkill(name: string) {
  const response = await api.get<ApiSkill>(`/skills/${encodeURIComponent(name)}`)
  return response.data
}

// POST /skills?type=tenant|personal  (multipart/form-data)
export async function createSkill(type: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await api.post<{ name: string; type: string; message: string }>(`/skills?type=${type}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

// POST /skills/import?type=tenant|personal
export async function importSkill(type: string, url: string) {
  const response = await api.post<{ name: string; type: string; message: string }>(
    `/skills/import?type=${type}`,
    { url },
  )
  return response.data
}

// DELETE /skills/{name}?type=tenant|personal
export async function deleteSkill(name: string, type: string) {
  await api.delete(`/skills/${encodeURIComponent(name)}`, { params: { type } })
}

// PATCH /skills/{scope}/{name}/enabled
export async function toggleSkillEnabled(scope: string, name: string, enabled: boolean) {
  const response = await api.patch<{ name: string; type: string; enabled: boolean }>(
    `/skills/${scope}/${encodeURIComponent(name)}/enabled`,
    { enabled },
  )
  return response.data
}

// GET /skills/{scope}/{name}/env-vars
export async function getEnvVars(scope: string, name: string) {
  const response = await api.get<EnvVarResponse>(`/skills/${scope}/${encodeURIComponent(name)}/env-vars`)
  return response.data
}

// PUT /skills/{scope}/{name}/env-vars
export async function updateEnvVars(scope: string, name: string, envVars: Record<string, string>) {
  const response = await api.put<EnvVarResponse>(
    `/skills/${scope}/${encodeURIComponent(name)}/env-vars`,
    { env_vars: envVars },
  )
  return response.data
}
