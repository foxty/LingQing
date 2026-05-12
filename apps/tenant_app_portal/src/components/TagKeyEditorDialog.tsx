import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Badge } from '@/components/ui/badge'

i18n.addResourceBundle('en', 'translation', {
  components: {
    tagKeyEditor: {
      createTitle: 'Create Tag Key',
      editTitle: 'Edit Tag Key',
      description: 'Manage tag key and its values',
      name: 'Name',
      descriptionField: 'Description',
      tagColor: 'Color',
      selectColor: 'Select a color',
      tagValues: 'Tag Values',
      noTagValues: 'No tag values yet',
      addValuePlaceholder: 'New value...',
      levelPlaceholder: 'Level (optional)',
      enabled: 'Enabled',
      disabled: 'Disabled',
      save: 'Save',
      cancel: 'Cancel',
      edit: 'Edit',
      create: 'Create',
      add: 'Add',
      deactivate: 'Deactivate',
      activate: 'Activate',
      delete: 'Delete',
      noValuesHint: 'Save the tag key first, then add values',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    tagKeyEditor: {
      createTitle: '创建标签键',
      editTitle: '编辑标签键',
      description: '管理标签键及其值',
      name: '名称',
      descriptionField: '描述',
      tagColor: '颜色',
      selectColor: '选择颜色',
      tagValues: '标签值',
      noTagValues: '暂无标签值',
      addValuePlaceholder: '新值...',
      levelPlaceholder: '级别（可选）',
      enabled: '已启用',
      disabled: '已禁用',
      save: '保存',
      cancel: '取消',
      edit: '编辑',
      create: '创建',
      add: '添加',
      deactivate: '停用',
      activate: '启用',
      delete: '删除',
      noValuesHint: '先保存标签键，然后添加值',
    },
  },
}, true, true)
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { TagKeyDTO, TagValueDTO } from '@/lib/tagsApi'

interface TagKeyEditorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editKey: TagKeyDTO | null
  keyForm: {
    name: string
    description: string
    color: string
  }
  onKeyFormChange: (next: TagKeyEditorDialogProps['keyForm']) => void
  canManage: boolean
  loading: boolean
  onSaveKey: () => void
  onCancel: () => void
  tagValues: TagValueDTO[]
  editingValueId: number | null
  editingValueText: string
  editingValueRankText: string
  onEditingValueIdChange: (value: number | null) => void
  onEditingValueTextChange: (value: string) => void
  onEditingValueRankTextChange: (value: string) => void
  onSaveTagValue: () => void
  onDisableTagValue: (tagValueId: number) => void
  onEnableTagValue: (tagValueId: number) => void
  onDeleteTagValue: (tagValueId: number) => void
  onEditTagValue: (tagValue: TagValueDTO) => void
  newValueText: string
  newValueRankText: string
  onNewValueTextChange: (value: string) => void
  onNewValueRankTextChange: (value: string) => void
  onAddTagValue: (keyId: number) => void
  onError: (message: string) => void
}

export default function TagKeyEditorDialog({
  open,
  onOpenChange,
  editKey,
  keyForm,
  onKeyFormChange,
  canManage,
  loading,
  onSaveKey,
  onCancel,
  tagValues,
  editingValueId,
  editingValueText,
  editingValueRankText,
  onEditingValueIdChange,
  onEditingValueTextChange,
  onEditingValueRankTextChange,
  onSaveTagValue,
  onDisableTagValue,
  onEnableTagValue,
  onDeleteTagValue,
  onEditTagValue,
  newValueText,
  newValueRankText,
  onNewValueTextChange,
  onNewValueRankTextChange,
  onAddTagValue,
}: TagKeyEditorDialogProps) {
  const { t } = useTranslation()
  const isEditing = !!editKey
  const colorOptions = [
    { label: t('components.tagKeyEditor.tagColor'), value: '#2563eb' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#dc2626' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#059669' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#7c3aed' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#d97706' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#0f766e' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#db2777' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#4f46e5' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#374151' },
    { label: t('components.tagKeyEditor.tagColor'), value: '#b45309' },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[80vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isEditing ? t('components.tagKeyEditor.editTitle') : t('components.tagKeyEditor.createTitle')}</DialogTitle>
          <DialogDescription>{t('components.tagKeyEditor.description')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 overflow-y-auto pr-2 h-full">
          <div className="space-y-2">
            <Label htmlFor="tag-key-name">{t('components.tagKeyEditor.name')}</Label>
            <Input
              id="tag-key-name"
              value={keyForm.name}
              onChange={(event) => onKeyFormChange({ ...keyForm, name: event.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tag-key-desc">{t('components.tagKeyEditor.descriptionField')}</Label>
            <Textarea
              id="tag-key-desc"
              value={keyForm.description}
              onChange={(event) => onKeyFormChange({ ...keyForm, description: event.target.value })}
              rows={3}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tag-key-color">{t('components.tagKeyEditor.tagColor')}</Label>
            <Select
              value={keyForm.color}
              onValueChange={(value) =>
                onKeyFormChange({
                  ...keyForm,
                  color: value,
                })
              }
            >
              <SelectTrigger id="tag-key-color">
                <SelectValue placeholder={t('components.tagKeyEditor.selectColor')} />
              </SelectTrigger>
              <SelectContent>
                {colorOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full border"
                        style={{ backgroundColor: option.value }}
                      />
                      <span>{option.label}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isEditing ? (
            <div className="space-y-3">
              <div className="text-sm font-semibold">{t('components.tagKeyEditor.tagValues')}</div>
              {tagValues.length === 0 ? (
                <div className="text-sm text-muted-foreground">{t('components.tagKeyEditor.noTagValues')}</div>
              ) : (
                <div className="space-y-2">
                  {tagValues.map((value) => (
                    <div key={value.id} className="flex items-center justify-between gap-2">
                      <div className="flex-1">
                        {editingValueId === value.id ? (
                          <div className="grid grid-cols-2 gap-2">
                            <Input
                              value={editingValueText}
                              onChange={(event) => onEditingValueTextChange(event.target.value)}
                            />
                            <Input
                              type="number"
                              min={1}
                              value={editingValueRankText}
                              onChange={(event) => onEditingValueRankTextChange(event.target.value)}
                              placeholder={t('components.tagKeyEditor.levelPlaceholder')}
                            />
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="text-sm">{value.value}</span>
                            {value.rank != null && <Badge variant="outline">R{value.rank}</Badge>}
                            <Badge variant={value.status === 'active' ? 'secondary' : 'outline'}>
                              {value.status === 'active' ? t('components.tagKeyEditor.enabled') : t('components.tagKeyEditor.disabled')}
                            </Badge>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {editingValueId === value.id ? (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={onSaveTagValue}
                              disabled={!canManage}
                            >
                              {t('components.tagKeyEditor.save')}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => {
                                onEditingValueIdChange(null)
                                onEditingValueTextChange('')
                                onEditingValueRankTextChange('')
                              }}
                            >
                              {t('components.tagKeyEditor.cancel')}
                            </Button>
                          </>
                        ) : (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => onEditTagValue(value)}
                              disabled={!canManage}
                            >
                             {t('components.tagKeyEditor.edit')}
                            </Button>
                            {value.status === 'active' && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => onDisableTagValue(value.id)}
                                disabled={!canManage}
                              >
                                {t('components.tagKeyEditor.deactivate')}
                              </Button>
                            )}
                            {value.status === 'disabled' && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => onEnableTagValue(value.id)}
                                disabled={!canManage}
                              >
                                {t('components.tagKeyEditor.activate')}
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => onDeleteTagValue(value.id)}
                              disabled={!canManage}
                            >
                              {t('components.tagKeyEditor.delete')}
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-3 gap-2">
                <Input
                  value={newValueText}
                  onChange={(event) => onNewValueTextChange(event.target.value)}
                  placeholder={t('components.tagKeyEditor.addValuePlaceholder')}
                />
                <Input
                  type="number"
                  min={1}
                  value={newValueRankText}
                  onChange={(event) => onNewValueRankTextChange(event.target.value)}
                  placeholder={t('components.tagKeyEditor.levelPlaceholder')}
                />
                <Button
                  variant="outline"
                  onClick={() => editKey && onAddTagValue(editKey.id)}
                  disabled={!newValueText.trim() || !canManage}
                >
                  {t('components.tagKeyEditor.add')}
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">{t('components.tagKeyEditor.noValuesHint')}</div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            {t('components.tagKeyEditor.cancel')}
          </Button>
          <Button onClick={onSaveKey} disabled={!keyForm.name.trim() || loading || !canManage}>
            {isEditing ? t('components.tagKeyEditor.save') : t('components.tagKeyEditor.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
