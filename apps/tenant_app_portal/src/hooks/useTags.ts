import { useCallback, useState } from 'react'

import {
  createResourceTagConfig,
  createTagKey,
  createTagValue,
  deleteResourceTagConfig,
  deleteTagKey,
  deleteTagValue,
  disableTagKey,
  disableTagValue,
  enableTagKey,
  enableTagValue,
  listResourceTagConfigs,
  listTagKeys,
  listTagValues,
  updateResourceTagConfig,
  updateTagKey,
  updateTagValue,
  type ResourceTagConfigCreateRequest,
  type ResourceTagConfigDTO,
  type ResourceTagConfigUpdateRequest,
  type ResourceType,
  type TagKeyCreateRequest,
  type TagKeyDTO,
  type TagKeyUpdateRequest,
  type TagValueCreateRequest,
  type TagValueDTO,
  type TagValueUpdateRequest,
} from '@/lib/tagsApi'

export function useTags() {
  const [tagKeys, setTagKeys] = useState<TagKeyDTO[]>([])
  const [tagValues, setTagValues] = useState<TagValueDTO[]>([])
  const [resourceTagConfigs, setResourceTagConfigs] = useState<ResourceTagConfigDTO[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchTagKeys = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listTagKeys()
      setTagKeys(data)
      return data
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to fetch tag keys'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchTagValues = useCallback(async (keyId?: number) => {
    setLoading(true)
    setError(null)
    try {
      const data = await listTagValues(keyId)
      if (!keyId) {
        setTagValues(data)
      }
      return data
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to fetch tag values'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchResourceTagConfigs = useCallback(async (resourceType?: ResourceType) => {
    setLoading(true)
    setError(null)
    try {
      const data = await listResourceTagConfigs(resourceType)
      if (!resourceType) {
        setResourceTagConfigs(data)
      }
      return data
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to fetch resource tag configs'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const createKey = useCallback(async (payload: TagKeyCreateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const created = await createTagKey(payload)
      setTagKeys((prev) => [...prev, created])
      return created
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to create tag key'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const updateKey = useCallback(async (tagKeyId: number, payload: TagKeyUpdateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const updated = await updateTagKey(tagKeyId, payload)
      setTagKeys((prev) => prev.map((key) => (key.id === tagKeyId ? updated : key)))
      return updated
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to update tag key'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const disableKey = useCallback(async (tagKeyId: number) => {
    setLoading(true)
    setError(null)
    try {
      const updated = await disableTagKey(tagKeyId)
      setTagKeys((prev) => prev.map((key) => (key.id === tagKeyId ? updated : key)))
      return updated
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to disable tag key'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const enableKey = useCallback(async (tagKeyId: number) => {
    setLoading(true)
    setError(null)
    try {
      const updated = await enableTagKey(tagKeyId)
      setTagKeys((prev) => prev.map((key) => (key.id === tagKeyId ? updated : key)))
      return updated
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to enable tag key'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const removeKey = useCallback(async (tagKeyId: number) => {
    setLoading(true)
    setError(null)
    try {
      await deleteTagKey(tagKeyId)
      setTagKeys((prev) => prev.filter((key) => key.id !== tagKeyId))
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to delete tag key'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const createValue = useCallback(async (payload: TagValueCreateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const created = await createTagValue(payload)
      setTagValues((prev) => [...prev, created])
      return created
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to create tag value'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const updateValue = useCallback(async (tagValueId: number, payload: TagValueUpdateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const updated = await updateTagValue(tagValueId, payload)
      setTagValues((prev) => prev.map((value) => (value.id === tagValueId ? updated : value)))
      return updated
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to update tag value'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const disableValue = useCallback(async (tagValueId: number) => {
    setLoading(true)
    setError(null)
    try {
      const updated = await disableTagValue(tagValueId)
      setTagValues((prev) => prev.map((value) => (value.id === tagValueId ? updated : value)))
      return updated
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to disable tag value'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const enableValue = useCallback(async (tagValueId: number) => {
    setLoading(true)
    setError(null)
    try {
      const updated = await enableTagValue(tagValueId)
      setTagValues((prev) => prev.map((value) => (value.id === tagValueId ? updated : value)))
      return updated
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to enable tag value'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const removeValue = useCallback(async (tagValueId: number) => {
    setLoading(true)
    setError(null)
    try {
      await deleteTagValue(tagValueId)
      setTagValues((prev) => prev.filter((value) => value.id !== tagValueId))
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to delete tag value'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const createConfig = useCallback(async (payload: ResourceTagConfigCreateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const created = await createResourceTagConfig(payload)
      setResourceTagConfigs((prev) => [...prev, created])
      return created
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to create resource tag config'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const updateConfig = useCallback(
    async (configId: number, payload: ResourceTagConfigUpdateRequest) => {
      setLoading(true)
      setError(null)
      try {
        const updated = await updateResourceTagConfig(configId, payload)
        setResourceTagConfigs((prev) =>
          prev.map((config) => (config.id === configId ? updated : config))
        )
        return updated
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to update resource tag config'
        setError(errorMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const removeConfig = useCallback(async (configId: number) => {
    setLoading(true)
    setError(null)
    try {
      await deleteResourceTagConfig(configId)
      setResourceTagConfigs((prev) => prev.filter((config) => config.id !== configId))
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to delete resource tag config'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    tagKeys,
    tagValues,
    resourceTagConfigs,
    loading,
    error,
    fetchTagKeys,
    fetchTagValues,
    fetchResourceTagConfigs,
    createKey,
    updateKey,
    disableKey,
    enableKey,
    removeKey,
    createValue,
    updateValue,
    disableValue,
    enableValue,
    removeValue,
    createConfig,
    updateConfig,
    removeConfig,
  }
}
