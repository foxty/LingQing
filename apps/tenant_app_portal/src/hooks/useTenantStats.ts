import { useQuery } from '@tanstack/react-query'
import { useAuth } from './useAuth'
import { getTenantStats, type TenantStats } from '@/lib/tenantApi'

export function useTenantStats() {
  const { user } = useAuth()

  return useQuery<TenantStats>({
    queryKey: ['tenant-stats', user?.tenantId],
    queryFn: getTenantStats,
    enabled: !!user,
    retry: 1,
  })
}
