import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import ReactECharts from 'echarts-for-react'

import type { DashboardWidget } from '@/lib/dashboardApi'
import { buildChartOptions, extractMetricValue } from '@/lib/dashboardChart'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      chartWidget: {
        incomplete: 'Incomplete chart',
        missingConfig: 'This chart has no configuration yet. Open the widget editor to map fields.',
        notEnoughPoints: 'Not enough points for a trend',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    components: {
      chartWidget: {
        incomplete: '图表不完整',
        missingConfig: '此图表尚未配置。打开组件编辑器映射字段。',
        notEnoughPoints: '点数不足，无法构成趋势',
      },
    },
  },
  true,
  true
)

interface ChartWidgetProps {
  widget: DashboardWidget
  data: Array<Record<string, any>>
}

export default function ChartWidget({ widget, data }: ChartWidgetProps) {
  const { t } = useTranslation()
  const options = useMemo(() => buildChartOptions(widget, data), [widget, data])

  if (!options) {
    return (
      <div className="space-y-1 p-3">
        <p className="text-sm font-medium text-warn">{t('components.chartWidget.incomplete')}</p>
        <p className="text-xs text-muted-foreground">{t('components.chartWidget.missingConfig')}</p>
      </div>
    )
  }

  if (data.length < 2) {
    const value = extractMetricValue(data, widget)
    return (
      <div className="flex h-full flex-col justify-center p-4 text-center">
        {widget.displayConfig?.title ? (
          <p className="mb-2 text-sm font-medium text-muted-foreground">{widget.displayConfig.title}</p>
        ) : null}
        {value !== null ? (
          <p className="text-3xl font-semibold tabular-nums">{value.toLocaleString()}</p>
        ) : (
          <p className="text-sm font-medium text-warn">{t('components.chartWidget.incomplete')}</p>
        )}
        <p className="mt-1 text-xs text-muted-foreground">{t('components.chartWidget.notEnoughPoints')}</p>
      </div>
    )
  }

  return (
    <div className="flex h-full w-full flex-col">
      <ReactECharts
        option={options}
        notMerge
        lazyUpdate
        style={{ height: '100%', width: '100%', minHeight: 160 }}
      />
    </div>
  )
}
