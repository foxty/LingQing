import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import i18n from '@/i18n/config'
import {
  agentApiErrorMessage,
  createCatalogAgent,
  deleteCatalogAgent,
  listAgentSkillCatalog,
  listCatalogAgents,
  updateCatalogAgent,
  type AgentWritePayload,
  type CatalogAgent,
} from '@/lib/agentsApi'
import { useAuth } from './useAuth'
import { useNotification } from './useNotification'

export function useAgents() {
  const { user } = useAuth()

  return useQuery<CatalogAgent[]>({
    queryKey: ['agents', user?.tenantId],
    queryFn: listCatalogAgents,
    enabled: !!user,
  })
}

export function useAgentSkillCatalog() {
  const { user } = useAuth()
  return useQuery({
    queryKey: ['agent-skill-catalog', user?.tenantId],
    queryFn: listAgentSkillCatalog,
    enabled: !!user,
  })
}

export function useCreateAgent() {
  const queryClient = useQueryClient()
  const { showError } = useNotification()
  return useMutation({
    mutationFn: (payload: AgentWritePayload) => createCatalogAgent(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
    onError: (error: unknown) => {
      showError(agentApiErrorMessage(error, i18n.t('agents.saveFailed')))
    },
  })
}

export function useUpdateAgent() {
  const queryClient = useQueryClient()
  const { showError } = useNotification()
  return useMutation({
    mutationFn: ({ agentId, payload }: { agentId: number; payload: Partial<AgentWritePayload> }) =>
      updateCatalogAgent(agentId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
    onError: (error: unknown) => {
      showError(agentApiErrorMessage(error, i18n.t('agents.saveFailed')))
    },
  })
}

export function useDeleteAgent() {
  const queryClient = useQueryClient()
  const { showError } = useNotification()
  return useMutation({
    mutationFn: (agentId: number) => deleteCatalogAgent(agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
    onError: (error: unknown) => {
      showError(agentApiErrorMessage(error, i18n.t('agents.deleteFailed')))
    },
  })
}
