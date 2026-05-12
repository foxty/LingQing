import { useQuery } from '@tanstack/react-query'
import { useAuth } from './useAuth'
import {
  getTenantTokenDaily,
  getTenantTokenSummary,
  getTenantUsageEvents,
  type GetTenantUsageEventsParams,
  type TenantTokenFilterParams,
  type TenantTokenSummary,
  type TokenUsageDailyPoint,
  type TokenUsageEventsResponse,
} from '@/lib/tenantApi'

export function useTenantTokenSummary(params: TenantTokenFilterParams = {}) {
  const { user } = useAuth()
  const days = params.days ?? 30

  return useQuery<TenantTokenSummary>({
    queryKey: ['tenant-token-summary', user?.tenantId, days, params.user_id, params.agent_id],
    queryFn: () => getTenantTokenSummary(params),
    enabled: !!user,
    retry: 1,
  })
}

export function useTenantTokenDaily(params: TenantTokenFilterParams = {}) {
  const { user } = useAuth()
  const days = params.days ?? 30

  return useQuery<TokenUsageDailyPoint[]>({
    queryKey: ['tenant-token-daily', user?.tenantId, days, params.user_id, params.agent_id],
    queryFn: () => getTenantTokenDaily(params),
    enabled: !!user,
    retry: 1,
  })
}

export function useTenantUsageEvents(params: GetTenantUsageEventsParams) {
  const { user } = useAuth()

  return useQuery<TokenUsageEventsResponse>({
    queryKey: [
      'tenant-usage-events',
      user?.tenantId,
      params.start_time,
      params.end_time,
      params.page,
      params.page_size,
      params.user_id,
      params.agent_id,
    ],
    queryFn: () => getTenantUsageEvents(params),
    enabled: !!user,
    retry: 1,
  })
}
