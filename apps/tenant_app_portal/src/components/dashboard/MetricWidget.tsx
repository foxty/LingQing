import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import type { DashboardWidget } from '@/lib/dashboardApi'
import { extractMetricValue } from '@/lib/dashboardChart'
import { cn } from '@/lib/utils'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      metricWidget: {
        incomplete: 'Incomplete',
        incompleteHint: 'This series has no comparable value for the current period.',
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
      metricWidget: {
        incomplete: '不完整',
        incompleteHint: '当前周期没有可比较的数值。',
      },
    },
  },
  true,
  true
)

interface MetricWidgetProps {
  widget: DashboardWidget
  data: Array<Record<string, any>>
}

function formatMetricValue(
  val: number | null | string,
  format?: 'number' | 'currency' | 'percent'
): string | null {
  if (val === null || (typeof val === 'number' && Number.isNaN(val))) return null

  const numVal = typeof val === 'number' ? val : parseFloat(String(val))

  if (isNaN(numVal)) {
    return String(val)
  }

  if (format === 'currency') {
    return new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: 'CNY',
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(numVal)
  }

  if (format === 'percent') {
    return `${numVal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}%`
  }

  // Default: number format
  return numVal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

export default function MetricWidget({ widget, data }: MetricWidgetProps) {
  const { t } = useTranslation()
  const displayConfig = widget.displayConfig
  const value = extractMetricValue(data, widget)
  const formattedValue = formatMetricValue(value, displayConfig?.metricFormat)
  const incomplete = formattedValue === null

  return (
    <div className="flex h-full flex-col justify-center rounded-md bg-card p-4">
      {displayConfig?.title && (
        <div className="mb-2 space-y-0.5">
          <div
            className="text-center text-sm font-medium text-muted-foreground"
            title={displayConfig.description}
          >
            {displayConfig.title}
          </div>
        </div>
      )}
      {incomplete ? (
        <div className="space-y-1 text-center">
          <p className="text-sm font-medium text-warn">{t('components.metricWidget.incomplete')}</p>
          <p className="text-xs text-muted-foreground">{t('components.metricWidget.incompleteHint')}</p>
        </div>
      ) : (
        <div className={cn('text-center text-3xl font-semibold tabular-nums')}>{formattedValue}</div>
      )}
    </div>
  )
}
