import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import SettingsSection from '@/components/SettingsSection'
import type { TokenUsageDailyPoint } from '@/lib/tenantApi'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    usageTab: {
      totalTokens: 'Total Tokens',
      llmCalls: 'LLM Calls',
      tokenTrend: 'Token Trend',
      tokenTrendDesc: 'Token usage over the last {{days}} days',
      tokenTrendDescForUser: 'Token usage for {{username}} over the last {{days}} days',
      noTokenData: 'No token data available',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    usageTab: {
      totalTokens: '总令牌数',
      llmCalls: 'LLM 调用',
      tokenTrend: '令牌趋势',
      tokenTrendDesc: '最近 {{days}} 天的令牌用量',
      tokenTrendDescForUser: '{{username}} 最近 {{days}} 天的令牌用量',
      noTokenData: '暂无令牌数据',
    }
  }
}, true, true)

function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

interface TokenTrendChartProps {
  days: number
  username?: string
  rows: TokenUsageDailyPoint[]
}

export default function TokenTrendChart({ days, username, rows }: TokenTrendChartProps) {
  const { t } = useTranslation()
  const description = username
    ? t('settings.usageTab.tokenTrendDescForUser', { days, username })
    : t('settings.usageTab.tokenTrendDesc', { days })
  const option = useMemo<EChartsOption | null>(() => {
    if (!rows.length) return null

    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const points = Array.isArray(params) ? params : [params]
          if (!points.length) return ''

          const dateLabel = points[0]?.axisValueLabel || points[0]?.name || ''
          const content = points
            .map((item: any) => {
              const value = Number(item?.value || 0)
              return `${item.marker}${item.seriesName}: ${formatNumber(value)}`
            })
            .join('<br/>')

          return `${dateLabel}<br/>${content}`
        },
      },
      legend: {
        data: [t('settings.usageTab.totalTokens'), t('settings.usageTab.llmCalls')],
      },
      grid: {
        left: 16,
        right: 16,
        top: 40,
        bottom: 16,
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: rows.map((row) => row.date),
      },
      yAxis: [
        {
          type: 'value',
          name: 'Tokens',
        },
        {
          type: 'value',
          name: t('settings.usageTab.llmCalls'),
        },
      ],
      series: [
        {
          name: t('settings.usageTab.totalTokens'),
          type: 'bar',
          data: rows.map((row) => row.total_tokens),
        },
        {
          name: t('settings.usageTab.llmCalls'),
          type: 'line',
          yAxisIndex: 1,
          data: rows.map((row) => row.llm_calls),
          smooth: true,
        },
      ],
    }
  }, [rows])

  return (
    <SettingsSection
      title={t('settings.usageTab.tokenTrend')}
      description={description}
    >
        {option ? (
          <div className="h-[320px] w-full">
            <ReactECharts option={option} style={{ height: '100%', width: '100%' }} />
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-muted-foreground">{t('settings.usageTab.noTokenData')}</div>
        )}
    </SettingsSection>
  )
}
