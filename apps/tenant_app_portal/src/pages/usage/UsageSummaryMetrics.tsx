import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { Card, CardContent } from '@/components/ui/card'
import { formatDurationMs, formatNumber, formatRate } from '@shared/frontend/format'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    settings: {
      usageTab: {
        totalTokens: 'Total Tokens',
        llmCalls: 'LLM Calls',
        toolCalls: 'Tool Calls',
        activeUsers: 'Active Users',
        lastNDays: 'last {{days}} days',
        tokenBreakdown: '{{input}} input · {{output}} output',
        llmErrorRate: 'LLM Error Rate',
        toolErrorRate: 'Tool Error Rate',
        avgLlmDuration: 'Avg LLM Duration',
        avgToolDuration: 'Avg Tool Duration',
      },
    },
    agentDetail: {
      metricsThreads: 'Threads',
      metricsSessions: 'Sessions',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    settings: {
      usageTab: {
        totalTokens: '总令牌数',
        llmCalls: 'LLM 调用',
        toolCalls: '工具调用',
        activeUsers: '活跃用户',
        lastNDays: '最近 {{days}} 天',
        tokenBreakdown: '{{input}} 输入 · {{output}} 输出',
        llmErrorRate: 'LLM 错误率',
        toolErrorRate: '工具错误率',
        avgLlmDuration: 'LLM 平均耗时',
        avgToolDuration: '工具平均耗时',
      },
    },
    agentDetail: {
      metricsThreads: '对话线程',
      metricsSessions: '会话',
    },
  },
  true,
  true
)

export type UsageSummaryMetricsData = {
  total_tokens: number
  total_input_tokens: number
  total_output_tokens: number
  total_llm_calls: number
  total_llm_errors: number
  total_tool_calls: number
  total_tool_errors: number
  unique_threads: number
  unique_sessions: number
  unique_users: number
  avg_llm_duration_ms?: number | null
  avg_tool_duration_ms?: number | null
}

type UsageSummaryMetricsProps = {
  summary: UsageSummaryMetricsData | null | undefined
  days: number
  showReachMetrics?: boolean
  /** Render without outer Card — use inside SettingsSection. */
  embedded?: boolean
}

type StatItem = {
  label: string
  value: string
}

function StatBar({ items }: { items: StatItem[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border bg-muted/50 p-4">
      {items.map((item) => (
        <div key={item.label} className="min-w-[7rem]">
          <p className="text-xs text-muted-foreground">{item.label}</p>
          <p className="text-lg font-semibold tabular-nums">{item.value}</p>
        </div>
      ))}
    </div>
  )
}

function UsageSummaryMetricsBody({
  summary,
  days,
  showReachMetrics,
}: Omit<UsageSummaryMetricsProps, 'embedded'>) {
  const { t, i18n: i18nInstance } = useTranslation()
  const locale = i18nInstance.language

  const statItems: StatItem[] = [
    { label: t('settings.usageTab.llmCalls'), value: formatNumber(summary?.total_llm_calls ?? 0, locale) },
    { label: t('settings.usageTab.toolCalls'), value: formatNumber(summary?.total_tool_calls ?? 0, locale) },
  ]

  if (showReachMetrics) {
    statItems.push(
      { label: t('agentDetail.metricsThreads'), value: formatNumber(summary?.unique_threads ?? 0, locale) },
      { label: t('agentDetail.metricsSessions'), value: formatNumber(summary?.unique_sessions ?? 0, locale) },
      { label: t('settings.usageTab.activeUsers'), value: formatNumber(summary?.unique_users ?? 0, locale) }
    )
  } else {
    statItems.push({
      label: t('settings.usageTab.activeUsers'),
      value: formatNumber(summary?.unique_users ?? 0, locale),
    })
  }

  statItems.push(
    {
      label: t('settings.usageTab.llmErrorRate'),
      value: formatRate(summary?.total_llm_errors ?? 0, summary?.total_llm_calls ?? 0),
    },
    {
      label: t('settings.usageTab.toolErrorRate'),
      value: formatRate(summary?.total_tool_errors ?? 0, summary?.total_tool_calls ?? 0),
    },
    { label: t('settings.usageTab.avgLlmDuration'), value: formatDurationMs(summary?.avg_llm_duration_ms) },
    { label: t('settings.usageTab.avgToolDuration'), value: formatDurationMs(summary?.avg_tool_duration_ms) }
  )

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm text-muted-foreground">
          {t('settings.usageTab.totalTokens')} · {t('settings.usageTab.lastNDays', { days })}
        </p>
        <p className="text-3xl font-semibold tabular-nums tracking-tight">
          {formatNumber(summary?.total_tokens ?? 0, locale)}
        </p>
        <p className="mt-1 text-sm text-muted-foreground tabular-nums">
          {t('settings.usageTab.tokenBreakdown', {
            input: formatNumber(summary?.total_input_tokens ?? 0, locale),
            output: formatNumber(summary?.total_output_tokens ?? 0, locale),
          })}
        </p>
      </div>
      <StatBar items={statItems} />
    </div>
  )
}

export default function UsageSummaryMetrics({
  summary,
  days,
  showReachMetrics = true,
  embedded = false,
}: UsageSummaryMetricsProps) {
  const body = (
    <UsageSummaryMetricsBody summary={summary} days={days} showReachMetrics={showReachMetrics} />
  )

  if (embedded) {
    return body
  }

  return (
    <Card>
      <CardContent className="p-6">{body}</CardContent>
    </Card>
  )
}
