import TagBindingsDialog from '@/components/TagBindingsDialog'
import { Button } from '@/components/ui/button'
import type { ResourceType, TagValueDTO } from '@/lib/tagsApi'
import { Pencil, Share2, Tag, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface ContainerRowActionsProps {
  onShare?: () => void
  shareTitle?: string
  tags?: {
    resourceType: ResourceType
    resourceId: number
    resourceTitle: string
    canRead: boolean
    canManage: boolean
    onTagsUpdated?: (resourceId: number, tags: TagValueDTO[]) => void
  }
  tagsTitle?: string
  onEdit?: () => void
  editDisabled?: boolean
  editHidden?: boolean
  editTitle?: string
  onDelete?: () => void
  deleteDisabled?: boolean
  deleteHidden?: boolean
  deleteTitle?: string
}

export default function ContainerRowActions({
  onShare,
  shareTitle,
  tags,
  tagsTitle,
  onEdit,
  editDisabled,
  editHidden,
  editTitle,
  onDelete,
  deleteDisabled,
  deleteHidden,
  deleteTitle,
}: ContainerRowActionsProps) {
  const { t } = useTranslation()

  return (
    <div className="flex items-center justify-end gap-1">
      {onShare ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={onShare}
          title={shareTitle ?? t('common.share')}
          className="h-8 w-8 p-0"
        >
          <Share2 className="w-4 h-4" />
        </Button>
      ) : null}
      {tags?.canRead ? (
        <TagBindingsDialog
          resourceType={tags.resourceType}
          resourceId={tags.resourceId}
          title={tags.resourceTitle}
          canManage={tags.canManage}
          canRead={tags.canRead}
          onTagsUpdated={tags.onTagsUpdated}
        >
          <Button
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0"
            title={tagsTitle ?? 'Manage tags'}
          >
            <Tag className="w-4 h-4" />
          </Button>
        </TagBindingsDialog>
      ) : null}
      {onEdit && !editHidden ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={onEdit}
          disabled={editDisabled}
          title={editTitle ?? t('common.edit')}
          className={`h-8 w-8 p-0 ${editDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <Pencil className={`w-4 h-4 ${editDisabled ? 'text-muted-foreground' : ''}`} />
        </Button>
      ) : null}
      {onDelete && !deleteHidden ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={onDelete}
          disabled={deleteDisabled}
          title={deleteTitle ?? t('common.delete')}
          className={`h-8 w-8 p-0 ${deleteDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <Trash2
            className={`w-4 h-4 ${deleteDisabled ? 'text-muted-foreground' : 'text-destructive'}`}
          />
        </Button>
      ) : null}
    </div>
  )
}
