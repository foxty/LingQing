import { describe, expect, it } from 'vitest'

import type { DashboardFilter } from '@/lib/dashboardApi'
import {
  collectValueOnlyFilterUpdates,
  getDatasourceOptionFilterIds,
  getDatasourceOptionsSourceKey,
  getWidgetFilterSignature,
  isValueOnlyFilterChange,
  widgetUsesFilter,
} from '@/lib/dashboardFilterUpdates'

const baseFilter = (overrides: Partial<DashboardFilter> = {}): DashboardFilter => ({
  id: 'filter-region',
  name: 'Region',
  type: 'dropdown_datasource',
  paramKey: 'region',
  value: 'apac',
  dataSourceId: 3,
  optionsQuery: 'SELECT region AS value FROM dim_region',
  required: false,
  ...overrides,
})

describe('getDatasourceOptionsSourceKey', () => {
  it('ignores value-only changes', () => {
    const before = getDatasourceOptionsSourceKey([baseFilter({ value: 'apac' })])
    const after = getDatasourceOptionsSourceKey([baseFilter({ value: 'emea' })])
    expect(after).toBe(before)
  })

  it('changes when options query or data source changes', () => {
    const before = getDatasourceOptionsSourceKey([baseFilter()])
    const afterQuery = getDatasourceOptionsSourceKey([
      baseFilter({ optionsQuery: 'SELECT DISTINCT region FROM dim_region' }),
    ])
    const afterSource = getDatasourceOptionsSourceKey([baseFilter({ dataSourceId: 9 })])
    expect(afterQuery).not.toBe(before)
    expect(afterSource).not.toBe(before)
  })
})

describe('isValueOnlyFilterChange', () => {
  it('returns true when only value changes', () => {
    expect(isValueOnlyFilterChange(baseFilter({ value: 'apac' }), baseFilter({ value: 'emea' }))).toBe(
      true
    )
  })

  it('returns false when definition fields change', () => {
    expect(
      isValueOnlyFilterChange(baseFilter(), baseFilter({ name: 'Market', value: 'emea' }))
    ).toBe(false)
  })
})

describe('getDatasourceOptionFilterIds', () => {
  it('returns datasource filter ids', () => {
    expect(
      getDatasourceOptionFilterIds([
        baseFilter({ id: 'filter-a' }),
        baseFilter({ id: 'filter-b', type: 'time_range', paramKey: 'time' }),
      ])
    ).toEqual(['filter-a'])
  })
})

describe('collectValueOnlyFilterUpdates', () => {
  it('collects value-only updates and skips unsaved new filters', () => {
    const previous = [baseFilter({ value: 'apac' })]
    const next = [
      baseFilter({ value: 'emea' }),
      baseFilter({ id: 'filter-new', paramKey: 'new_filter', value: 'x' }),
    ]
    expect(collectValueOnlyFilterUpdates(previous, next, 'filter-new')).toEqual([
      { id: 'filter-region', value: 'emea' },
    ])
  })
})

describe('widgetUsesFilter', () => {
  it('matches explicit param tokens and ignores unused filters', () => {
    const region = baseFilter()
    const channel = baseFilter({ id: 'filter-channel', paramKey: 'channel' })
    expect(widgetUsesFilter('SELECT 1 FROM orders WHERE $in_or_equal(:region, region)', region)).toBe(
      true
    )
    expect(widgetUsesFilter('SELECT 1 FROM orders WHERE $in_or_equal(:region, region)', channel)).toBe(
      false
    )
  })

  it('matches implicit time filter macros', () => {
    const timeFilter = baseFilter({
      id: 'filter-time',
      type: 'time_range',
      paramKey: 'time',
    })
    expect(widgetUsesFilter('SELECT 1 FROM orders WHERE $time_filter(order_date)', timeFilter)).toBe(
      true
    )
  })
})

describe('getWidgetFilterSignature', () => {
  it('changes only when a bound filter value changes', () => {
    const region = baseFilter({ value: 'apac' })
    const channel = baseFilter({ id: 'filter-channel', paramKey: 'channel', value: 'web' })
    const widget = { query: 'SELECT 1 FROM orders WHERE $in_or_equal(:region, region)' }

    const before = getWidgetFilterSignature(widget, [region, channel])
    const afterRegion = getWidgetFilterSignature(widget, [{ ...region, value: 'emea' }, channel])
    const afterUnused = getWidgetFilterSignature(widget, [region, { ...channel, value: 'app' }])

    expect(afterRegion).not.toBe(before)
    expect(afterUnused).toBe(before)
    expect(getWidgetFilterSignature({ query: 'SELECT 1' }, [region])).toBe('')
  })
})
