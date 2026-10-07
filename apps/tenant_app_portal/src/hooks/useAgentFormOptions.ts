import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { listAgentSkillCatalog } from '@/lib/agentsApi'
import { listApiConnectors } from '@/lib/apiConnectorApi'
import { listDocumentCollections } from '@/lib/documentCollectionsApi'
import { listDataSources } from '@/lib/dataSourceApi'
import { listRegistryProfiles } from '@/lib/llmConfigApi'

export function useAgentFormOptions(enabled = true) {
  const { user } = useAuth()
  const canFetch = enabled && !!user

  const skillsQuery = useQuery({
    queryKey: ['agent-skill-catalog', user?.tenantId],
    queryFn: listAgentSkillCatalog,
    enabled: canFetch,
  })
  const collectionsQuery = useQuery({
    queryKey: ['document-collections', user?.tenantId],
    queryFn: listDocumentCollections,
    enabled: canFetch,
  })
  const dataSourcesQuery = useQuery({
    queryKey: ['agent-data-sources'],
    queryFn: async () => (await listDataSources(1, 100)).items ?? [],
    enabled: canFetch,
  })
  const connectorsQuery = useQuery({
    queryKey: ['agent-api-connectors'],
    queryFn: listApiConnectors,
    enabled: canFetch,
  })
  const llmProfilesQuery = useQuery({
    queryKey: ['llm-profiles', 'llm'],
    queryFn: () => listRegistryProfiles('llm'),
    enabled: canFetch,
  })

  return {
    skills: skillsQuery.data ?? [],
    collections: collectionsQuery.data ?? [],
    dataSources: dataSourcesQuery.data ?? [],
    connectors: connectorsQuery.data ?? [],
    llmProfiles: llmProfilesQuery.data ?? [],
    isLoading:
      skillsQuery.isLoading ||
      collectionsQuery.isLoading ||
      dataSourcesQuery.isLoading ||
      connectorsQuery.isLoading ||
      llmProfilesQuery.isLoading,
  }
}
