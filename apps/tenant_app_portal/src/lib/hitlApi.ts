import api from './api'

export interface HitlApprovalActionRequest {
  version: number
  comment?: string
}

export interface HitlApprovalActionResponse {
  proposal_id: string
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'executed' | 'cancelled'
  version: number
  needs_agent_resume?: boolean
  ack_message?: string | null
}

export interface HitlApprovalResponse {
  proposal_id: string
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'executed' | 'cancelled'
  version: number
  thread_id: string
  tool_name: string
  tool_args: Record<string, any>
  risk_level: string
  reason?: string
  expires_at?: string
  approved_by?: number
  approved_at?: string
  rejected_by?: number
  rejected_at?: string
  created_at?: string
  updated_at?: string
}

export async function getHitlApproval(proposalId: string): Promise<HitlApprovalResponse> {
  const response = await api.get<HitlApprovalResponse>(`/hitl/approvals/${proposalId}`)
  return response.data
}

export async function approveHitlApproval(
  proposalId: string,
  payload: HitlApprovalActionRequest
): Promise<HitlApprovalActionResponse> {
  const response = await api.post<HitlApprovalActionResponse>(
    `/hitl/approvals/${proposalId}/approve`,
    payload
  )
  return response.data
}

export async function rejectHitlApproval(
  proposalId: string,
  payload: HitlApprovalActionRequest
): Promise<HitlApprovalActionResponse> {
  const response = await api.post<HitlApprovalActionResponse>(
    `/hitl/approvals/${proposalId}/reject`,
    payload
  )
  return response.data
}
