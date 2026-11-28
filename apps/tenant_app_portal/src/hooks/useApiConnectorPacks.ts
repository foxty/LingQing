import { useMutation, useQuery } from '@tanstack/react-query'
import { installApiConnectorPack, listApiConnectorPacks } from '@/lib/apiConnectorApi'

export interface InstallApiConnectorPackInput {
  pack_id: string
  client_id?: string
  client_secret?: string
  redirect_uri?: string
}

export function useApiConnectorPacks(enabled = true) {
  const packsQuery = useQuery({
    queryKey: ['api-connector-packs'],
    queryFn: listApiConnectorPacks,
    enabled,
  })
  const installMutation = useMutation<
    Awaited<ReturnType<typeof installApiConnectorPack>>,
    unknown,
    InstallApiConnectorPackInput
  >({
    mutationFn: installApiConnectorPack,
  })

  return {
    packs: packsQuery.data ?? [],
    packsLoading: packsQuery.isLoading,
    installPack: installMutation.mutateAsync,
    installing: installMutation.isPending,
  }
}
