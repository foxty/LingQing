import { fetchThinkingEffortControl } from '@/lib/chatApi'
import type { AgentCapabilityConfig } from '@/lib/agentsApi'
import { useQuery } from '@tanstack/react-query'

export function useAgentThinkingEffortControl(
  agentId: number,
  _agentConfig?: AgentCapabilityConfig
) {
  const query = useQuery({
    queryKey: ['thinking-effort-control', agentId],
    queryFn: () => fetchThinkingEffortControl(agentId),
    enabled: Number.isFinite(agentId) && agentId !== 0,
    staleTime: 60_000,
  })

  return {
    thinkingEffortControlEnabled: query.data?.enabled ?? false,
    loading: query.isLoading,
  }
}
