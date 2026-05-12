import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useEffect, useMemo, useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  components: {
    displayConfigEditor: {
      title: 'Title',
      description: 'Description',
      xAxisTitle: 'X-Axis Title',
      yAxisTitle: 'Y-Axis Title',
      legend: 'Legend',
      showLegend: 'Show Legend',
      legendPosition: 'Legend Position',
      default: 'Default',
      top: 'Top',
      bottom: 'Bottom',
      left: 'Left',
      right: 'Right',
      metricFormat: 'Format',
      number: 'Number',
      currency: 'Currency',
      percent: 'Percentage',
      seriesDisplayName: 'Series Display Name',
      displayNamePlaceholder: 'Enter display name...',
      tableConfig: 'Table Configuration',
      showHeader: 'Show Header',
      showRowNumber: 'Row Numbers',
      zebraStripes: 'Zebra Stripes',
      compactMode: 'Compact Mode',
      columnConfig: 'Column Configuration',
      align: 'Align',
      center: 'Center',
      width: 'Width',
      format: 'Format',
      string: 'String',
      datetime: 'Date Time',
      boolean: 'Boolean',
      precision: 'Precision',
      currencyCode: 'Currency Code',
      dateFormat: 'Date Format',
      nullDisplay: 'Null Display',
      prefix: 'Prefix',
      suffix: 'Suffix',
      trueLabel: 'True Label',
      falseLabel: 'False Label',
      pieChartNote: 'Pie chart uses the first series dimension for labels and the first metric for values',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    displayConfigEditor: {
      title: '标题',
      description: '描述',
      xAxisTitle: 'X 轴标题',
      yAxisTitle: 'Y 轴标题',
      legend: '图例',
      showLegend: '显示图例',
      legendPosition: '图例位置',
      default: '默认',
      top: '顶部',
      bottom: '底部',
      left: '左侧',
      right: '右侧',
      metricFormat: '格式',
      number: '数字',
      currency: '货币',
      percent: '百分比',
      seriesDisplayName: '系列显示名称',
      displayNamePlaceholder: '输入显示名称...',
      tableConfig: '表格配置',
      showHeader: '显示表头',
      showRowNumber: '行号',
      zebraStripes: '斑马纹',
      compactMode: '紧凑模式',
      columnConfig: '列配置',
      align: '对齐',
      center: '居中',
      width: '宽度',
      format: '格式',
      string: '字符串',
      datetime: '日期时间',
      boolean: '布尔',
      precision: '精度',
      currencyCode: '货币代码',
      dateFormat: '日期格式',
      nullDisplay: '空值显示',
      prefix: '前缀',
      suffix: '后缀',
      trueLabel: '真值标签',
      falseLabel: '假值标签',
      pieChartNote: '饼图使用第一个系列维度作为标签，第一个指标作为值',
    },
  },
}, true, true)
import type {
  ChartDisplayConfig,
  DashboardWidget,
  QueryPreviewColumn,
  TableColumnConfig,
  TableDisplayConfig,
  TableValueFormat,
} from '@/lib/dashboardApi'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface DisplayConfigEditorProps {
  widget: DashboardWidget
  columns?: QueryPreviewColumn[]
  onFieldChange: (field: 'displayConfig', value: ChartDisplayConfig | null) => void
}

const NONE_VALUE = '__none__'

function toNumber(value: string) {
  if (!value) return undefined
  const num = Number(value)
  return Number.isNaN(num) ? undefined : num
}

export default function DisplayConfigEditor({
  widget,
  columns = [],
  onFieldChange,
}: DisplayConfigEditorProps) {
  const { t } = useTranslation()
  const displayConfig = widget.displayConfig ?? {}
  const columnOptions = columns.map((column) => column.name)
  const chartType = widget.chartType ?? 'line'

  const [, setThresholdsText] = useState('')

  useEffect(() => {
    const text = JSON.stringify(displayConfig.gauge?.thresholds ?? [])
    setThresholdsText(text)
  }, [displayConfig.gauge?.thresholds])

  const updateDisplayConfig = (partial: Partial<ChartDisplayConfig> | null) => {
    if (!partial) {
      onFieldChange('displayConfig', null)
      return
    }
    onFieldChange('displayConfig', {
      ...displayConfig,
      ...partial,
    })
  }

  const updateTableConfig = (partial: Partial<TableDisplayConfig>) => {
    updateDisplayConfig({
      table: {
        ...displayConfig.table,
        ...partial,
      },
    })
  }

  const updateTableColumn = (field: string, partial: Partial<TableColumnConfig>) => {
    const existing = displayConfig.table?.columns ?? []
    const next = [...existing]
    const idx = next.findIndex((col) => col.field === field)
    if (idx >= 0) {
      next[idx] = { ...next[idx], ...partial, field }
    } else {
      next.push({ field, ...partial })
    }
    updateTableConfig({ columns: next })
  }

  const updateTableFormat = (field: string, partial: Partial<TableValueFormat>) => {
    const existing = displayConfig.table?.columns ?? []
    const idx = existing.findIndex((col) => col.field === field)
    const next = [...existing]
    const baseColumn = idx >= 0 ? next[idx] : { field }
    const nextFormat = { ...baseColumn.format, ...partial }
    const nextColumn = { ...baseColumn, format: nextFormat }
    if (idx >= 0) {
      next[idx] = nextColumn
    } else {
      next.push(nextColumn)
    }
    updateTableConfig({ columns: next })
  }

  const seriesLabelEntries = useMemo(() => {
    const mappingSeries = widget.fieldMapping?.series
    const seriesKeys = Array.isArray(mappingSeries)
      ? mappingSeries.map((item) => (typeof item === 'string' ? item : item?.name)).filter(Boolean)
      : []

    if (!seriesKeys.length) return [] as Array<{ key: string; label: string }>
    const labels = displayConfig.seriesLabels ?? {}
    return seriesKeys.map((name) => ({
      key: String(name),
      label: labels[String(name)] ?? '',
    }))
  }, [widget.fieldMapping?.series, displayConfig.seriesLabels])

  const updateSeriesLabel = (field: string, label: string) => {
    const next = {
      ...(displayConfig.seriesLabels ?? {}),
      [field]: label,
    }
    updateDisplayConfig({ seriesLabels: next })
  }

  const isChart = widget.type === 'chart'
  const isMetric = widget.type === 'metric'
  const isTable = widget.type === 'table'

  const isAxisSeriesChart =
    isChart &&
    ['line', 'bar', 'area', 'stacked_bar', 'grouped_bar', 'multi_line', 'multi_area'].includes(
      chartType
    )
  const isScatter = isChart && chartType === 'scatter'
  const isHeatmap = isChart && chartType === 'heatmap'
  const isPie = isChart && chartType === 'pie'
  const isGauge = isChart && chartType === 'gauge'

  return (
    <div className="space-y-6">
      <div className="space-y-4 border-b pb-4">
        <div className="space-y-2">
          <Label htmlFor="display-title">{t('components.displayConfigEditor.title')}</Label>
          <Input
            id="display-title"
            value={displayConfig.title ?? ''}
            onChange={(e) => updateDisplayConfig({ title: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="display-description">{t('components.displayConfigEditor.description')}</Label>
          <Input
            id="display-description"
            value={displayConfig.description ?? ''}
            onChange={(e) => updateDisplayConfig({ description: e.target.value })}
          />
        </div>
      </div>

      {(isAxisSeriesChart || isScatter || isHeatmap) && (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="display-x">{t('components.displayConfigEditor.xAxisTitle')}</Label>
            <Input
              id="display-x"
              value={displayConfig.xLabel ?? ''}
              onChange={(e) => updateDisplayConfig({ xLabel: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="display-y">{t('components.displayConfigEditor.yAxisTitle')}</Label>
            <Input
              id="display-y"
              value={displayConfig.yLabel ?? ''}
              onChange={(e) => updateDisplayConfig({ yLabel: e.target.value })}
            />
          </div>
        </div>
      )}

      {(isAxisSeriesChart || isScatter) && (
        <div className="space-y-3">
          <Label>{t('components.displayConfigEditor.legend')}</Label>
          <div className="flex items-center gap-2">
            <Checkbox
              checked={displayConfig.showLegend ?? true}
              onCheckedChange={(checked) => updateDisplayConfig({ showLegend: Boolean(checked) })}
            />
            <span className="text-sm">{t('components.displayConfigEditor.showLegend')}</span>
          </div>
          <div className="space-y-2">
            <Label htmlFor="legend-position">{t('components.displayConfigEditor.legendPosition')}</Label>
            <Select
              value={displayConfig.legendPosition ?? NONE_VALUE}
              onValueChange={(value) =>
                updateDisplayConfig({
                  legendPosition: value === NONE_VALUE ? undefined : (value as any),
                })
              }
            >
              <SelectTrigger id="legend-position">
                <SelectValue placeholder={t('components.displayConfigEditor.legendPosition')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE_VALUE}>{t('components.displayConfigEditor.default')}</SelectItem>
                <SelectItem value="top">{t('components.displayConfigEditor.top')}</SelectItem>
                <SelectItem value="bottom">{t('components.displayConfigEditor.bottom')}</SelectItem>
                <SelectItem value="left">{t('components.displayConfigEditor.left')}</SelectItem>
                <SelectItem value="right">{t('components.displayConfigEditor.right')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {(isMetric || isGauge) && (
        <div className="space-y-2">
          <Label htmlFor="metric-format">{t('components.displayConfigEditor.metricFormat')}</Label>
          <Select
            value={displayConfig.metricFormat ?? 'number'}
            onValueChange={(value) =>
              updateDisplayConfig({
                metricFormat: value as 'number' | 'currency' | 'percent',
              })
            }
          >
            <SelectTrigger id="metric-format">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="number">{t('components.displayConfigEditor.number')}</SelectItem>
              <SelectItem value="currency">{t('components.displayConfigEditor.currency')}</SelectItem>
              <SelectItem value="percent">{t('components.displayConfigEditor.percent')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {isAxisSeriesChart && seriesLabelEntries.length > 0 && (
        <div className="space-y-3">
          <Label>{t('components.displayConfigEditor.seriesDisplayName')}</Label>
          <div className="space-y-2">
            {seriesLabelEntries.map((entry) => (
              <div key={entry.key} className="grid grid-cols-[140px_1fr] items-center gap-2">
                <span className="text-xs text-muted-foreground truncate">{entry.key}</span>
                <Input
                  value={entry.label}
                  placeholder={t('components.displayConfigEditor.displayNamePlaceholder')}
                  onChange={(e) => updateSeriesLabel(entry.key, e.target.value)}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {isTable && (
        <div className="space-y-4">
          <Label>{t('components.displayConfigEditor.tableConfig')}</Label>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={displayConfig.table?.showHeader ?? true}
                onCheckedChange={(checked) => updateTableConfig({ showHeader: Boolean(checked) })}
              />
              {t('components.displayConfigEditor.showHeader')}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={displayConfig.table?.showRowNumbers ?? false}
                onCheckedChange={(checked) =>
                  updateTableConfig({ showRowNumbers: Boolean(checked) })
                }
              />
              {t('components.displayConfigEditor.showRowNumber')}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={displayConfig.table?.zebraStripes ?? false}
                onCheckedChange={(checked) => updateTableConfig({ zebraStripes: Boolean(checked) })}
              />
              {t('components.displayConfigEditor.zebraStripes')}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={displayConfig.table?.compact ?? false}
                onCheckedChange={(checked) => updateTableConfig({ compact: Boolean(checked) })}
              />
              {t('components.displayConfigEditor.compactMode')}
            </label>
          </div>

          {columnOptions.length > 0 && (
            <div className="space-y-4">
              <Label>{t('components.displayConfigEditor.columnConfig')}</Label>
              <div className="space-y-3">
                {columnOptions.map((field) => {
                  const column = displayConfig.table?.columns?.find((col) => col.field === field)
                  return (
                    <div key={field} className="rounded-md border p-3 space-y-3">
                      <div className="text-xs text-muted-foreground">{field}</div>
                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          placeholder={t('components.displayConfigEditor.displayNamePlaceholder')}
                          value={column?.label ?? ''}
                          onChange={(e) => updateTableColumn(field, { label: e.target.value })}
                        />
                        <Select
                          value={column?.align ?? NONE_VALUE}
                          onValueChange={(value) =>
                            updateTableColumn(field, {
                              align: value === NONE_VALUE ? undefined : (value as any),
                            })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder={t('components.displayConfigEditor.align')} />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value={NONE_VALUE}>{t('components.displayConfigEditor.default')}</SelectItem>
                            <SelectItem value="left">{t('components.displayConfigEditor.left')}</SelectItem>
                            <SelectItem value="center">{t('components.displayConfigEditor.center')}</SelectItem>
                            <SelectItem value="right">{t('components.displayConfigEditor.right')}</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          placeholder={t('components.displayConfigEditor.width')}
                          value={column?.width?.toString() ?? ''}
                          onChange={(e) =>
                            updateTableColumn(field, { width: toNumber(e.target.value) })
                          }
                        />
                        <Select
                          value={column?.format?.formatType ?? NONE_VALUE}
                          onValueChange={(value) =>
                            updateTableFormat(field, {
                              formatType: value === NONE_VALUE ? undefined : (value as any),
                            })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder={t('components.displayConfigEditor.format')} />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value={NONE_VALUE}>{t('components.displayConfigEditor.default')}</SelectItem>
                            <SelectItem value="string">{t('components.displayConfigEditor.string')}</SelectItem>
                            <SelectItem value="number">{t('components.displayConfigEditor.number')}</SelectItem>
                            <SelectItem value="currency">{t('components.displayConfigEditor.currency')}</SelectItem>
                            <SelectItem value="percent">{t('components.displayConfigEditor.percent')}</SelectItem>
                            <SelectItem value="datetime">{t('components.displayConfigEditor.datetime')}</SelectItem>
                            <SelectItem value="boolean">{t('components.displayConfigEditor.boolean')}</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          placeholder={t('components.displayConfigEditor.precision')}
                          value={column?.format?.precision?.toString() ?? ''}
                          onChange={(e) =>
                            updateTableFormat(field, {
                              precision: toNumber(e.target.value),
                            })
                          }
                        />
                        <Input
                          placeholder={t('components.displayConfigEditor.currencyCode')}
                          value={column?.format?.currency ?? ''}
                          onChange={(e) => updateTableFormat(field, { currency: e.target.value })}
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          placeholder={t('components.displayConfigEditor.dateFormat')}
                          value={column?.format?.dateFormat ?? ''}
                          onChange={(e) => updateTableFormat(field, { dateFormat: e.target.value })}
                        />
                        <Input
                          placeholder={t('components.displayConfigEditor.nullDisplay')}
                          value={column?.format?.nullDisplay ?? ''}
                          onChange={(e) =>
                            updateTableFormat(field, { nullDisplay: e.target.value })
                          }
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          placeholder={t('components.displayConfigEditor.prefix')}
                          value={column?.format?.prefix ?? ''}
                          onChange={(e) => updateTableFormat(field, { prefix: e.target.value })}
                        />
                        <Input
                          placeholder={t('components.displayConfigEditor.suffix')}
                          value={column?.format?.suffix ?? ''}
                          onChange={(e) => updateTableFormat(field, { suffix: e.target.value })}
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          placeholder={t('components.displayConfigEditor.trueLabel')}
                          value={column?.format?.trueLabel ?? ''}
                          onChange={(e) => updateTableFormat(field, { trueLabel: e.target.value })}
                        />
                        <Input
                          placeholder={t('components.displayConfigEditor.falseLabel')}
                          value={column?.format?.falseLabel ?? ''}
                          onChange={(e) => updateTableFormat(field, { falseLabel: e.target.value })}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {isPie && (
        <div className="text-xs text-muted-foreground">{t('components.displayConfigEditor.pieChartNote')}</div>
      )}
    </div>
  )
}
