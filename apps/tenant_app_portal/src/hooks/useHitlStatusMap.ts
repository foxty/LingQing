import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Message } from '@/types'
import {
  collectHitlProposalIds,
  fetchHitlStatusMap,
  type HitlStatusMap,
} from '@/lib/hitlStatus'

export function useHitlStatusMap(messages: Message[], enabled = true) {
  const proposalIds = useMemo(() => collectHitlProposalIds(messages), [messages])
  const proposalKey = proposalIds.slice().sort().join(',')

  return useQuery<HitlStatusMap>({
    queryKey: ['hitlStatusMap', proposalKey],
    queryFn: () => fetchHitlStatusMap(proposalIds),
    enabled: enabled && proposalIds.length > 0,
    staleTime: 30_000,
  })
}
