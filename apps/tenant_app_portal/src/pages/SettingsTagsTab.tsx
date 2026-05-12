import i18n from '@/i18n/config'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    tagsTab: {
      dimensionCreated: 'Dimension created',
      dimensionUpdated: 'Dimension updated',
      levelMustBePositive: 'Level must be a positive integer',
      valueCreated: 'Value created',
      valueUpdated: 'Value updated',
      dimensionDeleted: 'Dimension deleted',
      deleteFailed: 'Delete failed',
      noPermission: 'You do not have permission to view tags',
      title: 'Tags',
      description: 'Manage tag dimensions and values',
      newDimension: 'New Dimension',
      nameCol: 'Name',
      statusCol: 'Status',
      tagValuesCol: 'Tag Values',
      noDimensions: 'No dimensions configured',
      enabled: 'Enabled',
      disabled: 'Disabled',
      edit: 'Edit',
      resourceWhitelist: 'Resource Whitelist',
      resourceWhitelistDesc: 'Configure which resources can use tags',
      deactivateFailed: 'Deactivate failed',
      activateFailed: 'Activate failed',
      confirmDeleteTitle: 'Confirm Delete',
      confirmDeleteDesc: 'Are you sure you want to delete dimension "{{name}}"?',
      irreversible: 'This action cannot be undone',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    tagsTab: {
      dimensionCreated: '维度已创建',
      dimensionUpdated: '维度已更新',
      levelMustBePositive: '等级必须是正整数',
      valueCreated: '值已创建',
      valueUpdated: '值已更新',
      dimensionDeleted: '维度已删除',
      deleteFailed: '删除失败',
      noPermission: '您没有查看标签的权限',
      title: '标签',
      description: '管理标签维度和值',
      newDimension: '新建维度',
      nameCol: '名称',
      statusCol: '状态',
      tagValuesCol: '标签值',
      noDimensions: '暂无维度配置',
      enabled: '已启用',
      disabled: '已禁用',
      edit: '编辑',
      resourceWhitelist: '资源白名单',
      resourceWhitelistDesc: '配置哪些资源可以使用标签',
      deactivateFailed: '停用失败',
      activateFailed: '启用失败',
      confirmDeleteTitle: '确认删除',
      confirmDeleteDesc: '确定要删除维度"{{name}}"吗？',
      irreversible: '此操作不可撤销',
    }
  }
}, true, true)

import ResourceWhitelistConfigSection from '@/components/ResourceWhitelistConfigSection'
import SettingsSection from '@/components/SettingsSection'
import TagKeyEditorDialog from '@/components/TagKeyEditorDialog'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/hooks/useAuth'
import { useConfirmation } from '@/hooks/useConfirmation'
import { useNotification } from '@/hooks/useNotification'
import { useTags } from '@/hooks/useTags'
import type { ResourceType, TagKeyDTO, TagValueDTO } from '@/lib/tagsApi'
import { actionRules } from '@/lib/permissionRules'

const RESOURCE_TYPES: ResourceType[] = ['user', 'document_collection', 'data_source', 'api_connector']
const DEFAULT_TAG_COLOR = '#2563eb'

export default function SettingsTagsTab() {
  const { t } = useTranslation()
  const {
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
  } = useTags()

  const { hasAny } = useAuth()
  const { showError, showSuccess } = useNotification()

  const canRead = hasAny(actionRules.canReadTags())
  const canManage = hasAny(actionRules.canManageTags())

  const [createKeyOpen, setCreateKeyOpen] = useState(false)
  const [editKey, setEditKey] = useState<TagKeyDTO | null>(null)
  const [keyForm, setKeyForm] = useState({
    name: '',
    description: '',
    color: DEFAULT_TAG_COLOR,
  })

  const [newValueText, setNewValueText] = useState('')
  const [newValueRankText, setNewValueRankText] = useState('')
  const [editingValueId, setEditingValueId] = useState<number | null>(null)
  const [editingValueText, setEditingValueText] = useState('')
  const [editingValueRankText, setEditingValueRankText] = useState('')
  const deleteKeyConfirm = useConfirmation<TagKeyDTO | null>(null)

  useEffect(() => {
    if (!canRead) return
    fetchTagKeys().catch(() => undefined)
    fetchTagValues().catch(() => undefined)
    fetchResourceTagConfigs().catch(() => undefined)
  }, [canRead, fetchResourceTagConfigs, fetchTagKeys, fetchTagValues])

  const tagValuesByKey = useMemo(() => {
    const map = new Map<number, TagValueDTO[]>()
    tagValues.forEach((value) => {
      const items = map.get(value.key_id) || []
      items.push(value)
      map.set(value.key_id, items)
    })
    return map
  }, [tagValues])

  const resetKeyForm = () => {
    setKeyForm({
      name: '',
      description: '',
      color: DEFAULT_TAG_COLOR,
    })
  }

  const handleCreateKey = async () => {
    try {
      await createKey({
        name: keyForm.name.trim(),
        description: keyForm.description.trim() || null,
        color: keyForm.color,
      })
      showSuccess(t('settings.tagsTab.dimensionCreated'))
      setCreateKeyOpen(false)
      resetKeyForm()
    } catch (error: any) {
      showError(error.response?.data?.detail || t('settings.tagsTab.dimensionCreated'))
    }
  }

  const handleUpdateKey = async () => {
    if (!editKey) return
    try {
      await updateKey(editKey.id, {
        name: keyForm.name.trim(),
        description: keyForm.description.trim() || null,
        color: keyForm.color,
      })
      showSuccess(t('settings.tagsTab.dimensionUpdated'))
      setEditKey(null)
      resetKeyForm()
    } catch (error: any) {
      showError(error.response?.data?.detail || t('settings.tagsTab.dimensionUpdated'))
    }
  }

  const handleAddTagValue = async (keyId: number) => {
    if (!newValueText.trim()) return
    const trimmedRank = newValueRankText.trim()
    let parsedRank: number | null = null
    if (trimmedRank) {
      parsedRank = Number(trimmedRank)
      if (!Number.isInteger(parsedRank) || parsedRank <= 0) {
        showError(t('settings.tagsTab.levelMustBePositive'))
        return
      }
    }
    try {
      await createValue({
        key_id: keyId,
        value: newValueText.trim(),
        rank: parsedRank,
      })
      showSuccess(t('settings.tagsTab.valueCreated'))
      setNewValueText('')
      setNewValueRankText('')
    } catch (error: any) {
      showError(error.response?.data?.detail || t('settings.tagsTab.valueCreated'))
    }
  }

  const handleSaveTagValue = async () => {
    if (!editingValueId || !editingValueText.trim()) return
    const trimmedRank = editingValueRankText.trim()
    let parsedRank: number | null = null
    if (trimmedRank) {
      parsedRank = Number(trimmedRank)
      if (!Number.isInteger(parsedRank) || parsedRank <= 0) {
        showError(t('settings.tagsTab.levelMustBePositive'))
        return
      }
    }
    try {
      await updateValue(editingValueId, {
        value: editingValueText.trim(),
        rank: parsedRank,
      })
      showSuccess(t('settings.tagsTab.valueUpdated'))
      setEditingValueId(null)
      setEditingValueText('')
      setEditingValueRankText('')
    } catch (error: any) {
      showError(error.response?.data?.detail || t('settings.tagsTab.valueUpdated'))
    }
  }

  const handleToggleTagKeyStatus = (key: TagKeyDTO, nextActive: boolean) => {
    const action = nextActive ? enableKey : disableKey
    action(key.id).catch((err) => showError(err.response?.data?.detail || t('settings.tagsTab.dimensionUpdated')))
  }

  const handleDeleteTagKeyClick = (key: TagKeyDTO) => {
    deleteKeyConfirm.open(key)
  }

  const handleDeleteTagKeyConfirm = (key: TagKeyDTO | null) => {
    if (!key) return
    deleteKeyConfirm.setLoading(true)
    removeKey(key.id)
      .then(() => showSuccess(t('settings.tagsTab.dimensionDeleted')))
      .catch((err) => showError(err.response?.data?.detail || t('settings.tagsTab.deleteFailed')))
      .finally(() => {
        deleteKeyConfirm.setLoading(false)
        deleteKeyConfirm.close()
      })
  }

  return (
    <div className="space-y-6">
      {!canRead && (
        <Alert variant="destructive">
          <AlertDescription>{t('settings.tagsTab.noPermission')}</AlertDescription>
        </Alert>
      )}

      {canRead && error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <SettingsSection
        title={t('settings.tagsTab.title')}
        description={t('settings.tagsTab.description')}
        action={
          <Button onClick={() => setCreateKeyOpen(true)} disabled={!canManage || loading}>
            {t('settings.tagsTab.newDimension')}
          </Button>
        }
        contentClassName="p-0"
      >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('settings.tagsTab.nameCol')}</TableHead>
                <TableHead>{t('settings.tagsTab.statusCol')}</TableHead>
                <TableHead>{t('settings.tagsTab.tagValuesCol')}</TableHead>
                <TableHead className="text-right">{t('common.operation')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tagKeys.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4}                     className="py-8 text-center text-sm text-muted-foreground">
                    {t('settings.tagsTab.noDimensions')}
                  </TableCell>
                </TableRow>
              ) : (
                tagKeys.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 rounded-full border"
                          style={{ backgroundColor: key.color || DEFAULT_TAG_COLOR }}
                        />
                        <span>{key.name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={key.status === 'active'}
                          onCheckedChange={(checked) => handleToggleTagKeyStatus(key, checked)}
                          disabled={!canManage || loading}
                          aria-label={`${t('settings.tagsTab.statusCol')} ${key.name}`}
                        />
                        <span className="text-sm text-muted-foreground">
                          {key.status === 'active' ? t('settings.tagsTab.enabled') : t('settings.tagsTab.disabled')}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {(tagValuesByKey.get(key.id) || [])
                        .slice(0, 4)
                        .map((value) => value.value)
                        .join(', ') || '—'}
                      {(tagValuesByKey.get(key.id) || []).length > 4 && '…'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditKey(key)
                            setKeyForm({
                              name: key.name,
                              description: key.description || '',
                              color: key.color || DEFAULT_TAG_COLOR,
                            })
                          }}
                          disabled={!canManage}
                        >
                           {t('settings.tagsTab.edit')}
                          </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDeleteTagKeyClick(key)}
                          disabled={!canManage}
                        >
                          {t('common.delete')}
                         </Button>
                       </div>
                     </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
      </SettingsSection>

      <SettingsSection
        title={t('settings.tagsTab.resourceWhitelist')}
        description={t('settings.tagsTab.resourceWhitelistDesc')}
        contentClassName="p-0"
      >
        <ResourceWhitelistConfigSection
          resourceTypes={RESOURCE_TYPES}
          tagKeys={tagKeys}
          resourceTagConfigs={resourceTagConfigs}
          canManage={canManage}
          loading={loading}
          defaultTagColor={DEFAULT_TAG_COLOR}
          onCreateConfig={createConfig}
          onUpdateConfig={updateConfig}
          onRemoveConfig={removeConfig}
          onFetchResourceTagConfigs={fetchResourceTagConfigs}
          onError={(message) => showError(message)}
          onSuccess={(message) => showSuccess(message)}
        />
      </SettingsSection>

      <TagKeyEditorDialog
        open={createKeyOpen || !!editKey}
        onOpenChange={(open) => {
          if (!open) {
            setCreateKeyOpen(false)
            setEditKey(null)
            resetKeyForm()
            setNewValueText('')
            setNewValueRankText('')
            setEditingValueId(null)
            setEditingValueText('')
            setEditingValueRankText('')
          }
        }}
        editKey={editKey}
        keyForm={keyForm}
        onKeyFormChange={setKeyForm}
        canManage={canManage}
        loading={loading}
        onSaveKey={editKey ? handleUpdateKey : handleCreateKey}
        onCancel={() => {
          setCreateKeyOpen(false)
          setEditKey(null)
          resetKeyForm()
          setNewValueText('')
          setNewValueRankText('')
          setEditingValueId(null)
          setEditingValueText('')
          setEditingValueRankText('')
        }}
        tagValues={editKey ? tagValuesByKey.get(editKey.id) || [] : []}
        editingValueId={editingValueId}
        editingValueText={editingValueText}
        editingValueRankText={editingValueRankText}
        onEditingValueIdChange={setEditingValueId}
        onEditingValueTextChange={setEditingValueText}
        onEditingValueRankTextChange={setEditingValueRankText}
        onSaveTagValue={handleSaveTagValue}
        onDisableTagValue={(tagValueId) =>
          disableValue(tagValueId).catch((err) =>
            showError(err.response?.data?.detail || t('settings.tagsTab.deactivateFailed'))
          )
        }
        onEnableTagValue={(tagValueId) =>
          enableValue(tagValueId).catch((err) =>
            showError(err.response?.data?.detail || t('settings.tagsTab.activateFailed'))
          )
        }
        onDeleteTagValue={(tagValueId) =>
          removeValue(tagValueId).catch((err) =>
            showError(err.response?.data?.detail || t('settings.tagsTab.deleteFailed'))
          )
        }
        onEditTagValue={(value) => {
          setEditingValueId(value.id)
          setEditingValueText(value.value)
          setEditingValueRankText(value.rank != null ? String(value.rank) : '')
        }}
        newValueText={newValueText}
        newValueRankText={newValueRankText}
        onNewValueTextChange={setNewValueText}
        onNewValueRankTextChange={setNewValueRankText}
        onAddTagValue={handleAddTagValue}
        onError={(message) => showError(message)}
      />

      <ConfirmationDialog<TagKeyDTO | null>
        open={deleteKeyConfirm.isOpen}
        item={deleteKeyConfirm.item}
        isLoading={deleteKeyConfirm.isLoading}
        title={t('settings.tagsTab.confirmDeleteTitle')}
        description={(key) => (
          <>
            {t('settings.tagsTab.confirmDeleteDesc', { name: key?.name })}
            <br />
            <span className="text-red-600">{t('settings.tagsTab.irreversible')}</span>
          </>
        )}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={handleDeleteTagKeyConfirm}
        onCancel={deleteKeyConfirm.close}
      />
    </div>
  )
}
