import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import i18n from '@/i18n/config'
import { getApiErrorMessage } from '@/lib/api'
import {
  getSkills,
  createSkill,
  importSkill,
  deleteSkill,
  getEnvVars,
  updateEnvVars,
  toggleSkillEnabled,
} from '@/lib/skillsApi'
import { convertApiSkillToSkill } from '@/types'

export function useSkills(type?: string) {
  const { user } = useAuth()
  return useQuery({
    queryKey: ['skills', user?.tenantId, type],
    queryFn: async () => {
      const response = await getSkills(type)
      return {
        items: response.items.map(convertApiSkillToSkill),
        total: response.total,
      }
    },
    enabled: !!user,
  })
}

export function useCreateSkill() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showError } = useNotification()
  return useMutation({
    mutationFn: async ({ type, file }: { type: string; file: File }) => {
      return await createSkill(type, file)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills', user?.tenantId] })
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('skills.createFailed')))
    },
  })
}

export function useImportSkill() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showError } = useNotification()
  return useMutation({
    mutationFn: async ({ type, url }: { type: string; url: string }) => {
      return await importSkill(type, url)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills', user?.tenantId] })
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('skills.importFailed')))
    },
  })
}

export function useToggleSkillEnabled() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showError } = useNotification()
  return useMutation({
    mutationFn: async ({ scope, name, enabled }: { scope: string; name: string; enabled: boolean }) => {
      return await toggleSkillEnabled(scope, name, enabled)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills', user?.tenantId] })
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('skills.toggleFailed')))
    },
  })
}

export function useDeleteSkill() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showError } = useNotification()
  return useMutation({
    mutationFn: async ({ name, type }: { name: string; type: string }) => {
      await deleteSkill(name, type)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills', user?.tenantId] })
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('skills.deleteFailed')))
    },
  })
}

export function useSkillEnvVars(scope: string, name: string | undefined) {
  const { user } = useAuth()
  return useQuery({
    queryKey: ['skills', user?.tenantId, scope, name, 'env-vars'],
    queryFn: async () => {
      const response = await getEnvVars(scope, name!)
      return response.env_vars
    },
    enabled: !!user && !!name,
  })
}

export function useUpdateEnvVars(scope: string, name: string | undefined) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showError } = useNotification()
  return useMutation({
    mutationFn: async (envVars: Record<string, string>) => {
      return await updateEnvVars(scope, name!, envVars)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills', user?.tenantId, scope, name, 'env-vars'] })
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('skills.envVarsFailed')))
    },
  })
}
