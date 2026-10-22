import type { QueryClient } from '@tanstack/react-query'
import type { MultiSelectOption } from '@/components/agents/MultiSelectField'
import type { AgentAttachmentAccessItem } from '@/lib/agentsApi'
import { listApiConnectors } from '@/lib/apiConnectorApi'
import { listDocumentCollections } from '@/lib/documentCollectionsApi'
import { listDataSources } from '@/lib/dataSourceApi'

export const AGENT_ATTACHMENT_RESOURCE = {
  knowledge: 'document_collection',
  dataSource: 'data_source',
  apiConnector: 'api_connector',
} as const

export type AgentAttachmentPickerKind = 'data_source' | 'document_collection' | 'api_connector'

export const agentAttachmentPickerQueryKeys = {
  root: (tenantId: number) => ['agent-attachment-picker', tenantId] as const,
  search: (tenantId: number, kind: AgentAttachmentPickerKind, query: string) =>
    ['agent-attachment-picker', tenantId, kind, query.trim().toLowerCase()] as const,
}

export function invalidateAgentAttachmentPickerQueries(
  queryClient: QueryClient,
  tenantId: number | undefined
): void {
  if (tenantId == null) {
    return
  }
  void queryClient.invalidateQueries({ queryKey: agentAttachmentPickerQueryKeys.root(tenantId) })
}

const PICKER_PAGE_SIZE = 20
const PICKER_LIST_STALE_MS = 60_000

export function attachmentLabelKey(resourceType: string, resourceId: number): string {
  return `${resourceType}:${resourceId}`
}

export function buildAttachmentLabelMap(
  items: AgentAttachmentAccessItem[] | undefined
): Map<string, string> {
  const map = new Map<string, string>()
  for (const item of items ?? []) {
    map.set(attachmentLabelKey(item.resource_type, item.resource_id), item.name)
  }
  return map
}

export function selectedAttachmentOptions(
  ids: number[],
  resourceType: string,
  labelMap: Map<string, string>,
  extraLabels: Record<string, string>
): MultiSelectOption[] {
  return ids.map((id) => {
    const key = attachmentLabelKey(resourceType, id)
    return {
      id: String(id),
      label: extraLabels[key] ?? labelMap.get(key) ?? `#${id}`,
    }
  })
}

async function searchAttachmentPickerPage(
  kind: AgentAttachmentPickerKind,
  query: string
): Promise<MultiSelectOption[]> {
  const trimmed = query.trim()
  const searchQuery = trimmed || undefined

  switch (kind) {
    case 'data_source': {
      const response = await listDataSources(1, PICKER_PAGE_SIZE, searchQuery)
      return (response.items ?? []).map((source) => ({
        id: String(source.id),
        label: source.name,
        description: source.type,
      }))
    }
    case 'document_collection': {
      const response = await listDocumentCollections(1, PICKER_PAGE_SIZE, searchQuery)
      return (response.items ?? []).map((collection) => ({
        id: String(collection.id),
        label: collection.name,
        description: collection.description ?? undefined,
      }))
    }
    case 'api_connector': {
      const response = await listApiConnectors(1, PICKER_PAGE_SIZE, searchQuery)
      return (response.items ?? []).map((connector) => ({
        id: String(connector.id),
        label: connector.name,
        description: connector.base_url,
      }))
    }
    default: {
      const _exhaustive: never = kind
      return _exhaustive
    }
  }
}

export async function searchAgentAttachmentPicker(
  queryClient: QueryClient,
  tenantId: number,
  kind: AgentAttachmentPickerKind,
  query: string
): Promise<MultiSelectOption[]> {
  const normalized = query.trim().toLowerCase()
  return queryClient.fetchQuery({
    queryKey: agentAttachmentPickerQueryKeys.search(tenantId, kind, normalized),
    queryFn: () => searchAttachmentPickerPage(kind, query),
    staleTime: PICKER_LIST_STALE_MS,
  })
}
