import { useMutation } from '@tanstack/react-query'
import { startMyApiConnectorOAuth } from '@/lib/apiConnectorApi'
import { startMyDataSourceOAuth } from '@/lib/dataSourceApi'

type ResourceKind = 'api_connector' | 'data_source'

export function useIntegrationOAuth(resourceKind: ResourceKind) {
  const startMutation = useMutation({
    mutationFn: (resourceId: number) =>
      resourceKind === 'data_source'
        ? startMyDataSourceOAuth(resourceId)
        : startMyApiConnectorOAuth(resourceId),
  })

  return {
    startOAuth: startMutation.mutateAsync,
    starting: startMutation.isPending,
  }
}