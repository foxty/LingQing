import { useCallback, useState } from 'react'

import {
  bindTagValueToResource,
  listTagsForResource,
  unbindTagValueFromResource,
  type ResourceType,
  type TagBindingCreateRequest,
  type TagValueDTO,
} from '@/lib/tagsApi'

export function useTagBindings(resourceType: ResourceType, resourceId: number) {
  const [tags, setTags] = useState<TagValueDTO[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchTags = useCallback(async () => {
    if (!resourceId) return [] as TagValueDTO[]
    setLoading(true)
    setError(null)
    try {
      const data = await listTagsForResource(resourceType, resourceId)
      setTags(data)
      return data
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to fetch tags'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [resourceId, resourceType])

  const bindTagValue = useCallback(
    async (payload: TagBindingCreateRequest) => {
      setLoading(true)
      setError(null)
      try {
        const created = await bindTagValueToResource(resourceType, resourceId, payload)
        setTags((prev) => [...prev, created])
        return created
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to bind tag value'
        setError(errorMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [resourceId, resourceType]
  )

  const unbindTagValue = useCallback(
    async (tagValueId: number) => {
      setLoading(true)
      setError(null)
      try {
        await unbindTagValueFromResource(resourceType, resourceId, tagValueId)
        setTags((prev) => prev.filter((tag) => tag.id !== tagValueId))
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to unbind tag value'
        setError(errorMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [resourceId, resourceType]
  )

  return {
    tags,
    loading,
    error,
    fetchTags,
    bindTagValue,
    unbindTagValue,
    setTags,
  }
}
