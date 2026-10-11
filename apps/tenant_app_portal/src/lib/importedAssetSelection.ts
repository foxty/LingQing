import {
  listAssets,
  resolveAssetDescription,
  type AssetListResponse,
  type AssetMetadata,
  type DiscoveredAsset,
} from '@/lib/dataSourceApi'

const PAGE_SIZE = 100

type ImportedAsset = Pick<
  AssetMetadata,
  'asset_name' | 'asset_type' | 'columns' | 'row_count' | 'meta' | 'meta_override'
>

export function toDiscoveredAsset(asset: ImportedAsset): DiscoveredAsset | null {
  if (
    asset.asset_type !== 'table' &&
    asset.asset_type !== 'view' &&
    asset.asset_type !== 'materialized_view'
  ) {
    return null
  }
  return {
    name: asset.asset_name,
    type: asset.asset_type,
    description: resolveAssetDescription(asset as AssetMetadata),
    row_count: asset.row_count,
    columns: asset.columns?.map((column) => ({
      name: column.name,
      data_type: column.data_type,
    })),
  }
}

export async function loadImportedSelection(
  dataSourceId: number,
  listPage: (
    dataSourceId: number,
    page: number,
    pageSize: number
  ) => Promise<AssetListResponse> = listAssets
): Promise<Record<string, DiscoveredAsset>> {
  const selected: Record<string, DiscoveredAsset> = {}
  let page = 1
  let totalPages = 1
  do {
    const result = await listPage(dataSourceId, page, PAGE_SIZE)
    for (const item of result.items) {
      const asset = toDiscoveredAsset(item)
      if (asset) selected[asset.name] = asset
    }
    totalPages = result.total_pages ?? 0
    page += 1
  } while (page <= totalPages)
  return selected
}
