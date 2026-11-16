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
import {
  buildCollectionFormSchema,
  DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH,
  DOCUMENT_COLLECTION_NAME_MAX_LENGTH,
} from '@/lib/collectionFormSchema'
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo } from 'react'
import { useForm } from 'react-hook-form'
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
      nameTooLong: 'Name must be at most {{max}} characters',
      descriptionTooLong: 'Description must be at most {{max}} characters',
      charCount: '{{count}} / {{max}}',
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
      nameTooLong: '名称最多 {{max}} 个字符',
      descriptionTooLong: '描述最多 {{max}} 个字符',
      charCount: '{{count}} / {{max}}',
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

  const schema = useMemo(
    () =>
      buildCollectionFormSchema({
        nameRequired: t('components.collectionFormDialog.nameRequired'),
        nameTooLong: t('components.collectionFormDialog.nameTooLong', {
          max: DOCUMENT_COLLECTION_NAME_MAX_LENGTH,
        }),
        descriptionTooLong: t('components.collectionFormDialog.descriptionTooLong', {
          max: DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH,
        }),
      }),
    [t]
  )

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<CollectionFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', description: '' },
  })

  const nameValue = watch('name') ?? ''
  const descriptionValue = watch('description') ?? ''

  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && collection) {
      reset({
        name: collection.name,
        description: collection.description ?? '',
      })
    } else {
      reset({ name: '', description: '' })
    }
  }, [open, mode, collection, reset])

  const isCreate = mode === 'create'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit((values) => onSubmit(values))}>
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
                {...register('name')}
                placeholder={t('components.collectionFormDialog.namePlaceholder')}
                maxLength={DOCUMENT_COLLECTION_NAME_MAX_LENGTH}
                autoFocus
              />
              <p className="text-xs text-muted-foreground text-right tabular-nums">
                {t('components.collectionFormDialog.charCount', {
                  count: nameValue.length,
                  max: DOCUMENT_COLLECTION_NAME_MAX_LENGTH,
                })}
              </p>
              {errors.name?.message && (
                <p className="text-sm text-destructive">{errors.name.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="collection-description">
                {t('components.collectionFormDialog.description')}
              </Label>
              <Textarea
                id="collection-description"
                {...register('description')}
                placeholder={t('components.collectionFormDialog.descriptionPlaceholder')}
                maxLength={DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH}
                rows={3}
              />
              <p className="text-xs text-muted-foreground text-right tabular-nums">
                {t('components.collectionFormDialog.charCount', {
                  count: descriptionValue.length,
                  max: DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH,
                })}
              </p>
              {errors.description?.message && (
                <p className="text-sm text-destructive">{errors.description.message}</p>
              )}
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