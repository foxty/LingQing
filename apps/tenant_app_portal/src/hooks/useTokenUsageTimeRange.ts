import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  DEFAULT_USAGE_TIME_RANGE,
  formatTimeRangeSummary,
  usageTimeRangeBounds,
  type TimeRangeValue,
} from '@/lib/timeRangeUtils'

export function useTokenUsageTimeRange() {
  const { t } = useTranslation()
  const [timeRange, setTimeRange] = useState<TimeRangeValue>(DEFAULT_USAGE_TIME_RANGE)

  const bounds = useMemo(() => usageTimeRangeBounds(timeRange), [timeRange])
  const periodLabel = useMemo(
    () => formatTimeRangeSummary(timeRange, 'datetime', t),
    [timeRange, t]
  )

  return { timeRange, setTimeRange, bounds, periodLabel }
}