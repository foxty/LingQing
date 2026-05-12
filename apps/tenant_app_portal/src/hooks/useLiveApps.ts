import { useQuery } from '@tanstack/react-query'

import { listLiveApps, type LiveApp } from '@/lib/liveAppsApi'

export function useLiveApps() {
  return useQuery<LiveApp[]>({
    queryKey: ['live-apps'],
    queryFn: () => listLiveApps(),
  })
}
