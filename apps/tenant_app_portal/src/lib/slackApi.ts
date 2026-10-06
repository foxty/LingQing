import api from './api'

export interface SlackIntegration {
  id: number
  tenant_id: number
  agent_id: number
  slack_team_id: string | null
  slack_team_name: string | null
  slack_app_id: string | null
  bot_user_id: string | null
  bot_token_configured: boolean
  signing_secret_configured: boolean
  default_agent_id: number
  enabled: boolean
  endpoint_key: string
  events_url: string
  interactions_url: string
}

export interface CreateAgentSlackIntegrationRequest {
  bot_token: string
  signing_secret: string
  enabled?: boolean
}

export interface UpdateAgentSlackIntegrationRequest {
  bot_token?: string
  signing_secret?: string
  enabled?: boolean
}

export interface SlackTestConnectionResponse {
  ok: boolean
  team_id?: string | null
  team_name?: string | null
  bot_user_id?: string | null
  error?: string | null
}

export async function listSlackIntegrations(): Promise<SlackIntegration[]> {
  const res = await api.get<SlackIntegration[]>('/integrations/slack/endpoints')
  return res.data
}

export async function getAgentSlackIntegration(agentId: number): Promise<SlackIntegration | null> {
  const res = await api.get<SlackIntegration>(`/agents/${agentId}/integrations/slack`, {
    validateStatus: (status) => status === 200 || status === 204,
  })
  if (res.status === 204) return null
  return res.data
}

export async function prepareAgentSlackIntegration(agentId: number): Promise<SlackIntegration> {
  const res = await api.post<SlackIntegration>(`/agents/${agentId}/integrations/slack/prepare`)
  return res.data
}

export async function createAgentSlackIntegration(
  agentId: number,
  payload: CreateAgentSlackIntegrationRequest
): Promise<SlackIntegration> {
  const res = await api.post<SlackIntegration>(`/agents/${agentId}/integrations/slack`, payload)
  return res.data
}

export async function updateAgentSlackIntegration(
  agentId: number,
  payload: UpdateAgentSlackIntegrationRequest
): Promise<SlackIntegration> {
  const res = await api.patch<SlackIntegration>(`/agents/${agentId}/integrations/slack`, payload)
  return res.data
}

export async function deleteAgentSlackIntegration(agentId: number): Promise<void> {
  await api.delete(`/agents/${agentId}/integrations/slack`)
}

export async function enableAgentSlackIntegration(agentId: number): Promise<SlackIntegration> {
  const res = await api.post<SlackIntegration>(`/agents/${agentId}/integrations/slack/enable`)
  return res.data
}

export async function disableAgentSlackIntegration(agentId: number): Promise<SlackIntegration> {
  const res = await api.post<SlackIntegration>(`/agents/${agentId}/integrations/slack/disable`)
  return res.data
}

export async function testAgentSlackConnection(agentId: number): Promise<SlackTestConnectionResponse> {
  const res = await api.post<SlackTestConnectionResponse>(`/agents/${agentId}/integrations/slack/test`)
  return res.data
}

export async function downloadAgentSlackAppManifest(agentId: number): Promise<void> {
  const res = await api.get<Blob>(`/agents/${agentId}/integrations/slack/manifest`, {
    responseType: 'blob',
  })
  downloadManifestBlob(res.data, res.headers['content-disposition'] as string | undefined)
}

function downloadManifestBlob(blob: Blob, disposition?: string) {
  const match = disposition?.match(/filename="([^"]+)"/)
  const filename = match?.[1] ?? 'lingqing-slack-manifest.json'
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
