import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { getCatalogAgent, listAgentSkillCatalog, SYSTEM_AGENT_ONE_ID } from '@/lib/agentsApi'
import { listRegistryProfiles } from '@/lib/llmConfigApi'

export function useAgentFormOptions(enabled = true) {
  const { user } = useAuth()
  const canFetch = enabled && !!user

  const skillsQuery = useQuery({
    queryKey: ['agent-skill-catalog', user?.tenantId],
    queryFn: listAgentSkillCatalog,
    enabled: canFetch,
  })
  const llmProfilesQuery = useQuery({
    queryKey: ['llm-profiles', 'llm'],
    queryFn: () => listRegistryProfiles('llm'),
    enabled: canFetch,
  })
  /** Agent One profile carries the platform-effective max loop (hint / create prefill). */
  const platformAgentQuery = useQuery({
    queryKey: ['catalog-agent', SYSTEM_AGENT_ONE_ID, user?.tenantId],
    queryFn: () => getCatalogAgent(SYSTEM_AGENT_ONE_ID),
    enabled: canFetch,
  })

  return {
    skills: skillsQuery.data ?? [],
    llmProfiles: llmProfilesQuery.data ?? [],
    platformMaxLoopIterations: platformAgentQuery.data?.config.max_loop_iterations,
    isLoading:
      skillsQuery.isLoading || llmProfilesQuery.isLoading || platformAgentQuery.isLoading,
  }
}