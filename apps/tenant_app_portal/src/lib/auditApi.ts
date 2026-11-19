import api from './api'

export interface AuditEventDTO {
  id: number
  tenant_id: number
  actor_user_id: number | null
  actor_type: string | null
  event_type: string
  outcome: string | null
  client_ip: string | null
  user_agent: string | null
  request_id: string | null
  resource_type: string | null
  resource_id: string | null
  payload: Record<string, unknown> | null
  created_at: string
}

export interface AuditEventListResponse {
  items: AuditEventDTO[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ListAuditEventsParams {
  actor_user_id?: number
  event_type?: string
  from?: string
  to?: string
  page?: number
  page_size?: number
}

export async function listAuditEvents(params: ListAuditEventsParams = {}): Promise<AuditEventListResponse> {
  const res = await api.get<AuditEventListResponse>('/audit/events', { params })
  return res.data
}

export interface AuditEventTypesResponse {
  items: string[]
}

export async function listAuditEventTypes(): Promise<AuditEventTypesResponse> {
  const res = await api.get<AuditEventTypesResponse>('/audit/event-types')
  return res.data
}

export async function exportAuditEvents(params: ListAuditEventsParams = {}): Promise<{
  blob: Blob
  truncated: boolean
  totalMatched: number
  exportedCount: number
}> {
  const res = await api.get<Blob>('/audit/events/export', {
    params,
    responseType: 'blob',
  })
  const truncated = res.headers['x-audit-truncated'] === 'true'
  const totalMatched = Number(res.headers['x-audit-total-matched'] ?? 0)
  const exportedCount = Number(res.headers['x-audit-exported-count'] ?? 0)
  return { blob: res.data, truncated, totalMatched, exportedCount }
}

export function formatAuditPayload(payload: Record<string, unknown> | null | undefined): string {
  if (!payload || Object.keys(payload).length === 0) {
    return ''
  }
  try {
    return JSON.stringify(payload)
  } catch {
    return ''
  }
}