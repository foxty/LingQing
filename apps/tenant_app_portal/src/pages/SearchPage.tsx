import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Search as SearchIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  search: {
    title: 'Search',
    description: 'Search across documents, datasets, and API connectors',
    placeholder: 'Search...',
    searchType: 'Type',
    count: 'Count',
    itemCount: '{{count}} results',
    searchFailed: 'Search failed: {{error}}',
    searching: 'Searching...',
    noResults: 'No results found',
    allTypes: 'All Types',
    documents: 'Documents',
    datasets: 'Datasets',
    resultName: 'Name',
    resultType: 'Type',
    resultScore: 'Score',
    resultSource: 'Source',
    resultSummary: 'Summary',
    resultDataSource: 'Data Source',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  search: {
    title: '搜索',
    description: '搜索文档、数据集和API连接器',
    placeholder: '搜索...',
    searchType: '类型',
    count: '数量',
    itemCount: '{{count}}条结果',
    searchFailed: '搜索失败：{{error}}',
    searching: '搜索中...',
    noResults: '未找到结果',
    allTypes: '全部类型',
    documents: '文档',
    datasets: '数据集',
    resultName: '名称',
    resultType: '类型',
    resultScore: '分数',
    resultSource: '来源',
    resultSummary: '摘要',
    resultDataSource: '数据源',
  }
}, true, true)

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import TagChips from '@/components/TagChips'
import { useAuth } from '@/hooks/useAuth'
import { useSearchQuality } from '@/hooks/useSearchQuality'
import { actionRules } from '@/lib/permissionRules'
import {
  SEARCH_ITEM_TYPE_API_CONNECTOR,
  SEARCH_ITEM_TYPE_ASSET,
  SEARCH_ITEM_TYPE_DOCUMENT,
  SEARCH_TARGET_API_CONNECTOR,
  SEARCH_TARGET_ASSET,
  SEARCH_TARGET_DOCUMENT,
  type SearchResultItem,
  type SearchSource,
} from '@/lib/searchApi'
import { listTagKeys, listTagsForResource, TAG_RESOURCE_TYPES, type TagKeyDTO, type TagValueDTO } from '@/lib/tagsApi'

const SEARCH_SCOPE_ALL = 'all' as const
type SearchScope = SearchSource | typeof SEARCH_SCOPE_ALL

function getSearchTypes(t: (key: string) => string) {
  return [
    {
      label: t('search.allTypes'),
      value: SEARCH_SCOPE_ALL,
      sources: [SEARCH_TARGET_DOCUMENT, SEARCH_TARGET_ASSET, SEARCH_TARGET_API_CONNECTOR],
    },
    { label: t('search.documents'), value: SEARCH_TARGET_DOCUMENT, sources: [SEARCH_TARGET_DOCUMENT] },
    { label: t('search.datasets'), value: SEARCH_TARGET_ASSET, sources: [SEARCH_TARGET_ASSET] },
    { label: 'API', value: SEARCH_TARGET_API_CONNECTOR, sources: [SEARCH_TARGET_API_CONNECTOR] },
  ]
}

const LIMIT_OPTIONS = [5, 10, 20]

export default function SearchPage() {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [searchScope, setSearchScope] = useState<SearchScope>(SEARCH_SCOPE_ALL)
  const [pageSize, setPageSize] = useState(10)
  const [tagKeys, setTagKeys] = useState<TagKeyDTO[]>([])
  const [resultTags, setResultTags] = useState<Record<string, TagValueDTO[]>>({})

  const { hasAny } = useAuth()
  const canReadTags = hasAny(actionRules.canReadTags())

  const searchMutation = useSearchQuality()

  const results = useMemo<SearchResultItem[]>(() => {
    return searchMutation.data?.items ?? []
  }, [searchMutation.data])

  const getResultKey = (item: SearchResultItem): string =>
    `${item.resource_type}-${String(item.resource_id)}`

  const getTagResourceId = (item: SearchResultItem): number | null => {
    const content = item.contents?.[0] as Record<string, unknown> | undefined
    if (!content) {
      return null
    }

    if (item.resource_type === SEARCH_ITEM_TYPE_DOCUMENT) {
      const collectionId = content.collection_id
      return typeof collectionId === 'number' ? collectionId : null
    }

    if (item.resource_type === SEARCH_ITEM_TYPE_ASSET) {
      const dataSource = content.data_source as { id?: number } | undefined
      return typeof dataSource?.id === 'number' ? dataSource.id : null
    }

    if (item.resource_type === SEARCH_ITEM_TYPE_API_CONNECTOR) {
      const connectorId = content.connector_id
      return typeof connectorId === 'number' ? connectorId : null
    }

    return null
  }

  const getDataSourceLabel = (item: SearchResultItem): string => {
    if (item.resource_type === SEARCH_ITEM_TYPE_DOCUMENT) {
      return '--'
    }

    if (item.resource_type === SEARCH_ITEM_TYPE_API_CONNECTOR) {
      const content = item.contents?.[0] as { connector_name?: string } | undefined
      return content?.connector_name || '--'
    }

    const content = item.contents?.[0] as Record<string, unknown> | undefined
    const dataSource = content?.data_source as { name?: string; type?: string } | undefined
    const assetType = typeof content?.asset_type === 'string' ? content.asset_type : undefined

    if (!dataSource?.name) {
      return assetType ?? '--'
    }
    return assetType ? `${dataSource.name} • ${assetType}` : dataSource.name
  }

  useEffect(() => {
    if (!canReadTags) return
    listTagKeys()
      .then(setTagKeys)
      .catch(() => undefined)
  }, [canReadTags])

  useEffect(() => {
    if (!canReadTags || results.length === 0) {
      setResultTags({})
      return
    }

    Promise.all(
      results.map(async (item) => {
        const resourceType =
          item.resource_type === SEARCH_ITEM_TYPE_DOCUMENT
            ? TAG_RESOURCE_TYPES.DOCUMENT_COLLECTION
            : item.resource_type === SEARCH_ITEM_TYPE_ASSET
              ? TAG_RESOURCE_TYPES.DATA_SOURCE
              : TAG_RESOURCE_TYPES.API_CONNECTOR
        const resourceId = getTagResourceId(item)
        if (resourceId === null) {
          return { key: getResultKey(item), tags: [] }
        }
        try {
          const tags = await listTagsForResource(resourceType, resourceId)
          return { key: getResultKey(item), tags }
        } catch {
          return { key: getResultKey(item), tags: [] }
        }
      })
    )
      .then((items) => {
        const next: Record<string, TagValueDTO[]> = {}
        items.forEach(({ key, tags }) => {
          next[key] = tags
        })
        setResultTags(next)
      })
      .catch(() => undefined)
  }, [canReadTags, results])

  const searchTypes = useMemo(() => getSearchTypes(t), [t])

  const handleSearch = async () => {
    const trimmed = query.trim()
    if (!trimmed) return
    const selectedSources = searchTypes.find((option) => option.value === searchScope)
      ?.sources ?? [SEARCH_TARGET_DOCUMENT, SEARCH_TARGET_ASSET, SEARCH_TARGET_API_CONNECTOR]

    await searchMutation.mutateAsync({
      query: trimmed,
      sources: selectedSources,
      page: 1,
      page_size: pageSize,
    })
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t('search.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('search.description')}</p>
      </div>

      <div className="flex flex-col gap-3 rounded-lg border bg-muted/50 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative w-72">
            <SearchIcon className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t('search.placeholder')}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  handleSearch()
                }
              }}
              className="pl-8 h-9"
            />
          </div>

          <Select
            value={searchScope}
            onValueChange={(value) => setSearchScope(value as SearchScope)}
          >
            <SelectTrigger className="w-40">
              <SelectValue placeholder={t('search.searchType')} />
            </SelectTrigger>
            <SelectContent>
              {searchTypes.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={String(pageSize)} onValueChange={(value) => setPageSize(Number(value))}>
            <SelectTrigger className="w-28">
              <SelectValue placeholder={t('search.count')} />
            </SelectTrigger>
            <SelectContent>
              {LIMIT_OPTIONS.map((option) => (
                <SelectItem key={option} value={String(option)}>
                  {t('search.itemCount', { count: option })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button onClick={handleSearch} disabled={searchMutation.isPending}>
            {t('common.search')}
          </Button>
        </div>

        {searchMutation.error && (
          <div className="text-sm text-red-600">{t('search.searchFailed', { error: searchMutation.error.message })}</div>
        )}
      </div>

      <div className="overflow-hidden rounded-lg border bg-card">
        <Table>
          <TableHeader>
              <TableRow>
                <TableHead>{t('search.resultName')}</TableHead>
                <TableHead className="w-28">{t('search.resultType')}</TableHead>
                <TableHead className="w-24">{t('search.resultScore')}</TableHead>
                <TableHead className="w-20">{t('search.resultSource')}</TableHead>
                <TableHead>{t('search.resultSummary')}</TableHead>
                <TableHead className="w-56">{t('search.resultDataSource')}</TableHead>
              </TableRow>
          </TableHeader>
          <TableBody>
            {searchMutation.isPending && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  {t('search.searching')}
                </TableCell>
              </TableRow>
            )}
            {!searchMutation.isPending && results.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  {t('search.noResults')}
                </TableCell>
              </TableRow>
            )}
            {results.map((item) => (
              <TableRow key={getResultKey(item)}>
                <TableCell className="font-medium">
                  <div className="flex flex-col gap-1">
                    <span>{item.title}</span>
                    {canReadTags && (resultTags[getResultKey(item)]?.length || 0) > 0 && (
                      <TagChips tags={resultTags[getResultKey(item)]} tagKeys={tagKeys} compact />
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  {item.resource_type === SEARCH_ITEM_TYPE_DOCUMENT
                    ? t('search.documents')
                    : item.resource_type === SEARCH_ITEM_TYPE_ASSET
                      ? t('search.datasets')
                      : item.resource_type === SEARCH_ITEM_TYPE_API_CONNECTOR
                        ? 'API'
                        : '--'}
                </TableCell>
                <TableCell>
                  {item.score !== null && item.score !== undefined ? item.score.toFixed(4) : '--'}
                </TableCell>
                <TableCell>{item.source || '--'}</TableCell>
                <TableCell className="text-muted-foreground">{item.snippet || '--'}</TableCell>
                <TableCell className="text-muted-foreground">{getDataSourceLabel(item)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}