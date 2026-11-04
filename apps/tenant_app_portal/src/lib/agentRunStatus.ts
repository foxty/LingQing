/** Mirrors backend ``AgentRunStatus`` (``apps.tenant_app_service.chat.domain``). */

export const AGENT_RUN_STATUS = {
  QUEUED: 'queued',
  RUNNING: 'running',
  AWAITING_HITL: 'awaiting_hitl',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const

export type AgentRunStatus = (typeof AGENT_RUN_STATUS)[keyof typeof AGENT_RUN_STATUS]

export const ACTIVE_AGENT_RUN_STATUSES: readonly AgentRunStatus[] = [
  AGENT_RUN_STATUS.QUEUED,
  AGENT_RUN_STATUS.RUNNING,
  AGENT_RUN_STATUS.AWAITING_HITL,
]

export interface TriggerAgentRunSummary {
  run_id: string
  agent_id: number
  invoke_index: number
  session_id: string
  status: AgentRunStatus
}

const ALL_STATUSES: readonly string[] = Object.values(AGENT_RUN_STATUS)

export function isAgentRunStatus(value: string): value is AgentRunStatus {
  return ALL_STATUSES.includes(value)
}

/** Read-time run status stamped on history messages (AI) or derived from ``trigger_runs`` (human). */
export function messageAgentRunStatus(message: {
  message_metadata?: Record<string, unknown> | null
}): AgentRunStatus | undefined {
  const raw = message.message_metadata?.agent_run_status
  if (typeof raw === 'string' && isAgentRunStatus(raw)) {
    return raw
  }
  return undefined
}

export function isActiveRunStatus(status: AgentRunStatus | null | undefined): boolean {
  if (!status) return false
  return (ACTIVE_AGENT_RUN_STATUSES as readonly string[]).includes(status)
}
