import { describe, expect, it } from 'vitest'
import {
  collectDataSourceIdsFromDashboard,
  dataSourceSelectOptionsQueryKey,
} from './useDataSources'

describe('useDataSources helpers', () => {
  it('collectDataSourceIdsFromDashboard gathers widget and filter ids', () => {
    const ids = collectDataSourceIdsFromDashboard({
      layout: { cols: 12, rows: 12, gap: 16, rowHeight: 80 },
      widgets: [{ id: 'w1', dataSourceId: 3 } as any],
      filters: [{ id: 'f1', dataSourceId: 7 } as any],
    })
    expect(ids.sort((a, b) => a - b)).toEqual([3, 7])
  })

  it('dataSourceSelectOptionsQueryKey is stable for id order', () => {
    const a = dataSourceSelectOptionsQueryKey(1, [3, 1, 3])
    const b = dataSourceSelectOptionsQueryKey(1, [1, 3])
    expect(a).toEqual(b)
  })
})
