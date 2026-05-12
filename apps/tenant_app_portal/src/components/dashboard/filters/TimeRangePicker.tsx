import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useEffect, useMemo, useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  components: {
    timeRangePicker: {
      selectTimeRange: 'Select time range',
      presets: 'Presets',
      custom: 'Custom Range',
      today: 'Today',
      yesterday: 'Yesterday',
      last_7_days: 'Last 7 Days',
      last_30_days: 'Last 30 Days',
      this_month: 'This Month',
      last_month: 'Last Month',
      this_year: 'This Year',
      dateOnly: 'Date Only',
      dateTime: 'Date & Time',
      start: 'Start',
      end: 'End',
      dateHint: 'Dates are inclusive: from 00:00 to 23:59 UTC',
      dateTimeHint: 'Supports specific time selection',
      cancel: 'Cancel',
      confirm: 'Apply',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    timeRangePicker: {
      selectTimeRange: '选择时间范围',
      presets: '预设',
      custom: '自定义范围',
      today: '今天',
      yesterday: '昨天',
      last_7_days: '最近 7 天',
      last_30_days: '最近 30 天',
      this_month: '本月',
      last_month: '上月',
      this_year: '今年',
      dateOnly: '仅日期',
      dateTime: '日期时间',
      start: '开始',
      end: '结束',
      dateHint: '日期包含：从 00:00 到 23:59 UTC',
      dateTimeHint: '支持具体时间选择',
      cancel: '取消',
      confirm: '应用',
    },
  },
}, true, true)
import { CalendarRange } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { normalizeForPrecision } from '@/lib/timeRangeUtils'

const TIME_PRESETS = [
  { value: 'today' },
  { value: 'yesterday' },
  { value: 'last_7_days' },
  { value: 'last_30_days' },
  { value: 'this_month' },
  { value: 'last_month' },
  { value: 'this_year' },
]

export interface TimeRangeValue {
  mode?: 'relative' | 'absolute'
  preset?: string
  start?: string
  end?: string
}

interface TimeRangePickerProps {
  value?: TimeRangeValue | null
  onChange: (value: TimeRangeValue) => void
  precision?: 'date' | 'datetime'
  className?: string
}

function buildSummary(value: TimeRangeValue | null | undefined, precision: 'date' | 'datetime', t: (key: string) => string) {
  if (!value) return t('components.timeRangePicker.selectTimeRange')
  if (value.mode === 'relative' && value.preset) {
    const labelKey = `components.timeRangePicker.${value.preset}`
    const label = t(labelKey)
    return label !== labelKey ? label : t('components.timeRangePicker.selectTimeRange')
  }
  if (value.mode === 'absolute' && (value.start || value.end)) {
    const start = normalizeForPrecision(value.start, precision) ?? t('components.timeRangePicker.start').split(' ')[0]
    const end = normalizeForPrecision(value.end, precision) ?? t('components.timeRangePicker.end').split(' ')[0]
    return `${start} ~ ${end}`
  }
  return t('components.timeRangePicker.selectTimeRange')
}

export default function TimeRangePicker({
  value,
  onChange,
  precision: defaultPrecision = 'datetime',
  className,
}: TimeRangePickerProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [tempPrecision, setTempPrecision] = useState<'date' | 'datetime'>(defaultPrecision)
  const [tempStart, setTempStart] = useState(value?.start ?? '')
  const [tempEnd, setTempEnd] = useState(value?.end ?? '')

  const summary = useMemo(
    () => buildSummary(value ?? null, defaultPrecision, t),
    [value, defaultPrecision, t]
  )
  const current = value ?? { mode: 'relative', preset: 'last_7_days' }

  /**
   * 同步 defaultPrecision 变化到 tempPrecision
   * 当 FilterEditor 改变精度设置时，组件立即更新
   */
  useEffect(() => {
    setTempPrecision(defaultPrecision)
    setTempStart(normalizeForPrecision(current.start, defaultPrecision) ?? '')
    setTempEnd(normalizeForPrecision(current.end, defaultPrecision) ?? '')
  }, [defaultPrecision, current.end, current.start])

  /**
   * Handle preset button click - immediately submit and close.
   */
  const handlePresetClick = (preset: string) => {
    onChange({
      mode: 'relative',
      preset,
    })
    setOpen(false)
  }

  /**
   * Handle precision toggle - reset temp values for fresh selection.
   * Note: The actual precision (defaultPrecision) is controlled by parent (FilterEditor),
   * this is just for internal UI state when editing custom ranges.
   */
  const handlePrecisionChange = (newPrecision: 'date' | 'datetime') => {
    setTempPrecision(newPrecision)
    setTempStart('')
    setTempEnd('')
  }

  /**
   * Handle custom range commit - validate both dates are filled, then submit.
   */
  const handleCommitCustomRange = () => {
    if (tempStart && tempEnd) {
      onChange({
        mode: 'absolute',
        start: tempStart,
        end: tempEnd,
      })
      setOpen(false)
    }
  }

  /**
   * Determine input type based on precision.
   */
  const inputType = tempPrecision === 'date' ? 'date' : 'datetime-local'

  /**
   * When popover opens, sync temp values from current value and latest precision.
   */
  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen) {
      // Opening: sync temp values from current and use current precision
      setTempStart(normalizeForPrecision(current.start, defaultPrecision) ?? '')
      setTempEnd(normalizeForPrecision(current.end, defaultPrecision) ?? '')
      setTempPrecision(defaultPrecision)
    }
    setOpen(newOpen)
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="outline" className={cn('min-w-[220px] justify-between', className)}>
          <span className="truncate text-left">{summary}</span>
          <CalendarRange className="ml-2 h-4 w-4 text-muted-foreground" />
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-[520px]" align="start">
        <div className="grid gap-4 md:grid-cols-[1fr,1.4fr]">
          {/* Presets column */}
          <div className="space-y-2">
            <div className="text-sm font-medium">{t('components.timeRangePicker.presets')}</div>
            <div className="grid gap-2">
              {TIME_PRESETS.map((preset) => (
                <Button
                  key={preset.value}
                  variant={
                    current.preset === preset.value && current.mode === 'relative'
                      ? 'default'
                      : 'ghost'
                  }
                  className="justify-start"
                  onClick={() => handlePresetClick(preset.value)}
                >
                  {t(`components.timeRangePicker.${preset.value}`)}
                </Button>
              ))}
            </div>
          </div>

          {/* Custom range column */}
          <div className="space-y-3">
            <div className="text-sm font-medium">{t('components.timeRangePicker.custom')}</div>

            {/* Precision toggle */}
            <div className="flex gap-2 border-b pb-3">
              <Button
                size="sm"
                variant={tempPrecision === 'date' ? 'default' : 'outline'}
                onClick={() => handlePrecisionChange('date')}
                className="flex-1"
              >
                {t('components.timeRangePicker.dateOnly')}
              </Button>
              <Button
                size="sm"
                variant={tempPrecision === 'datetime' ? 'default' : 'outline'}
                onClick={() => handlePrecisionChange('datetime')}
                className="flex-1"
              >
                {t('components.timeRangePicker.dateTime')}
              </Button>
            </div>

            {/* Start date/datetime input */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                {t('components.timeRangePicker.start', { precision: tempPrecision === 'date' ? t('components.timeRangePicker.dateOnly').toLowerCase() : t('components.timeRangePicker.dateTime').toLowerCase() })}
              </Label>
              <Input
                type={inputType}
                value={tempStart}
                onChange={(e) => setTempStart(e.target.value)}
                placeholder={tempPrecision === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DDTHH:mm'}
              />
            </div>

            {/* End date/datetime input */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                {t('components.timeRangePicker.end', { precision: tempPrecision === 'date' ? t('components.timeRangePicker.dateOnly').toLowerCase() : t('components.timeRangePicker.dateTime').toLowerCase() })}
              </Label>
              <Input
                type={inputType}
                value={tempEnd}
                onChange={(e) => setTempEnd(e.target.value)}
                placeholder={tempPrecision === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DDTHH:mm'}
              />
            </div>

            {/* Info text */}
            {tempPrecision === 'date' && (
              <p className="text-xs text-muted-foreground">
                {t('components.timeRangePicker.dateHint')}
              </p>
            )}
            {tempPrecision === 'datetime' && (
              <p className="text-xs text-muted-foreground">
                {t('components.timeRangePicker.dateTimeHint')}
              </p>
            )}

            {/* Action buttons */}
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setOpen(false)}>
                {t('components.timeRangePicker.cancel')}
              </Button>
              <Button
                className="flex-1"
                onClick={handleCommitCustomRange}
                disabled={!tempStart || !tempEnd}
              >
                {t('components.timeRangePicker.confirm')}
              </Button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
