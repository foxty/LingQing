import { describe, expect, it, vi } from 'vitest'
import type { AssetListResponse, AssetMetadata } from '@/lib/dataSourceApi'
import { loadImportedSelection, toDiscoveredAsset } from '@/lib/importedAssetSelection'

function asset(
  overrides: Partial<AssetMetadata> & Pick<AssetMetadata, 'asset_name' | 'asset_type'>
): AssetMetadata {
  return {
    id: 1,
    data_source_id: 1,
    columns: [],
    source_info: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('toDiscoveredAsset', () => {
  it('keeps warehouse asset names and drops other types', () => {
    const table = toDiscoveredAsset(
      asset({
        asset_name: 'test_catalog.test_schema.orders_1',
        asset_type: 'table',
        row_count: 4,
        columns: [{ name: 'id', data_type: 'int' }],
      })
    )
    expect(table).toMatchObject({
      name: 'test_catalog.test_schema.orders_1',
      type: 'table',
      row_count: 4,
    })
    expect(
      toDiscoveredAsset(asset({ asset_name: 'api.orders', asset_type: 'api_endpoint' }))
    ).toBeNull()
  })
})

describe('loadImportedSelection', () => {
  it('merges every page and skips non-warehouse assets', async () => {
    const page = (items: AssetMetadata[], totalPages: number): AssetListResponse => ({
      items,
      total: 2,
      page: 1,
      page_size: 100,
      total_pages: totalPages,
    })
    const listPage = vi
      .fn()
      .mockResolvedValueOnce(
        page(
          [
            asset({ asset_name: 'test_catalog.test_schema.orders_1', asset_type: 'table' }),
            asset({ asset_name: 'connector.lookup', asset_type: 'api_endpoint' }),
          ],
          2
        )
      )
      .mockResolvedValueOnce(
        page([asset({ asset_name: 'test_catalog.other.events_2', asset_type: 'view' })], 2)
      )

    const selected = await loadImportedSelection(7, listPage)

    expect(listPage).toHaveBeenCalledTimes(2)
    expect(Object.keys(selected).sort()).toEqual([
      'test_catalog.other.events_2',
      'test_catalog.test_schema.orders_1',
    ])
  })
})
