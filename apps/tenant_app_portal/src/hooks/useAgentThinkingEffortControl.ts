import { fetchThinkingEffortControl, type ThinkingEffortOption } from '@/lib/chatApi'
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

  const options: ThinkingEffortOption[] = query.data?.options ?? []
  const defaultValue = query.data?.default_value ?? ''

  return {
    thinkingEffortControlEnabled: query.data?.enabled ?? false,
    thinkingEffortOptions: options,
    defaultThinkingEffortValue: defaultValue,
    agentModelId: query.data?.model_id ?? '',
    agentProfileName: query.data?.profile_name ?? '',
    loading: query.isLoading,
  }
}
