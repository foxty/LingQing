import { useQuery } from '@tanstack/react-query'
import {
  getAgentUsageDaily,
  getAgentUsageEvents,
  getAgentUsageSummary,
  type AgentUsageFilterParams,
  type GetAgentUsageEventsParams,
} from '@/lib/agentsApi'
import { useAuth } from './useAuth'

export function useAgentUsageSummary(
  agentId: number | undefined,
  params: AgentUsageFilterParams = {},
  enabled = true
) {
  const { user } = useAuth()
  const days = params.days ?? 30

  return useQuery({
    queryKey: ['agent-usage-summary', user?.tenantId, agentId, days, params.user_id],
    queryFn: () => getAgentUsageSummary(agentId!, params),
    enabled: enabled && !!user && agentId !== undefined,
  })
}

export function useAgentUsageDaily(
  agentId: number | undefined,
  params: AgentUsageFilterParams = {},
  enabled = true
) {
  const { user } = useAuth()
  const days = params.days ?? 30

  return useQuery({
    queryKey: ['agent-usage-daily', user?.tenantId, agentId, days, params.user_id],
    queryFn: () => getAgentUsageDaily(agentId!, params),
    enabled: enabled && !!user && agentId !== undefined,
  })
}

export function useAgentUsageEvents(
  agentId: number | undefined,
  params: GetAgentUsageEventsParams,
  enabled = true
) {
  const { user } = useAuth()
  return useQuery({
    queryKey: [
      'agent-usage-events',
      user?.tenantId,
      agentId,
      params.start_time,
      params.end_time,
      params.page,
      params.page_size,
      params.user_id,
    ],
    queryFn: () => getAgentUsageEvents(agentId!, params),
    enabled: enabled && !!user && agentId !== undefined,
  })
}
