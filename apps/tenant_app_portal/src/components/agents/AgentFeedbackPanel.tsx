import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Download, Loader2, MessageSquare, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react'
import EmptyState from '@/components/EmptyState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useNotification } from '@/hooks/useNotification'
import { useAgents } from '@/hooks/useAgents'
import {
  downloadFeedbackExport,
  useFeedbackList,
  useFeedbackStats,
} from '@/hooks/useMessageFeedbackAnalysis'
import { getApiErrorMessage } from '@/lib/api'
import { formatDate } from '@/lib/dateTime'
import type { FeedbackListItem } from '@/lib/feedbackApi'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    agentFeedback: {
      totalFeedback: 'Total feedback',
      positiveRate: 'Positive rate',
      negativeCount: 'Negative',
      allAgents: 'All agents',
      allSources: 'All sources',
      portal: 'Portal',
      slack: 'Slack',
      allRatings: 'All ratings',
      positive: 'Positive',
      negative: 'Negative',
      exportCsv: 'Export CSV',
      exportFailed: 'Failed to export feedback',
      thread: 'Thread',
      user: 'User',
      agent: 'Agent',
      rating: 'Rating',
      source: 'Source',
      comment: 'Comment',
      preview: 'AI preview',
      createdAt: 'Created',
      noData: 'No feedback yet',
      noDataHint: 'Ratings appear here after users respond to agent messages in the portal or Slack.',
      loadFailed: 'Failed to load feedback data',
      openThread: 'Open conversation',
      loadMore: 'Load more',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    agentFeedback: {
      totalFeedback: '反馈总数',
      positiveRate: '好评率',
      negativeCount: '差评',
      allAgents: '全部智能体',
      allSources: '全部来源',
      portal: '门户',
      slack: 'Slack',
      allRatings: '全部评分',
      positive: '好评',
      negative: '差评',
      exportCsv: '导出 CSV',
      exportFailed: '导出反馈失败',
      thread: '会话',
      user: '用户',
      agent: '智能体',
      rating: '评分',
      source: '来源',
      comment: '备注',
      preview: 'AI 摘要',
      createdAt: '时间',
      noData: '暂无反馈',
      noDataHint: '用户在门户或 Slack 中对智能体消息评价后，会显示在这里。',
      loadFailed: '加载反馈数据失败',
      openThread: '打开对话',
      loadMore: '加载更多',
    },
  },
  true,
  true
)

export type AgentFeedbackPanelProps = {
  agentId?: number
  showAgentFilter?: boolean
  showAgentColumn?: boolean
  showStats?: boolean
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export default function AgentFeedbackPanel({
  agentId,
  showAgentFilter = true,
  showAgentColumn = true,
  showStats = true,
}: AgentFeedbackPanelProps) {
  const { t, i18n: i18nInstance } = useTranslation()
  const { showError } = useNotification()
  const { data: agents = [] } = useAgents()

  const [agentFilter, setAgentFilter] = useState<string>(
    agentId !== undefined ? String(agentId) : 'all'
  )
  const [sourceFilter, setSourceFilter] = useState<string>('all')
  const [ratingFilter, setRatingFilter] = useState<string>('all')
  const [exporting, setExporting] = useState(false)
  const [listCursor, setListCursor] = useState<number | undefined>()
  const [items, setItems] = useState<FeedbackListItem[]>([])

  useEffect(() => {
    if (agentId !== undefined) {
      setAgentFilter(String(agentId))
    }
  }, [agentId])

  const filterKey = `${agentFilter}:${sourceFilter}:${ratingFilter}`

  const queryParams = useMemo(
    () => ({
      agent_id: agentFilter === 'all' ? undefined : Number(agentFilter),
      source: sourceFilter === 'all' ? undefined : sourceFilter,
      rating: ratingFilter === 'all' ? undefined : ratingFilter,
      limit: 50,
    }),
    [agentFilter, ratingFilter, sourceFilter]
  )

  const statsQuery = useFeedbackStats(queryParams)
  const listQuery = useFeedbackList({ ...queryParams, cursor: listCursor })

  useEffect(() => {
    setListCursor(undefined)
    setItems([])
  }, [filterKey])

  useEffect(() => {
    if (!listQuery.data) {
      return
    }
    if (listCursor === undefined) {
      setItems(listQuery.data.items)
      return
    }
    setItems((previous) => [...previous, ...listQuery.data!.items])
  }, [listQuery.data, listCursor, filterKey])

  const agentNameById = new Map(agents.map((agent) => [agent.id, agent.name]))
  const loadError = statsQuery.error || listQuery.error
  const isLoading = statsQuery.isLoading || listQuery.isLoading
  const isInitialListLoading = listQuery.isLoading && listCursor === undefined
  const dateLocale = i18nInstance.language.startsWith('zh') ? 'zh-CN' : 'en-US'

  const handleRefresh = () => {
    setListCursor(undefined)
    void statsQuery.refetch()
    void listQuery.refetch()
  }

  const handleLoadMore = () => {
    if (listQuery.data?.next_cursor != null) {
      setListCursor(listQuery.data.next_cursor)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      await downloadFeedbackExport(queryParams)
    } catch (err) {
      showError(getApiErrorMessage(err, t('agentFeedback.exportFailed')))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-4">
      {loadError ? (
        <Alert variant="destructive">
          <AlertDescription>{t('agentFeedback.loadFailed')}</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {showAgentFilter ? (
            <Select value={agentFilter} onValueChange={setAgentFilter}>
              <SelectTrigger className="h-9 w-[160px]">
                <SelectValue placeholder={t('agentFeedback.allAgents')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('agentFeedback.allAgents')}</SelectItem>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={String(agent.id)}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="h-9 w-[140px]">
              <SelectValue placeholder={t('agentFeedback.allSources')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('agentFeedback.allSources')}</SelectItem>
              <SelectItem value="portal">{t('agentFeedback.portal')}</SelectItem>
              <SelectItem value="slack">{t('agentFeedback.slack')}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={ratingFilter} onValueChange={setRatingFilter}>
            <SelectTrigger className="h-9 w-[140px]">
              <SelectValue placeholder={t('agentFeedback.allRatings')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('agentFeedback.allRatings')}</SelectItem>
              <SelectItem value="positive">{t('agentFeedback.positive')}</SelectItem>
              <SelectItem value="negative">{t('agentFeedback.negative')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2">
          <Button variant="outline" className="h-11" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            {t('common.refresh')}
          </Button>
          <Button
            variant="outline"
            className="h-11"
            onClick={() => void handleExport()}
            disabled={exporting}
          >
            {exporting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            {t('agentFeedback.exportCsv')}
          </Button>
        </div>
      </div>

      {showStats ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[
            {
              label: t('agentFeedback.totalFeedback'),
              value: statsQuery.data?.total_count ?? 0,
            },
            {
              label: t('agentFeedback.positiveRate'),
              value: formatPercent(statsQuery.data?.positive_rate ?? 0),
            },
            {
              label: t('agentFeedback.negativeCount'),
              value: statsQuery.data?.negative_count ?? 0,
            },
          ].map((metric) => (
            <Card key={metric.label}>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">{metric.label}</p>
                {statsQuery.isLoading ? (
                  <Loader2 className="mt-2 h-5 w-5 animate-spin text-muted-foreground" />
                ) : (
                  <p className="mt-1 text-2xl font-semibold tabular-nums">{metric.value}</p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      {isInitialListLoading && items.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : items.length === 0 ? (
        <EmptyState
          title={t('agentFeedback.noData')}
          description={t('agentFeedback.noDataHint')}
        />
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <TooltipProvider delayDuration={200}>
            <Table className="table-fixed w-full">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-10 w-28">{t('agentFeedback.rating')}</TableHead>
                  <TableHead className="h-10 w-24">{t('agentFeedback.source')}</TableHead>
                  {showAgentColumn ? (
                    <TableHead className="h-10 w-32">{t('agentFeedback.agent')}</TableHead>
                  ) : null}
                  <TableHead className="h-10 w-32">{t('agentFeedback.user')}</TableHead>
                  <TableHead className="h-10 min-w-[10rem]">{t('agentFeedback.preview')}</TableHead>
                  <TableHead className="h-10 min-w-[8rem]">{t('agentFeedback.comment')}</TableHead>
                  <TableHead className="h-10 w-12 text-center">{t('agentFeedback.thread')}</TableHead>
                  <TableHead className="h-10 w-40">{t('agentFeedback.createdAt')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <Badge variant="secondary" className="gap-1">
                        {item.rating === 'positive' ? (
                          <ThumbsUp className="h-3 w-3" />
                        ) : (
                          <ThumbsDown className="h-3 w-3" />
                        )}
                        {item.rating === 'positive'
                          ? t('agentFeedback.positive')
                          : t('agentFeedback.negative')}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {item.source === 'slack'
                        ? t('agentFeedback.slack')
                        : t('agentFeedback.portal')}
                    </TableCell>
                    {showAgentColumn ? (
                      <TableCell className="max-w-0 truncate">
                        {agentNameById.get(item.agent_id) ?? item.agent_id}
                      </TableCell>
                    ) : null}
                    <TableCell className="max-w-0 truncate">{item.username ?? item.user_id}</TableCell>
                    <TableCell className="max-w-0 truncate text-muted-foreground">
                      {item.ai_message_preview ?? ''}
                    </TableCell>
                    <TableCell className="max-w-0 truncate text-muted-foreground">
                      {item.comment ?? ''}
                    </TableCell>
                    <TableCell className="w-12 text-center">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Link
                            to={`/workbench/${item.thread_id}`}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-primary hover:bg-muted"
                            aria-label={t('agentFeedback.openThread')}
                          >
                            <MessageSquare className="h-4 w-4" />
                          </Link>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs font-mono text-xs break-all">
                          {item.thread_id}
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm tabular-nums text-muted-foreground">
                      {formatDate(item.created_at, { locale: dateLocale, fallback: '' })}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TooltipProvider>
          {listQuery.data?.has_more ? (
            <div className="flex justify-center border-t p-4">
              <Button variant="outline" onClick={handleLoadMore} disabled={listQuery.isFetching}>
                {listQuery.isFetching && listCursor !== undefined ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                {t('agentFeedback.loadMore')}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
