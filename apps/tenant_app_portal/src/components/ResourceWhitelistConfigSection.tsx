import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    resourceWhitelist: {
      resourceType: 'Resource Type',
      tagDimension: 'Tag Dimension',
      valuePattern: 'Value Pattern',
      noConfigs: 'No configurations yet',
      configure: 'Configure',
      editTitle: 'Edit Resource Tag Configuration',
      editDesc: 'Configure which tag dimensions apply to this resource type',
      selectResourceType: 'Select Resource Type',
      enabledCol: 'Enabled',
      dimensionCol: 'Dimension',
      patternCol: 'Pattern',
      noDimensions: 'No tag dimensions available',
      selectPattern: 'Select pattern',
      disabled: 'Disabled',
      cancel: 'Cancel',
      save: 'Save',
      updateSuccess: 'Configuration updated',
      updateFailed: 'Failed to update configuration',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    resourceWhitelist: {
      resourceType: '资源类型',
      tagDimension: '标签维度',
      valuePattern: '值模式',
      noConfigs: '暂无配置',
      configure: '配置',
      editTitle: '编辑资源标签配置',
      editDesc: '配置哪些标签维度适用于此资源类型',
      selectResourceType: '选择资源类型',
      enabledCol: '启用',
      dimensionCol: '维度',
      patternCol: '模式',
      noDimensions: '没有可用的标签维度',
      selectPattern: '选择模式',
      disabled: '已禁用',
      cancel: '取消',
      save: '保存',
      updateSuccess: '配置已更新',
      updateFailed: '配置更新失败',
    },
  },
}, true, true)

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { ResourceTagConfigDTO, ResourceType, TagKeyDTO, TagValueMode } from '@/lib/tagsApi'

interface ResourceWhitelistConfigSectionProps {
  resourceTypes: ResourceType[]
  tagKeys: TagKeyDTO[]
  resourceTagConfigs: ResourceTagConfigDTO[]
  canManage: boolean
  loading: boolean
  defaultTagColor: string
  onCreateConfig: (payload: {
    resource_type: ResourceType
    tag_key_id: number
    value_mode: TagValueMode
  }) => Promise<unknown>
  onUpdateConfig: (id: number, payload: { value_mode: TagValueMode }) => Promise<unknown>
  onRemoveConfig: (id: number) => Promise<unknown>
  onFetchResourceTagConfigs: () => Promise<unknown>
  onError: (message: string) => void
  onSuccess: (message: string) => void
}

export default function ResourceWhitelistConfigSection({
  resourceTypes,
  tagKeys,
  resourceTagConfigs,
  canManage,
  loading,
  defaultTagColor,
  onCreateConfig,
  onUpdateConfig,
  onRemoveConfig,
  onFetchResourceTagConfigs,
  onError,
  onSuccess,
}: ResourceWhitelistConfigSectionProps) {
  const { t } = useTranslation()
  const [resourceConfigOpen, setResourceConfigOpen] = useState(false)
  const [resourceConfigType, setResourceConfigType] = useState<ResourceType>(
    resourceTypes[0] || 'user'
  )
  const [resourceConfigForm, setResourceConfigForm] = useState<
    Record<number, { enabled: boolean; valueMode: TagValueMode }>
  >({})

  const tagKeyMap = useMemo(() => {
    const map = new Map<number, TagKeyDTO>()
    tagKeys.forEach((key) => map.set(key.id, key))
    return map
  }, [tagKeys])

  const resourceConfigByType = useMemo(() => {
    const map = new Map<ResourceType, Map<number, ResourceTagConfigDTO>>()
    resourceTagConfigs.forEach((config) => {
      const typeMap = map.get(config.resource_type) || new Map<number, ResourceTagConfigDTO>()
      typeMap.set(config.tag_key_id, config)
      map.set(config.resource_type, typeMap)
    })
    return map
  }, [resourceTagConfigs])

  const handleOpenResourceConfig = (resourceType: ResourceType) => {
    setResourceConfigType(resourceType)
    const existing =
      resourceConfigByType.get(resourceType) || new Map<number, ResourceTagConfigDTO>()
    const next: Record<number, { enabled: boolean; valueMode: TagValueMode }> = {}
    tagKeys.forEach((key) => {
      const config = existing.get(key.id)
      next[key.id] = {
        enabled: Boolean(config),
        valueMode: (config?.value_mode || 'inclusive') as TagValueMode,
      }
    })
    setResourceConfigForm(next)
    setResourceConfigOpen(true)
  }

  const handleSaveResourceConfig = async () => {
    const existing =
      resourceConfigByType.get(resourceConfigType) || new Map<number, ResourceTagConfigDTO>()
    const tasks: Promise<unknown>[] = []

    Object.entries(resourceConfigForm).forEach(([keyId, config]) => {
      const numericKeyId = Number(keyId)
      const existingConfig = existing.get(numericKeyId)
      if (config.enabled) {
        if (existingConfig) {
          if (existingConfig.value_mode !== config.valueMode) {
            tasks.push(onUpdateConfig(existingConfig.id, { value_mode: config.valueMode }))
          }
        } else {
          tasks.push(
            onCreateConfig({
              resource_type: resourceConfigType,
              tag_key_id: numericKeyId,
              value_mode: config.valueMode,
            })
          )
        }
      } else if (existingConfig) {
        tasks.push(onRemoveConfig(existingConfig.id))
      }
    })

    try {
      if (tasks.length > 0) {
        await Promise.all(tasks)
      }
      await onFetchResourceTagConfigs()
      onSuccess(t('components.resourceWhitelist.updateSuccess'))
      setResourceConfigOpen(false)
    } catch (error: any) {
      onError(error.response?.data?.detail || t('components.resourceWhitelist.updateFailed'))
    }
  }

  return (
    <>
      <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('components.resourceWhitelist.resourceType')}</TableHead>
              <TableHead>{t('components.resourceWhitelist.tagDimension')}</TableHead>
              <TableHead>{t('components.resourceWhitelist.valuePattern')}</TableHead>
              <TableHead className="text-right">{t('common.operation')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {resourceTypes.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                 {t('components.resourceWhitelist.noConfigs')}
                 </TableCell>
              </TableRow>
            ) : (
              resourceTypes.map((type) => {
                const configs = Array.from(resourceConfigByType.get(type)?.values() || [])
                const keyNames = configs
                  .map((config) => tagKeyMap.get(config.tag_key_id)?.name || config.tag_key_id)
                  .join(', ')
                const modeSummary = configs
                  .map(
                    (config) =>
                      `${tagKeyMap.get(config.tag_key_id)?.name || config.tag_key_id}: ${config.value_mode || 'inclusive'}`
                  )
                  .join(', ')

                return (
                  <TableRow key={type}>
                    <TableCell>{type}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {keyNames || '—'}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {modeSummary || '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleOpenResourceConfig(type)}
                        disabled={!canManage}
                      >
                        {t('components.resourceWhitelist.configure')}
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>

      <Dialog open={resourceConfigOpen} onOpenChange={setResourceConfigOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('components.resourceWhitelist.editTitle')}</DialogTitle>
            <DialogDescription>{t('components.resourceWhitelist.editDesc')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label>{t('components.resourceWhitelist.selectResourceType')}</Label>
              <Select
                value={resourceConfigType}
                onValueChange={(value) => handleOpenResourceConfig(value as ResourceType)}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t('components.resourceWhitelist.selectResourceType')} />
                </SelectTrigger>
                <SelectContent>
                  {resourceTypes.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="overflow-hidden rounded-lg border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[140px]">{t('components.resourceWhitelist.enabledCol')}</TableHead>
                    <TableHead>{t('components.resourceWhitelist.dimensionCol')}</TableHead>
                    <TableHead className="w-[180px]">{t('components.resourceWhitelist.patternCol')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tagKeys.length === 0 ? (
                    <TableRow>
                        <TableCell
                          colSpan={3}
                          className="py-6 text-center text-sm text-muted-foreground"
                        >
                          {t('components.resourceWhitelist.noDimensions')}
                        </TableCell>
                    </TableRow>
                  ) : (
                    tagKeys.map((key) => {
                      const formItem = resourceConfigForm[key.id]
                      const isDisabled = key.status !== 'active'
                      return (
                        <TableRow key={key.id}>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <Switch
                                checked={formItem?.enabled ?? false}
                                onCheckedChange={(checked) =>
                                  setResourceConfigForm((prev) => ({
                                    ...prev,
                                    [key.id]: {
                                      enabled: checked,
                                      valueMode: prev[key.id]?.valueMode || 'inclusive',
                                    },
                                  }))
                                }
                                disabled={isDisabled || !canManage}
                                aria-label={t('common.toggle') + ' ' + key.name}
                              />
                              <span className="text-sm text-muted-foreground">
                                {formItem?.enabled ? t('components.resourceWhitelist.enabledCol') : t('components.resourceWhitelist.disabled')}
                              </span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span
                                className="h-2.5 w-2.5 rounded-full border"
                                style={{ backgroundColor: key.color || defaultTagColor }}
                              />
                              <span>{key.name}</span>
                              {isDisabled && (
                                  <Badge variant="outline" className="ml-2">
                                    {t('components.resourceWhitelist.disabled')}
                                  </Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <Select
                              value={formItem?.valueMode || 'inclusive'}
                              onValueChange={(value) =>
                                setResourceConfigForm((prev) => ({
                                  ...prev,
                                  [key.id]: {
                                    enabled: prev[key.id]?.enabled ?? false,
                                    valueMode: value as TagValueMode,
                                  },
                                }))
                              }
                              disabled={!formItem?.enabled || isDisabled || !canManage}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder={t('components.resourceWhitelist.selectPattern')} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="inclusive">inclusive</SelectItem>
                                <SelectItem value="exclusive">exclusive</SelectItem>
                              </SelectContent>
                            </Select>
                          </TableCell>
                        </TableRow>
                      )
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setResourceConfigOpen(false)}>
              {t('components.resourceWhitelist.cancel')}
            </Button>
            <Button onClick={handleSaveResourceConfig} disabled={!canManage || loading}>
              {t('components.resourceWhitelist.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
