import i18n from '@/i18n/config'
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
import { Textarea } from '@/components/ui/textarea'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle('en', 'translation', {
  components: {
    collectionFormDialog: {
      createTitle: 'New Collection',
      editTitle: 'Rename Collection',
      createDescription: 'Organize documents into a collection for access control and retrieval.',
      editDescription: 'Update the collection name or description.',
      name: 'Name',
      namePlaceholder: 'Engineering',
      description: 'Description',
      descriptionPlaceholder: 'Optional description',
      nameRequired: 'Collection name is required',
      cancel: 'Cancel',
      create: 'Create',
      save: 'Save',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    collectionFormDialog: {
      createTitle: '新建集合',
      editTitle: '编辑集合',
      createDescription: '将文档组织到集合中，便于权限管理与检索。',
      editDescription: '更新集合名称或描述。',
      name: '名称',
      namePlaceholder: '工程文档',
      description: '描述',
      descriptionPlaceholder: '可选描述',
      nameRequired: '请输入集合名称',
      cancel: '取消',
      create: '创建',
      save: '保存',
    },
  },
}, true, true)

export interface CollectionFormValues {
  name: string
  description: string
}

interface CollectionFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'create' | 'edit'
  collection?: DocumentCollection | null
  isSubmitting?: boolean
  onSubmit: (values: CollectionFormValues) => void | Promise<void>
}

export default function CollectionFormDialog({
  open,
  onOpenChange,
  mode,
  collection,
  isSubmitting = false,
  onSubmit,
}: CollectionFormDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [nameError, setNameError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && collection) {
      setName(collection.name)
      setDescription(collection.description ?? '')
    } else {
      setName('')
      setDescription('')
    }
    setNameError(null)
  }, [open, mode, collection])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    const trimmedName = name.trim()
    if (!trimmedName) {
      setNameError(t('components.collectionFormDialog.nameRequired'))
      return
    }
    setNameError(null)
    await onSubmit({ name: trimmedName, description: description.trim() })
  }

  const isCreate = mode === 'create'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {isCreate
                ? t('components.collectionFormDialog.createTitle')
                : t('components.collectionFormDialog.editTitle')}
            </DialogTitle>
            <DialogDescription>
              {isCreate
                ? t('components.collectionFormDialog.createDescription')
                : t('components.collectionFormDialog.editDescription')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="collection-name">{t('components.collectionFormDialog.name')}</Label>
              <Input
                id="collection-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('components.collectionFormDialog.namePlaceholder')}
                autoFocus
              />
              {nameError && <p className="text-sm text-destructive">{nameError}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="collection-description">
                {t('components.collectionFormDialog.description')}
              </Label>
              <Textarea
                id="collection-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('components.collectionFormDialog.descriptionPlaceholder')}
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('components.collectionFormDialog.cancel')}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isCreate
                ? t('components.collectionFormDialog.create')
                : t('components.collectionFormDialog.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
