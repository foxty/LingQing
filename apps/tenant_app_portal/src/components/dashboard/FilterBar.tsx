import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useEffect, useMemo, useState } from 'react'

import {
  getDatasourceOptionFilterIds,
  getDatasourceOptionsSourceKey,
} from '@/lib/dashboardFilterUpdates'

i18n.addResourceBundle('en', 'translation', {
  components: {
    filterBar: {
      all: 'All',
      pleaseSelect: 'Please select',
      noOptions: 'No options',
      newFilter: 'New Filter',
      noFilters: 'No filters',
      brokenFilters: '{{count}} filter(s) have errors',
      optionLoadFailed: 'Failed to load options',
      optionLoadError: 'Error loading options',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    filterBar: {
      all: '全部',
      pleaseSelect: '请选择',
      noOptions: '无选项',
      newFilter: '新建筛选',
      noFilters: '无筛选条件',
      brokenFilters: '{{count}} 个筛选条件有错误',
      optionLoadFailed: '加载选项失败',
      optionLoadError: '加载选项出错',
    },
  },
}, true, true)
import { AlertCircle, Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import TimeRangePicker from '@/components/dashboard/filters/TimeRangePicker'

import {
  type DashboardFilter,
  type DashboardFilterOption,
  getDashboardFilterOptions,
} from '@/lib/dashboardApi'

interface FilterBarProps {
  dashboardId: number
  filters: DashboardFilter[]
  isEditing: boolean
  selectedFilterId?: string | null
  onFiltersChange: (filters: DashboardFilter[]) => void
  onEditFilter: (filterId: string) => void
  onCreateFilter: () => void
}

const ALL_OPTION_VALUE = '__all__'

type FilterOptionItem = {
  label: string
  valueStr: string
  rawValue: DashboardFilterOption['value']
}

const buildSafeOptions = (options: DashboardFilterOption[]): FilterOptionItem[] =>
  options
    .map((option) => {
      const rawValue = option.value
      const valueStr =
        rawValue === null || rawValue === undefined || rawValue === '' ? '' : String(rawValue)
      return {
        label: option.label,
        valueStr,
        rawValue,
      }
    })
    .filter((option) => option.valueStr !== '')

const isAllSelectedValue = (filter: DashboardFilter, currentValue: DashboardFilter['value']) =>
  !filter.required &&
  (currentValue === null ||
    currentValue === undefined ||
    (Array.isArray(currentValue) && currentValue.length === 0))

const normalizeSelectedValues = (
  selectedValues: Array<string | number>,
  safeOptions: FilterOptionItem[]
) =>
  selectedValues.map((value) => {
    const matched = safeOptions.find((option) => option.valueStr === String(value))
    return matched ? matched.rawValue : value
  })

const FilterValue = ({
  filter,
  options,
  hasError,
  onUpdate,
}: {
  filter: DashboardFilter
  options: DashboardFilterOption[]
  hasError?: boolean
  onUpdate: (patch: Partial<DashboardFilter>) => void
}) => {
  const { t } = useTranslation()
  const errorBorderClass = hasError ? 'border-destructive focus-visible:ring-destructive/40' : ''

  if (filter.type === 'time_range') {
    return (
      <TimeRangePicker
        value={filter.value}
        onChange={(nextValue) =>
          onUpdate({
            value: nextValue,
          })
        }
        precision={filter.timePrecision || 'datetime'}
      />
    )
  }

  if (filter.type === 'dropdown_static' || filter.type === 'dropdown_datasource') {
    const safeOptions = buildSafeOptions(options)
    const currentValue = filter.value
    const allowMultiple = Boolean(filter.allowMultiple)
    const isAllSelected = isAllSelectedValue(filter, currentValue)

    if (allowMultiple) {
      const selectedValues = Array.isArray(currentValue)
        ? currentValue
        : currentValue === null || currentValue === undefined
          ? []
          : [currentValue]
      const displayValue = safeOptions
        .filter((option) => selectedValues.some((value) => String(value) === option.valueStr))
        .map((option) => option.label)
        .join(', ')

      return (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className={`w-72 justify-between ${errorBorderClass}`}
            >
              <span className="truncate">{isAllSelected ? t('components.filterBar.all') : displayValue || t('components.filterBar.pleaseSelect')}</span>
              <span className="ml-2 text-xs text-muted-foreground">{selectedValues.length}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-72 z-50">
            {!filter.required && (
              <DropdownMenuCheckboxItem
                key={ALL_OPTION_VALUE}
                checked={isAllSelected}
                onCheckedChange={(checked) => {
                  if (checked) {
                    onUpdate({ value: null })
                  } else {
                    onUpdate({ value: [] })
                  }
                }}
              >
                {t('components.filterBar.all')}
              </DropdownMenuCheckboxItem>
            )}
            {safeOptions.length === 0 ? (
              <div className="px-2 py-1.5 text-xs text-muted-foreground">{t('components.filterBar.noOptions')}</div>
            ) : (
              safeOptions.map((option) => {
                const isChecked = selectedValues.some((value) => String(value) === option.valueStr)
                return (
                  <DropdownMenuCheckboxItem
                    key={option.valueStr}
                    checked={isChecked}
                    onCheckedChange={(checked) => {
                      const nextValues = new Set(selectedValues.map((value) => String(value)))
                      if (checked) {
                        nextValues.add(option.valueStr)
                      } else {
                        nextValues.delete(option.valueStr)
                      }
                      const normalized = normalizeSelectedValues(
                        Array.from(nextValues),
                        safeOptions
                      )
                      onUpdate({ value: normalized })
                    }}
                  >
                    {option.label}
                  </DropdownMenuCheckboxItem>
                )
              })
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )
    }

    return (
      <Select
        value={
          currentValue !== undefined && currentValue !== null
            ? String(currentValue)
            : filter.required
              ? ''
              : ALL_OPTION_VALUE
        }
        onValueChange={(nextValue) => {
          if (!filter.required && nextValue === ALL_OPTION_VALUE) {
            onUpdate({ value: null })
            return
          }
          const matched = safeOptions.find((option) => option.valueStr === nextValue)
          onUpdate({ value: matched ? matched.rawValue : nextValue })
        }}
      >
          <SelectTrigger className={`w-56 ${errorBorderClass}`}>
            <SelectValue placeholder={t('components.filterBar.pleaseSelect')} />
          </SelectTrigger>
        <SelectContent>
          {!filter.required && <SelectItem value={ALL_OPTION_VALUE}>{t('components.filterBar.all')}</SelectItem>}
          {safeOptions.map((option) => (
            <SelectItem key={option.valueStr} value={option.valueStr}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  return (
    <Input
      value={filter.value ?? ''}
      onChange={(event) => onUpdate({ value: event.target.value })}
      className={`w-64 ${errorBorderClass}`}
    />
  )
}

const FilterItem = ({
  filter,
  isEditing,
  isSelected,
  isHighlighted,
  options,
  optionError,
  onEdit,
  onUpdate,
}: {
  filter: DashboardFilter
  isEditing: boolean
  isSelected: boolean
  isHighlighted: boolean
  options: DashboardFilterOption[]
  optionError?: string
  onEdit: () => void
  onUpdate: (patch: Partial<DashboardFilter>) => void
}) => {
  const { t } = useTranslation()
  const hasError = Boolean(optionError)
  const [errorOpen, setErrorOpen] = useState(false)

  return (
    <div
      className={`flex items-center gap-3 rounded-md px-2 py-2 w-max transition-colors ${
        isSelected ? 'bg-blue-200 ring-2 ring-blue-400' : isHighlighted ? 'bg-yellow-100' : ''
      } ${isEditing ? 'cursor-pointer hover:bg-muted/50' : ''}`}
      onClick={() => {
        if (isEditing) {
          onEdit()
        }
      }}
    >
      <div className="min-w-[120px] text-sm font-medium flex items-center gap-1.5">
        {hasError && optionError && (
          <Popover open={errorOpen} onOpenChange={setErrorOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="inline-flex items-center"
                aria-label={t('components.filterBar.optionLoadFailed')}
                onClick={(event) => {
                  event.stopPropagation()
                  setErrorOpen((prev) => !prev)
                }}
                onMouseEnter={() => setErrorOpen(true)}
                onMouseLeave={() => setErrorOpen(false)}
                onFocus={() => setErrorOpen(true)}
                onBlur={() => setErrorOpen(false)}
              >
                <AlertCircle className="h-3.5 w-3.5 text-destructive" />
              </button>
            </PopoverTrigger>
            <PopoverContent
              className="w-80 px-3 py-2 text-xs"
              align="start"
              side="top"
              onMouseEnter={() => setErrorOpen(true)}
              onMouseLeave={() => setErrorOpen(false)}
            >
              {optionError}
            </PopoverContent>
          </Popover>
        )}
        {filter.name}
      </div>
      <div onClick={(event) => event.stopPropagation()}>
        <FilterValue filter={filter} options={options} hasError={hasError} onUpdate={onUpdate} />
      </div>
    </div>
  )
}

export default function FilterBar({
  dashboardId,
  filters,
  isEditing,
  selectedFilterId,
  onFiltersChange,
  onEditFilter,
  onCreateFilter,
}: FilterBarProps) {
  const { t } = useTranslation()
  const [optionsMap, setOptionsMap] = useState<Record<string, DashboardFilterOption[]>>({})
  const [optionErrorsMap, setOptionErrorsMap] = useState<Record<string, string>>({})
  const [highlightedFilterIds, setHighlightedFilterIds] = useState<Set<string>>(new Set())
  const optionSourceKey = getDatasourceOptionsSourceKey(filters)
  const optionSources = useMemo(
    () => getDatasourceOptionFilterIds(filters),
    // Identity is optionSourceKey so value-only edits do not reload options.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- filters content is keyed above
    [optionSourceKey]
  )

  useEffect(() => {
    let cancelled = false

    const loadOptions = async () => {
      if (optionSources.length === 0) {
        if (!cancelled) {
          setOptionErrorsMap({})
        }
        return
      }

      const updated: Record<string, DashboardFilterOption[]> = {}
      const optionErrors: Record<string, string> = {}
      for (const filterId of optionSources) {
        try {
          const result = await getDashboardFilterOptions(dashboardId, filterId)
          updated[filterId] = result.options
          if (result.hasError) {
            optionErrors[filterId] = result.errorMessage || t('components.filterBar.optionLoadError')
          }
        } catch {
          updated[filterId] = []
          optionErrors[filterId] = t('components.filterBar.optionLoadFailed')
        }
      }
      if (!cancelled) {
        setOptionsMap((prev) => ({ ...prev, ...updated }))
        setOptionErrorsMap(optionErrors)
      }
    }

    void loadOptions()
    return () => {
      cancelled = true
    }
  }, [optionSources, dashboardId, t])

  const brokenFilterCount = filters.filter((filter) => Boolean(optionErrorsMap[filter.id])).length

  const updateFilter = (filterId: string, patch: Partial<DashboardFilter>) => {
    const nextFilters = filters.map((filter) =>
      filter.id === filterId
        ? {
            ...filter,
            ...patch,
          }
        : filter
    )
    onFiltersChange(nextFilters)

    // Highlight the modified filter
    setHighlightedFilterIds((prev) => new Set(prev).add(filterId))
    const timer = setTimeout(() => {
      setHighlightedFilterIds((prev) => {
        const next = new Set(prev)
        next.delete(filterId)
        return next
      })
    }, 1500)
    return () => clearTimeout(timer)
  }

  return (
    <div className="space-y-3 rounded-lg border bg-background px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">Filters</div>
        {isEditing && (
          <Button size="sm" variant="outline" onClick={onCreateFilter}>
            <Plus className="mr-2 h-4 w-4" />
            {t('components.filterBar.newFilter')}
          </Button>
        )}
      </div>

      {filters.length === 0 && <div className="text-sm text-muted-foreground">{t('components.filterBar.noFilters')}</div>}

      {brokenFilterCount > 0 && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {t('components.filterBar.brokenFilters', { count: brokenFilterCount })}
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        {filters.map((filter) => (
          <FilterItem
            key={filter.id}
            filter={filter}
            options={
              filter.type === 'dropdown_datasource'
                ? (optionsMap[filter.id] ?? [])
                : (filter.options ?? [])
            }
            isEditing={isEditing}
            isSelected={selectedFilterId === filter.id}
            isHighlighted={highlightedFilterIds.has(filter.id)}
            optionError={optionErrorsMap[filter.id]}
            onEdit={() => onEditFilter(filter.id)}
            onUpdate={(patch) => updateFilter(filter.id, patch)}
          />
        ))}
      </div>
    </div>
  )
}
