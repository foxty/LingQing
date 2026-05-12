import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import type { FieldMapping, DashboardWidget, QueryPreviewColumn } from '@/lib/dashboardApi'

i18n.addResourceBundle('en', 'translation', {
  components: {
    fieldMappingEditor: {
      selectField: 'Select field',
      notSelected: 'Not selected',
      seriesCommaSeparated: 'Series (comma separated)',
      seriesField: 'Series Fields',
      loadingFields: 'Loading fields...',
      previewUnavailable: 'Preview not available',
      availableFields: 'Available fields: {{fields}}',
      noFieldPreview: 'No field preview available',
      numericField: 'Value Field',
      xAxisField: 'X-Axis Field',
      yAxisField: 'Y-Axis Field',
      labelField: 'Label Field',
      bubbleSizeField: 'Bubble Size Field',
      colorGroupField: 'Color Group Field',
      tableNote: 'Table widgets use the field mapping defined in Display Config → Column Configuration',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    fieldMappingEditor: {
      selectField: '选择字段',
      notSelected: '未选择',
      seriesCommaSeparated: '系列（逗号分隔）',
      seriesField: '系列字段',
      loadingFields: '加载字段中...',
      previewUnavailable: '预览不可用',
      availableFields: '可用字段: {{fields}}',
      noFieldPreview: '无字段预览',
      numericField: '值字段',
      xAxisField: 'X 轴字段',
      yAxisField: 'Y 轴字段',
      labelField: '标签字段',
      bubbleSizeField: '气泡大小字段',
      colorGroupField: '颜色分组字段',
      tableNote: '表格组件使用显示配置 → 列配置中定义的字段映射',
    },
  },
}, true, true)
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface FieldMappingEditorProps {
  widget: DashboardWidget
  columns?: QueryPreviewColumn[]
  isLoading?: boolean
  error?: string | null
  onFieldChange: (field: 'fieldMapping', value: FieldMapping | null) => void
}

const NONE_VALUE = '__none__'

function normalizeSeries(series: FieldMapping['series']): string[] {
  if (!series) return []
  if (!Array.isArray(series)) return []
  return series
    .map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object' && 'name' in item) {
        return String(item.name)
      }
      return ''
    })
    .filter(Boolean)
}

function FieldSelect({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string
  label: string
  value?: string
  options: string[]
  onChange: (next?: string) => void
}) {
  const { t } = useTranslation()
  if (!options.length) {
    return (
      <div className="space-y-2">
        <Label htmlFor={id}>{label}</Label>
        <Input id={id} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={value ?? NONE_VALUE}
        onValueChange={(next) => onChange(next === NONE_VALUE ? undefined : next)}
      >
        <SelectTrigger id={id}>
          <SelectValue placeholder={t('components.fieldMappingEditor.selectField')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE_VALUE}>{t('components.fieldMappingEditor.notSelected')}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export default function FieldMappingEditor({
  widget,
  columns = [],
  isLoading,
  error,
  onFieldChange,
}: FieldMappingEditorProps) {
  const { t } = useTranslation()
  const mapping = widget.fieldMapping ?? {}
  const columnOptions = columns.map((column) => column.name)
  const chartType = widget.chartType ?? 'line'

  const series = normalizeSeries(mapping.series)

  const updateMapping = (partial: Partial<FieldMapping> | null) => {
    if (!partial) {
      onFieldChange('fieldMapping', null)
      return
    }
    onFieldChange('fieldMapping', {
      ...mapping,
      ...partial,
    })
  }

  const toggleSeries = (field: string) => {
    const next = series.includes(field)
      ? series.filter((item) => item !== field)
      : [...series, field]
    updateMapping({ series: next })
  }

  const renderSeriesPicker = () => {
    if (!columnOptions.length) {
      return (
        <div className="space-y-2">
          <Label htmlFor="mapping-series">{t('components.fieldMappingEditor.seriesCommaSeparated')}</Label>
          <Input
            id="mapping-series"
            value={series.join(', ')}
            onChange={(e) =>
              updateMapping({
                series: e.target.value
                  .split(',')
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
          />
        </div>
      )
    }

    return (
      <div className="space-y-2">
        <Label>{t('components.fieldMappingEditor.seriesField')}</Label>
        <div className="grid grid-cols-2 gap-2">
          {columnOptions.map((field) => (
            <label key={field} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={series.includes(field)}
                onCheckedChange={() => toggleSeries(field)}
              />
              <span>{field}</span>
            </label>
          ))}
        </div>
      </div>
    )
  }

  const isChart = widget.type === 'chart'
  const isMetric = widget.type === 'metric'
  const isTable = widget.type === 'table'

  const isAxisSeriesChart =
    isChart &&
    ['line', 'bar', 'area', 'stacked_bar', 'grouped_bar', 'multi_line', 'multi_area'].includes(
      chartType
    )
  const isPie = isChart && chartType === 'pie'
  const isScatter = isChart && chartType === 'scatter'
  const isHeatmap = isChart && chartType === 'heatmap'
  const isGauge = isChart && chartType === 'gauge'

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted-foreground">
        {isLoading
          ? t('components.fieldMappingEditor.loadingFields')
          : error
            ? t('components.fieldMappingEditor.previewUnavailable')
            : columnOptions.length
              ? `${t('components.fieldMappingEditor.availableFields', { fields: columnOptions.join(', ') })}`
              : t('components.fieldMappingEditor.noFieldPreview')}
      </div>

      {(isMetric || isGauge) && (
        <FieldSelect
          id="mapping-value"
          label={t('components.fieldMappingEditor.numericField')}
          value={mapping.value}
          options={columnOptions}
          onChange={(value) => updateMapping({ value })}
        />
      )}

      {isAxisSeriesChart && (
        <>
          <FieldSelect
            id="mapping-x"
            label={t('components.fieldMappingEditor.xAxisField')}
            value={mapping.xAxis}
            options={columnOptions}
            onChange={(value) => updateMapping({ xAxis: value })}
          />
          {renderSeriesPicker()}
        </>
      )}

      {isHeatmap && (
        <>
          <FieldSelect
            id="mapping-x"
            label={t('components.fieldMappingEditor.xAxisField')}
            value={mapping.xAxis}
            options={columnOptions}
            onChange={(value) => updateMapping({ xAxis: value })}
          />
          <FieldSelect
            id="mapping-y"
            label={t('components.fieldMappingEditor.yAxisField')}
            value={mapping.yAxis}
            options={columnOptions}
            onChange={(value) => updateMapping({ yAxis: value })}
          />
          <FieldSelect
            id="mapping-value"
            label={t('components.fieldMappingEditor.numericField')}
            value={mapping.value}
            options={columnOptions}
            onChange={(value) => updateMapping({ value })}
          />
        </>
      )}

      {isPie && (
        <>
          <FieldSelect
            id="mapping-label"
            label={t('components.fieldMappingEditor.labelField')}
            value={mapping.xAxis}
            options={columnOptions}
            onChange={(value) => updateMapping({ xAxis: value })}
          />
          <FieldSelect
            id="mapping-value"
            label={t('components.fieldMappingEditor.numericField')}
            value={mapping.value}
            options={columnOptions}
            onChange={(value) => updateMapping({ value })}
          />
        </>
      )}

      {isScatter && (
        <>
          <FieldSelect
            id="mapping-x"
            label={t('components.fieldMappingEditor.xAxisField')}
            value={mapping.xAxis}
            options={columnOptions}
            onChange={(value) => updateMapping({ xAxis: value })}
          />
          <FieldSelect
            id="mapping-y"
            label={t('components.fieldMappingEditor.yAxisField')}
            value={mapping.yAxis}
            options={columnOptions}
            onChange={(value) => updateMapping({ yAxis: value })}
          />
          <FieldSelect
            id="mapping-size"
            label={t('components.fieldMappingEditor.bubbleSizeField')}
            value={mapping.size}
            options={columnOptions}
            onChange={(value) => updateMapping({ size: value })}
          />
          <FieldSelect
            id="mapping-color"
            label={t('components.fieldMappingEditor.colorGroupField')}
            value={mapping.color}
            options={columnOptions}
            onChange={(value) => updateMapping({ color: value })}
          />
        </>
      )}

      {isTable && (
        <div className="text-xs text-muted-foreground">
          {t('components.fieldMappingEditor.tableNote')}
        </div>
      )}
    </div>
  )
}
