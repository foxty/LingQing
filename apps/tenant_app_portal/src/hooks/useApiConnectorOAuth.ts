import { useMutation } from '@tanstack/react-query'
import { startMyApiConnectorOAuth } from '@/lib/apiConnectorApi'

export function useApiConnectorOAuth() {
  const startMutation = useMutation({
    mutationFn: startMyApiConnectorOAuth,
  })

  return {
    startOAuth: startMutation.mutateAsync,
    starting: startMutation.isPending,
  }
}
