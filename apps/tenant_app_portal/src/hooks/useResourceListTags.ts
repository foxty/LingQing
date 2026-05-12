import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  listTagKeys,
  listTagsForResource,
  type ResourceType,
  type TagKeyDTO,
  type TagValueDTO,
} from '@/lib/tagsApi'

export function useResourceListTags(
  resourceType: ResourceType,
  resources: Array<{ id: number }>,
  canReadTags: boolean
) {
  const [tagKeys, setTagKeys] = useState<TagKeyDTO[]>([])
  const [tagsMap, setTagsMap] = useState<Record<number, TagValueDTO[]>>({})

  const resourceIds = useMemo(() => resources.map((resource) => resource.id), [resources])
  const resourceIdsKey = resourceIds.join(',')

  useEffect(() => {
    if (!canReadTags) {
      return
    }
    listTagKeys()
      .then(setTagKeys)
      .catch(() => undefined)
  }, [canReadTags])

  useEffect(() => {
    if (!canReadTags || resourceIds.length === 0) {
      setTagsMap({})
      return
    }

    let cancelled = false
    Promise.all(
      resourceIds.map(async (id) => {
        const tags = await listTagsForResource(resourceType, id)
        return { id, tags }
      })
    )
      .then((results) => {
        if (cancelled) {
          return
        }
        const next: Record<number, TagValueDTO[]> = {}
        results.forEach(({ id, tags }) => {
          next[id] = tags
        })
        setTagsMap(next)
      })
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [canReadTags, resourceType, resourceIdsKey])

  const setTagsForResource = useCallback((resourceId: number, tags: TagValueDTO[]) => {
    setTagsMap((prev) => ({ ...prev, [resourceId]: tags }))
  }, [])

  return { tagKeys, tagsMap, setTagsForResource }
}
