import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { listAgentSkillCatalog } from '@/lib/agentsApi'
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

  return {
    skills: skillsQuery.data ?? [],
    llmProfiles: llmProfilesQuery.data ?? [],
    isLoading: skillsQuery.isLoading || llmProfilesQuery.isLoading,
  }
}
