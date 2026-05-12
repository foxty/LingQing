import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useEffect, useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  components: {
    filterEditor: {
      title: 'Filter: {{name}}',
      name: 'Name',
      type: 'Type',
      timeRange: 'Time Range',
      staticDropdown: 'Static Dropdown',
      datasourceDropdown: 'Datasource Dropdown',
      paramName: 'Parameter Name',
      paramNamePlaceholder: 'e.g. date_range',
      paramNameInvalid: 'Parameter name must start with a letter and contain only letters, numbers, and underscores',
      defaultValue: 'Default Value',
      dateOnly: 'Date Only',
      dateTime: 'Date & Time',
      all: 'All',
      noOptions: 'No options available',
      multiSelect: 'Multi-select',
      required: 'Required',
      mustSelectValue: 'Must select a value',
      dataSource: 'Data Source',
      optionSql: 'Options SQL',
      staticOptions: 'Static Options (one per line, format: label=value)',
      deleteFilter: 'Delete Filter',
      deleteConfirmDesc: 'Are you sure you want to delete "{{name}}"?',
      irreversible: 'This action cannot be undone.',
      paramChangeTitle: 'Parameter Name Change',
      paramChangeDesc: '{{count}} widget(s) use this parameter and will be updated',
      affectedWidgets: 'Affected Widgets',
      willReplace: 'The following parameters will be replaced:',
      confirmUpdate: 'Update',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    filterEditor: {
      title: '筛选: {{name}}',
      name: '名称',
      type: '类型',
      timeRange: '时间范围',
      staticDropdown: '静态下拉',
      datasourceDropdown: '数据源下拉',
      paramName: '参数名称',
      paramNamePlaceholder: '例如 date_range',
      paramNameInvalid: '参数名必须以字母开头，仅包含字母、数字和下划线',
      defaultValue: '默认值',
      dateOnly: '仅日期',
      dateTime: '日期时间',
      all: '全部',
      noOptions: '无可用选项',
      multiSelect: '多选',
      required: '必填',
      mustSelectValue: '必须选择一个值',
      dataSource: '数据源',
      optionSql: '选项 SQL',
      staticOptions: '静态选项（每行一个，格式: label=value）',
      deleteFilter: '删除筛选',
      deleteConfirmDesc: '确定要删除 "{{name}}" 吗？',
      irreversible: '此操作不可撤销。',
      paramChangeTitle: '参数名称更改',
      paramChangeDesc: '{{count}} 个组件使用了此参数，将被更新',
      affectedWidgets: '受影响的组件',
      willReplace: '以下参数将被替换:',
      confirmUpdate: '更新',
    },
  },
}, true, true)
import type { CSSProperties } from 'react'
import { Settings2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
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
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Textarea } from '@/components/ui/textarea'
import TimeRangePicker from '@/components/dashboard/filters/TimeRangePicker'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { cn } from '@/lib/utils'
import { normalizeTimeRangeValue } from '@/lib/timeRangeUtils'
import { useConfirmation } from '@/hooks/useConfirmation'
import type { DashboardFilter, DashboardFilterType, DashboardWidget } from '@/lib/dashboardApi'
import {
  getFilterParamNames,
  detectAffectedWidgets,
  getParamChangeInfo,
} from '@/lib/filterParamUtils'

interface FilterEditorProps {
  filter: DashboardFilter
  dataSources: Array<{ id: number; name: string }>
  allWidgets?: DashboardWidget[]
  originalFilter?: DashboardFilter
  onUpdate: (patch: Partial<DashboardFilter>) => void
  onSave: (updatedWidgets?: DashboardWidget[]) => Promise<void>
  onRemove: () => Promise<void>
  onClose: () => void
  containerClassName?: string
  containerStyle?: CSSProperties
}

const FILTER_TYPES: Array<{ value: DashboardFilterType; labelKey: string }> = [
  { value: 'time_range', labelKey: 'components.filterEditor.timeRange' },
  { value: 'dropdown_static', labelKey: 'components.filterEditor.staticDropdown' },
  { value: 'dropdown_datasource', labelKey: 'components.filterEditor.datasourceDropdown' },
]

const PARAM_KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/
const ALL_OPTION_VALUE = '__all__'

function normalizeOptionsInput(raw: string): { label: string; value: string }[] {
  return raw
    .split('\n')
    .map((line) => line.trim())
    .map((line) => {
      if (!line) return null
      const hasSeparator = line.includes('=')
      if (!hasSeparator) {
        return { label: line, value: line }
      }
      const [labelPart, valuePart] = line.split('=')
      const labelRaw = labelPart?.trim() ?? ''
      const valueRaw = valuePart?.trim() ?? ''
      const label = labelRaw || valueRaw
      if (!label && !valueRaw) return null
      return { label, value: valueRaw }
    })
    .filter((option): option is { label: string; value: string } => Boolean(option))
}

export default function FilterEditor({
  filter,
  dataSources,
  allWidgets = [],
  originalFilter,
  onUpdate,
  onSave,
  onRemove,
  onClose,
  containerClassName,
  containerStyle,
}: FilterEditorProps) {
  const { t } = useTranslation()
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [staticOptionsInput, setStaticOptionsInput] = useState('')
  const [affectedWidgets, setAffectedWidgets] = useState<DashboardWidget[]>([])
  const [paramChangeConfirm, setParamChangeConfirm] = useState(false)
  const removeConfirm = useConfirmation<DashboardFilter | null>(null)

  useEffect(() => {
    setStaticOptionsInput('')
  }, [filter.id])

  useEffect(() => {
    if (filter.type !== 'dropdown_static') return
    const initial = (filter.options ?? []).map((opt) => `${opt.label}=${opt.value}`).join('\n')
    setStaticOptionsInput(initial)
  }, [filter.id, filter.type, filter.options])

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)

    try {
      // Check if param_key has changed
      const oldParamKey = originalFilter?.paramKey
      const newParamKey = filter.paramKey
      const paramKeyChanged = oldParamKey !== newParamKey

      if (!newParamKey || !PARAM_KEY_PATTERN.test(newParamKey)) {
        setError(t('components.filterEditor.paramNameInvalid'))
        setIsSaving(false)
        return
      }

      if (paramKeyChanged && allWidgets.length > 0 && originalFilter) {
        // Get old and new parameter names
        const oldParamNames = getFilterParamNames(originalFilter)

        // Detect affected widgets
        const affected = detectAffectedWidgets(oldParamNames, allWidgets)

        if (affected.length > 0) {
          // Show confirmation dialog
          setAffectedWidgets(affected)
          setParamChangeConfirm(true)
          setIsSaving(false)
          return
        }
      }

      // No parameter change or no affected widgets, proceed with save
      await onSave()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
      setIsSaving(false)
    }
  }

  const handleConfirmParamChange = async () => {
    setParamChangeConfirm(false)

    if (!originalFilter) {
      return
    }

    setIsSaving(true)
    try {
      const oldParamNames = getFilterParamNames(originalFilter)
      const newParamNames = getFilterParamNames(filter)

      // Update affected widgets with new parameter names
      const updatedWidgets = affectedWidgets.map((widget) => {
        let newQuery = widget.query || ''
        oldParamNames.forEach((oldParam, idx) => {
          const regex = new RegExp(`:${oldParam}\\b`, 'g')
          newQuery = newQuery.replace(regex, `:${newParamNames[idx]}`)
        })
        return { ...widget, query: newQuery }
      })

      // Save with updated widgets
      await onSave(updatedWidgets)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancelParamChange = () => {
    setParamChangeConfirm(false)
    setAffectedWidgets([])
  }

  const handleRemoveClick = () => {
    removeConfirm.open(filter)
  }

  const handleConfirmRemove = async (target: DashboardFilter | null) => {
    if (!target) return
    removeConfirm.setLoading(true)
    try {
      await onRemove()
      removeConfirm.close()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Remove failed')
      removeConfirm.setLoading(false)
    }
  }

  return (
    <div
      className={cn('shrink-0 border-l bg-background shadow-lg', containerClassName)}
      style={containerStyle}
    >
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Settings2 className="h-4 w-4" />
          {t('components.filterEditor.title', { name: filter.name })}
        </div>
        <button className="text-sm text-muted-foreground hover:text-foreground" onClick={onClose}>
          {t('common.close')}
        </button>
      </div>

      <div className="overflow-y-auto p-4 space-y-4" style={{ height: 'calc(100% - 53px)' }}>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t('components.filterEditor.name')}</Label>
            <Input
              value={filter.name}
              onChange={(event) => onUpdate({ name: event.target.value })}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('components.filterEditor.type')}</Label>
            <Select
              value={filter.type}
              onValueChange={(nextValue) => {
                const nextType = nextValue as DashboardFilterType
                const patch: Partial<DashboardFilter> = { type: nextType }
                if (nextType === 'time_range' && !filter.value) {
                  patch.value = { mode: 'relative', preset: 'last_7_days' }
                }
                if (
                  (nextType === 'dropdown_static' || nextType === 'dropdown_datasource') &&
                  filter.value === undefined
                ) {
                  patch.value = null
                }
                onUpdate(patch)
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FILTER_TYPES.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {t(option.labelKey)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>{t('components.filterEditor.paramName')}</Label>
            <Input
              value={filter.paramKey ?? ''}
              onChange={(event) => onUpdate({ paramKey: event.target.value })}
              placeholder={t('components.filterEditor.paramNamePlaceholder')}
            />
            <div className="text-xs text-muted-foreground">
              {(() => {
                const baseKey = filter.paramKey || ''
                if (filter.type === 'time_range') {
                  return (
                    <div className="flex flex-wrap gap-2">
                      <span className="rounded-sm bg-muted px-2 py-1">:start_{baseKey}</span>
                      <span className="rounded-sm bg-muted px-2 py-1">:end_{baseKey}</span>
                    </div>
                  )
                }
                return (
                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-sm bg-muted px-2 py-1">:{baseKey}</span>
                  </div>
                )
              })()}
            </div>
            {!PARAM_KEY_PATTERN.test(filter.paramKey ?? '') && (filter.paramKey ?? '') !== '' && (
              <div className="text-xs text-destructive">
                {t('components.filterEditor.paramNameInvalid')}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label>{t('components.filterEditor.defaultValue')}</Label>
            {filter.type === 'time_range' ? (
              <div className="space-y-3">
                <div className="flex gap-2 border-b pb-3">
                  <Button
                    size="sm"
                    variant={filter.timePrecision === 'date' ? 'default' : 'outline'}
                    onClick={() =>
                      onUpdate({
                        timePrecision: 'date',
                        value: normalizeTimeRangeValue(filter.value, 'date'),
                      })
                    }
                    className="flex-1"
                  >
                    {t('components.filterEditor.dateOnly')}
                  </Button>
                  <Button
                    size="sm"
                    variant={filter.timePrecision !== 'date' ? 'default' : 'outline'}
                    onClick={() =>
                      onUpdate({
                        timePrecision: 'datetime',
                        value: normalizeTimeRangeValue(filter.value, 'datetime'),
                      })
                    }
                    className="flex-1"
                  >
                    {t('components.filterEditor.dateTime')}
                  </Button>
                </div>
                <TimeRangePicker
                  value={filter.value as any}
                  onChange={(nextValue) =>
                    onUpdate({
                      value: nextValue,
                    })
                  }
                  precision={filter.timePrecision || 'datetime'}
                />
              </div>
            ) : filter.type === 'dropdown_static' || filter.type === 'dropdown_datasource' ? (
              filter.allowMultiple ? (
                (filter.options ?? []).length === 0 ? (
                  <div className="text-xs text-muted-foreground">{t('components.filterEditor.noOptions')}</div>
                ) : (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" size="sm" className="w-full justify-between">
                        <span className="truncate">
                          {(() => {
                            const isAllSelected =
                              !filter.required &&
                              (filter.value === null || filter.value === undefined)
                            if (isAllSelected) return t('components.filterEditor.all')
                            const selectedValues = Array.isArray(filter.value) ? filter.value : []
                            const selectedLabels = (filter.options ?? [])
                              .filter((option) =>
                                selectedValues.some(
                                  (value) => String(value) === String(option.value)
                                )
                              )
                              .map((option) => option.label)
                            return selectedLabels.length > 0 ? selectedLabels.join(', ') : t('components.filterBar.pleaseSelect')
                          })()}
                        </span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {Array.isArray(filter.value) ? filter.value.length : 0}
                        </span>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="w-80">
                      {!filter.required && (
                        <DropdownMenuCheckboxItem
                          key={ALL_OPTION_VALUE}
                          checked={
                            filter.value === null ||
                            filter.value === undefined ||
                            (Array.isArray(filter.value) && filter.value.length === 0)
                          }
                          onCheckedChange={(checked) => {
                            if (checked) {
                              onUpdate({ value: null })
                            } else {
                              onUpdate({ value: [] })
                            }
                          }}
                        >
                          {t('components.filterEditor.all')}
                          </DropdownMenuCheckboxItem>
                      )}
                      {(filter.options ?? []).map((option) => {
                        const selectedValues = Array.isArray(filter.value) ? filter.value : []
                        const isChecked = selectedValues.some(
                          (value) => String(value) === String(option.value)
                        )
                        return (
                          <DropdownMenuCheckboxItem
                            key={String(option.value)}
                            checked={isChecked}
                            onCheckedChange={(checked) => {
                              const nextValues = new Set(
                                selectedValues.map((value) => String(value))
                              )
                              const optionValue = String(option.value)
                              if (checked) {
                                nextValues.add(optionValue)
                              } else {
                                nextValues.delete(optionValue)
                              }
                              const normalized = Array.from(nextValues).map((value) => {
                                const matched = (filter.options ?? []).find(
                                  (opt) => String(opt.value) === value
                                )
                                return matched ? matched.value : value
                              })
                              onUpdate({ value: normalized })
                            }}
                          >
                            {option.label}
                          </DropdownMenuCheckboxItem>
                        )
                      })}
                    </DropdownMenuContent>
                  </DropdownMenu>
                )
              ) : (
                <Select
                  value={
                    filter.value !== undefined && filter.value !== null
                      ? String(filter.value)
                      : filter.required
                        ? ''
                        : ALL_OPTION_VALUE
                  }
                  onValueChange={(nextValue) => {
                    if (!filter.required && nextValue === ALL_OPTION_VALUE) {
                      onUpdate({ value: null })
                      return
                    }
                    const options = filter.options ?? []
                    const matched = options.find((option) => String(option.value) === nextValue)
                    onUpdate({ value: matched ? matched.value : nextValue })
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t('components.filterEditor.defaultValue')} />
                  </SelectTrigger>
                  <SelectContent>
                    {!filter.required && <SelectItem value={ALL_OPTION_VALUE}>{t('components.filterEditor.all')}</SelectItem>}
                    {(filter.options ?? []).length === 0 ? (
                      <SelectItem value="__empty__" disabled>
                        {t('components.filterEditor.noOptions')}
                      </SelectItem>
                    ) : (
                      (filter.options ?? []).map((option) => (
                        <SelectItem key={String(option.value)} value={String(option.value)}>
                          {option.label}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              )
            ) : (
              <Input
                value={filter.value ?? ''}
                onChange={(event) => onUpdate({ value: event.target.value })}
                placeholder={t('components.filterEditor.defaultValue')}
              />
            )}
          </div>

          {(filter.type === 'dropdown_static' || filter.type === 'dropdown_datasource') && (
            <div className="space-y-2">
              <Label>{t('components.filterEditor.multiSelect')}</Label>
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={Boolean(filter.allowMultiple)}
                  onCheckedChange={(checked) => {
                    onUpdate({ allowMultiple: Boolean(checked) })
                  }}
                />
                <span className="text-sm text-muted-foreground">{t('components.filterEditor.multiSelect')}</span>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <Label>{t('components.filterEditor.required')}</Label>
            <div className="flex items-center gap-2">
              <Checkbox
                checked={Boolean(filter.required)}
                onCheckedChange={(checked) => {
                  onUpdate({ required: Boolean(checked) })
                }}
              />
              <span className="text-sm text-muted-foreground">{t('components.filterEditor.mustSelectValue')}</span>
            </div>
          </div>

          {filter.type === 'dropdown_datasource' && (
            <>
              <div className="space-y-2">
                <Label>{t('components.filterEditor.dataSource')}</Label>
                <Select
                  value={filter.dataSourceId ? String(filter.dataSourceId) : ''}
                  onValueChange={(value) => onUpdate({ dataSourceId: Number(value) })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t('components.filterEditor.dataSource')} />
                  </SelectTrigger>
                  <SelectContent>
                    {dataSources.map((source) => (
                      <SelectItem key={source.id} value={String(source.id)}>
                        {source.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>{t('components.filterEditor.optionSql')}</Label>
                <Input
                  value={filter.optionsQuery ?? ''}
                  onChange={(event) => onUpdate({ optionsQuery: event.target.value })}
                  placeholder="SELECT value, label FROM ..."
                />
              </div>
            </>
          )}

          {filter.type === 'dropdown_static' && (
            <div className="space-y-2">
              <Label>{t('components.filterEditor.staticOptions')}</Label>
              <Textarea
                value={staticOptionsInput}
                onChange={(event) => {
                  const nextValue = event.target.value
                  setStaticOptionsInput(nextValue)
                  onUpdate({ options: normalizeOptionsInput(nextValue) })
                }}
              />
            </div>
          )}
        </div>

        {error && (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="space-y-2 pt-4 border-t">
          <Button className="w-full" onClick={handleSave} disabled={isSaving}>
            {isSaving ? `${t('common.save')}...` : t('common.save')}
          </Button>
          <Button
            variant="destructive"
            onClick={handleRemoveClick}
            disabled={removeConfirm.isLoading}
            className="w-full"
          >
            {removeConfirm.isLoading ? `${t('common.delete')}...` : `${t('common.delete')} Filter`}
          </Button>
        </div>

        <ConfirmationDialog<DashboardFilter | null>
          open={removeConfirm.isOpen}
          item={removeConfirm.item}
          isLoading={removeConfirm.isLoading}
          title={t('components.filterEditor.deleteFilter')}
          description={(target) => (
            <>
              {t('components.filterEditor.deleteConfirmDesc', { name: target?.name })}
              <br />
              <span className="text-red-600">{t('components.filterEditor.irreversible')}</span>
            </>
          )}
          confirmText={t('common.deleteConfirm')}
          isDangerous
          onConfirm={handleConfirmRemove}
          onCancel={removeConfirm.close}
        />

        {/* Parameter change confirmation dialog */}
        {paramChangeConfirm && originalFilter && affectedWidgets.length > 0 && (
          <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center">
            <div className="bg-background border rounded-lg shadow-lg p-6 max-w-md space-y-4">
              <div>
                <h2 className="text-lg font-semibold">{t('components.filterEditor.paramChangeTitle')}</h2>
                <p className="text-sm text-muted-foreground mt-2">
                  {t('components.filterEditor.paramChangeDesc', { count: affectedWidgets.length })}
                </p>
              </div>

              <div className="max-h-48 overflow-y-auto">
                <div className="text-xs text-muted-foreground space-y-2">
                  <div className="font-medium text-foreground mb-2">{t('components.filterEditor.affectedWidgets')}:</div>
                  {affectedWidgets.map((widget) => (
                    <div key={widget.id} className="rounded-sm bg-muted px-2 py-1">
                      • {widget.id}
                    </div>
                  ))}
                </div>
              </div>

              <div className="text-xs text-muted-foreground bg-blue-50 rounded px-3 py-2 border border-blue-200">
                <div className="font-medium text-blue-900 mb-1">{t('components.filterEditor.willReplace')}:</div>
                {getParamChangeInfo(
                  getFilterParamNames(originalFilter),
                  getFilterParamNames(filter)
                ).map((info, idx) => (
                  <div key={idx}>
                    {info.old} → {info.new}
                  </div>
                ))}
              </div>

              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={handleCancelParamChange} disabled={isSaving}>
                  {t('common.cancel')}
                </Button>
                <Button variant="default" onClick={handleConfirmParamChange} disabled={isSaving}>
                  {isSaving ? `${t('components.filterEditor.confirmUpdate')}...` : t('components.filterEditor.confirmUpdate')}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
