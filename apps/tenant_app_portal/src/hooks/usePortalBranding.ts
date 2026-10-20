import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { readCachedPortalBranding, writeCachedPortalBranding } from '@/lib/portalBrandingCache'
import i18n from '@/i18n/config'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { getApiErrorMessage } from '@/lib/api'
import {
  deletePortalLogo,
  getPortalBranding,
  updatePortalBranding,
  uploadPortalLogo,
  type PortalBranding,
  type UpdatePortalBrandingPayload,
} from '@/lib/portalBrandingApi'

export function usePortalBranding() {
  const { user } = useAuth()
  const tenantId = user?.tenantId

  const query = useQuery<PortalBranding>({
    queryKey: ['portal-branding', tenantId],
    queryFn: getPortalBranding,
    enabled: tenantId != null,
    staleTime: 5 * 60 * 1000,
    initialData: () => (tenantId != null ? readCachedPortalBranding(tenantId) : undefined),
  })

  useEffect(() => {
    if (tenantId != null && query.data) {
      writeCachedPortalBranding(tenantId, query.data)
    }
  }, [tenantId, query.data])

  return query
}

function persistBrandingCache(
  queryClient: ReturnType<typeof useQueryClient>,
  tenantId: number | undefined,
  data: PortalBranding
) {
  if (tenantId === undefined) {
    return
  }
  queryClient.setQueryData(['portal-branding', tenantId], data)
  writeCachedPortalBranding(tenantId, data)
}

export function useUpdatePortalBranding() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (payload: UpdatePortalBrandingPayload) => updatePortalBranding(payload),
    onSuccess: (data) => {
      persistBrandingCache(queryClient, user?.tenantId, data)
      queryClient.invalidateQueries({ queryKey: ['portal-branding'] })
      showSuccess(i18n.t('settings.appearanceTab.saveSuccess'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('settings.appearanceTab.saveFailed')))
    },
  })
}

export function useUploadPortalLogo() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (file: File) => uploadPortalLogo(file),
    onSuccess: (data) => {
      persistBrandingCache(queryClient, user?.tenantId, data)
      queryClient.invalidateQueries({ queryKey: ['portal-branding'] })
      showSuccess(i18n.t('settings.appearanceTab.logoSaved'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('settings.appearanceTab.logoFailed')))
    },
  })
}

export function useDeletePortalLogo() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: () => deletePortalLogo(),
    onSuccess: (data) => {
      persistBrandingCache(queryClient, user?.tenantId, data)
      queryClient.invalidateQueries({ queryKey: ['portal-branding'] })
      showSuccess(i18n.t('settings.appearanceTab.logoRemoved'))
    },
    onError: (error: unknown) => {
      showError(getApiErrorMessage(error, i18n.t('settings.appearanceTab.logoFailed')))
    },
  })
}
