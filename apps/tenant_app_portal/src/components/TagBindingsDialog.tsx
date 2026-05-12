import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    tagBindingsDialog: {
      description: 'Select tag values to apply to this resource',
      noPermission: 'You do not have permission to view tags',
      noDimensions: 'No tag dimensions are configured for this resource type',
      noTagValues: 'No tag values for this dimension',
      unbindSuccess: 'Tag removed successfully',
      bindingSuccess: 'Tag applied successfully',
      bindFailed: 'Failed to apply tag',
      unbindFailed: 'Failed to remove tag',
      close: 'Close',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    tagBindingsDialog: {
      description: '选择要应用于此资源的标签值',
      noPermission: '你没有查看标签的权限',
      noDimensions: '此资源类型未配置标签维度',
      noTagValues: '该维度下没有标签值',
      unbindSuccess: '标签移除成功',
      bindingSuccess: '标签应用成功',
      bindFailed: '标签应用失败',
      unbindFailed: '标签移除失败',
      close: '关闭',
    },
  },
}, true, true)
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useNotification } from '@/hooks/useNotification'
import { useTagBindings } from '@/hooks/useTagBindings'
import { useTags } from '@/hooks/useTags'
import {
  bindTagValueToResource,
  listTagsForResource,
  unbindTagValueFromResource,
  type ResourceType,
  type TagKeyDTO,
  type TagValueDTO,
} from '@/lib/tagsApi'
import { Check } from 'lucide-react'

interface TagBindingsDialogProps {
  resourceType: ResourceType
  resourceId: number
  title: string
  canManage: boolean
  canRead?: boolean
  selectedResourceIds?: number[]
  onTagsUpdated?: (resourceId: number, tags: TagValueDTO[]) => void
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children?: ReactNode
}

export default function TagBindingsDialog({
  resourceType,
  resourceId,
  title,
  canManage,
  canRead = true,
  selectedResourceIds,
  onTagsUpdated,
  open: controlledOpen,
  onOpenChange,
  children,
}: TagBindingsDialogProps) {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()
  const { fetchTagKeys, fetchTagValues, fetchResourceTagConfigs } = useTags()
  const { tags, loading, fetchTags, bindTagValue, unbindTagValue, setTags } = useTagBindings(
    resourceType,
    resourceId
  )

  const [internalOpen, setInternalOpen] = useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = onOpenChange ?? setInternalOpen
  const [tagKeys, setTagKeys] = useState<TagKeyDTO[]>([])
  const [allowedKeyIds, setAllowedKeyIds] = useState<number[]>([])
  const [tagValuesByKey, setTagValuesByKey] = useState<Record<number, TagValueDTO[]>>({})
  const [bulkLoading, setBulkLoading] = useState(false)

  const allowedKeys = useMemo(
    () => tagKeys.filter((key) => allowedKeyIds.includes(key.id)),
    [allowedKeyIds, tagKeys]
  )

  const boundTagValueIds = useMemo(() => new Set(tags.map((tag) => tag.id)), [tags])

  const tagKeyMap = useMemo(() => {
    const map = new Map<number, TagKeyDTO>()
    tagKeys.forEach((key) => map.set(key.id, key))
    return map
  }, [tagKeys])

  const targetResourceIds = useMemo(() => {
    if (!selectedResourceIds || selectedResourceIds.length === 0) {
      return [resourceId]
    }
    const unique = new Set<number>(selectedResourceIds)
    unique.add(resourceId)
    return Array.from(unique)
  }, [selectedResourceIds, resourceId])

  const isBatchMode = selectedResourceIds !== undefined && targetResourceIds.length > 1

  const fetchTagsForResources = useCallback(
    async (resourceIds: number[]) => {
      const results = await Promise.all(
        resourceIds.map(async (id) => {
          const tags = await listTagsForResource(resourceType, id)
          return { resourceId: id, tags }
        })
      )
      return results
    },
    [resourceType]
  )

  const buildUnionTags = useCallback((items: Array<{ tags: TagValueDTO[] }>) => {
    const unionMap = new Map<number, TagValueDTO>()
    items.forEach(({ tags }) => {
      tags.forEach((tag) => {
        unionMap.set(tag.id, tag)
      })
    })
    return Array.from(unionMap.values())
  }, [])

  const refreshData = useCallback(async () => {
    if (!resourceId || !canRead) return
    try {
      const [keys, configs] = await Promise.all([
        fetchTagKeys(),
        fetchResourceTagConfigs(resourceType),
      ])
      setTagKeys(keys)
      const configKeyIds = configs.map((config) => config.tag_key_id)
      setAllowedKeyIds(configKeyIds)

      const valuesByKey: Record<number, TagValueDTO[]> = {}
      await Promise.all(
        configKeyIds.map(async (keyId) => {
          const values = await fetchTagValues(keyId)
          valuesByKey[keyId] = values
        })
      )
      setTagValuesByKey(valuesByKey)

      if (isBatchMode) {
        const results = await fetchTagsForResources(targetResourceIds)
        const unionTags = buildUnionTags(results)
        setTags(unionTags)
      } else {
        const boundTags = await fetchTags()
        setTags(boundTags)
      }
    } catch (error: any) {
      showError(error.response?.data?.detail || t('common.failedToLoad'))
    }
  }, [
    canRead,
    buildUnionTags,
    fetchTagsForResources,
    fetchResourceTagConfigs,
    fetchTagKeys,
    fetchTagValues,
    fetchTags,
    isBatchMode,
    resourceId,
    resourceType,
    setTags,
    showError,
    targetResourceIds,
  ])

  useEffect(() => {
    if (open) {
      refreshData()
    }
  }, [open, refreshData])

  const handleToggleTag = async (tagValueId: number, bound: boolean, status: string) => {
    if (!canManage) return
    if (!bound && status !== 'active') return

    if (isBatchMode) {
      setBulkLoading(true)
      try {
        await Promise.all(
          targetResourceIds.map(async (id) => {
            if (bound) {
              try {
                await unbindTagValueFromResource(resourceType, id, tagValueId)
              } catch (error: any) {
                const status = error?.response?.status
                if (status !== 404) {
                  throw error
                }
              }
              return
            }
            await bindTagValueToResource(resourceType, id, { tag_value_id: tagValueId })
          })
        )
        const results = await fetchTagsForResources(targetResourceIds)
        const unionTags = buildUnionTags(results)
        setTags(unionTags)
        if (onTagsUpdated) {
          results.forEach(({ resourceId: id, tags }) => onTagsUpdated(id, tags))
        }
        showSuccess(bound ? t('components.tagBindingsDialog.unbindSuccess') : t('components.tagBindingsDialog.bindingSuccess'))
      } catch (error: any) {
        showError(error.response?.data?.detail || (bound ? t('components.tagBindingsDialog.unbindFailed') : t('components.tagBindingsDialog.bindFailed')))
      } finally {
        setBulkLoading(false)
      }
      return
    }

    try {
      if (bound) {
        await unbindTagValue(tagValueId)
      } else {
        await bindTagValue({ tag_value_id: tagValueId })
      }
      const nextTags = await fetchTags()
      onTagsUpdated?.(resourceId, nextTags)
      showSuccess(bound ? t('components.tagBindingsDialog.unbindSuccess') : t('components.tagBindingsDialog.bindingSuccess'))
    } catch (error: any) {
      showError(error.response?.data?.detail || (bound ? t('components.tagBindingsDialog.unbindFailed') : t('components.tagBindingsDialog.bindFailed')))
    }
  }

  const isBusy = loading || bulkLoading
  const isControlled = controlledOpen !== undefined

  const panelBody = (
    <>
      {!canRead ? (
        <div className="text-sm text-muted-foreground">{t('components.tagBindingsDialog.noPermission')}</div>
      ) : (
        <div className="space-y-5">
          {allowedKeys.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              {t('components.tagBindingsDialog.noDimensions')}
            </div>
          ) : (
            <div className="space-y-5">
              {allowedKeys.map((key) => {
                const values = tagValuesByKey[key.id] || []
                return (
                  <div key={key.id} className="space-y-3">
                    <div>
                      <div className="text-sm font-semibold">{key.name}</div>
                    </div>

                    {values.length === 0 ? (
                      <div className="text-sm text-muted-foreground">{t('components.tagBindingsDialog.noTagValues')}</div>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {values.map((value) => {
                          const bound = boundTagValueIds.has(value.id)
                          const tagColor = tagKeyMap.get(value.key_id)?.color || '#64748b'
                          const isDisabled =
                            !canManage || isBusy || (!bound && value.status !== 'active')

                          return (
                            <button
                              key={value.id}
                              type="button"
                              onClick={() => handleToggleTag(value.id, bound, value.status)}
                              disabled={isDisabled}
                              aria-pressed={bound}
                              className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs transition-colors ${
                                bound ? 'shadow-sm' : 'bg-transparent'
                              } ${
                                isDisabled
                                  ? 'opacity-60 cursor-not-allowed'
                                  : 'hover:opacity-90'
                              }`}
                              style={
                                bound
                                  ? {
                                      backgroundColor: tagColor,
                                      borderColor: tagColor,
                                      color: '#fff',
                                    }
                                  : {
                                      borderColor: tagColor,
                                      color: tagColor,
                                    }
                              }
                            >
                              <span>{value.value}</span>
                              {bound && <Check className="h-3 w-3" />}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
          {t('components.tagBindingsDialog.close')}
        </Button>
      </div>
    </>
  )

  if (isControlled) {
    return (
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{t('components.tagBindingsDialog.description')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">{panelBody}</div>
        </DialogContent>
      </Dialog>
    )
  }

  if (!children) {
    return null
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        className="w-[420px] max-h-[70vh] overflow-y-auto"
        align="start"
        side="right"
        sideOffset={8}
        collisionPadding={16}
      >
        <div className="space-y-4">
          <div>
            <div className="text-sm font-semibold">{title}</div>
            <div className="text-xs text-muted-foreground">{t('components.tagBindingsDialog.description')}</div>
          </div>
          {panelBody}
        </div>
      </PopoverContent>
    </Popover>
  )
}
