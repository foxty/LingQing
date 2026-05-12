import { useMutation } from '@tanstack/react-query'

import { search, type SearchParams, type SearchResponse } from '@/lib/searchApi'

export function useSearchQuality() {
  return useMutation<SearchResponse, Error, SearchParams>({
    mutationFn: (params) => search(params),
  })
}
