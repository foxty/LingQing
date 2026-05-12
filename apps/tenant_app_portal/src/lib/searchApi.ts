import api from './api'

export const SEARCH_TARGET_DOCUMENT = 'document' as const
export const SEARCH_TARGET_ASSET = 'asset' as const
export const SEARCH_TARGET_API_CONNECTOR = 'api_connector' as const

export const SEARCH_TARGETS = [
  SEARCH_TARGET_DOCUMENT,
  SEARCH_TARGET_ASSET,
  SEARCH_TARGET_API_CONNECTOR,
] as const

export type SearchSource = (typeof SEARCH_TARGETS)[number]

export const SEARCH_ITEM_TYPE_DOCUMENT = 'document' as const
export const SEARCH_ITEM_TYPE_ASSET = 'asset' as const
export const SEARCH_ITEM_TYPE_API_CONNECTOR = 'api_connector' as const
export const SEARCH_ITEM_TYPES = [
  SEARCH_ITEM_TYPE_DOCUMENT,
  SEARCH_ITEM_TYPE_ASSET,
  SEARCH_ITEM_TYPE_API_CONNECTOR,
] as const
export type SearchItemType = (typeof SEARCH_ITEM_TYPES)[number]

export interface SearchDataSourceMeta {
  id?: number
  name?: string
  type?: string
}

export interface SearchResultItem {
  resource_type: SearchItemType
  resource_id: number | string
  title: string
  score?: number | null
  source?: 'fts' | 'vector' | 'hybrid' | null
  snippet?: string | null
  contents?: Array<Record<string, unknown>>
}

export interface SearchResponse {
  items: SearchResultItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

export interface SearchParams {
  query: string
  sources?: SearchSource[]
  page?: number
  page_size?: number
}

export async function search(params: SearchParams): Promise<SearchResponse> {
  const searchParams = new URLSearchParams()
  searchParams.append('query', params.query)

  if (params.sources?.length) {
    params.sources.forEach((source) => {
      searchParams.append('sources', source)
    })
  }

  if (params.page !== undefined) {
    searchParams.append('page', String(params.page))
  }

  if (params.page_size !== undefined) {
    searchParams.append('page_size', String(params.page_size))
  }

  const response = await api.get<SearchResponse>('/search', {
    params: searchParams,
    paramsSerializer: (value) => value.toString(),
  })
  return response.data
}