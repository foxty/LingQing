import TagBindingsDialog from '@/components/TagBindingsDialog'
import { connectionActionLabelKey } from '@/components/IntegrationCredentialsCell'
import type { UserConnectionStatus } from '@/components/IntegrationCredentialsCell'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { ResourceType, TagValueDTO } from '@/lib/tagsApi'
import {
  KeyRound,
  Link2,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Share2,
  Tag,
  Trash2,
} from 'lucide-react'
import { useState, type MouseEvent } from 'react'
import { useTranslation } from 'react-i18next'

export interface ContainerRowActionsProps {
  connection?: {
    label: string
    status?: UserConnectionStatus | null
    onClick: (e: MouseEvent) => void
    hidden?: boolean
  }
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
  connection,
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
  const [tagsOpen, setTagsOpen] = useState(false)

  const showConnection = Boolean(connection && !connection.hidden)
  const showShare = Boolean(onShare)
  const showTags = Boolean(tags?.canRead)
  const showEdit = Boolean(onEdit && !editHidden)
  const showDelete = Boolean(onDelete && !deleteHidden)

  if (!showConnection && !showShare && !showTags && !showEdit && !showDelete) {
    return null
  }

  const connectionActionKey = connection?.status
    ? connectionActionLabelKey(connection.status)
    : 'actionConnect'

  const ConnectionIcon =
    connectionActionKey === 'actionManage'
      ? KeyRound
      : connectionActionKey === 'actionReconnect'
        ? RefreshCw
        : Link2

  const connectionItemClass =
    connectionActionKey === 'actionManage'
      ? 'text-success focus:text-success'
      : connectionActionKey === 'actionReconnect'
        ? 'text-destructive focus:text-destructive'
        : 'text-primary focus:text-primary'

  return (
    <>
      <div className="flex items-center justify-end" onClick={(e) => e.stopPropagation()}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 w-8 p-0"
              aria-label={t('common.action')}
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[11rem]">
            {showConnection && connection ? (
              <DropdownMenuItem
                className={connectionItemClass}
                onClick={(e) => {
                  e.stopPropagation()
                  connection.onClick(e)
                }}
              >
                <ConnectionIcon className="mr-2 h-4 w-4" />
                {connection.label}
              </DropdownMenuItem>
            ) : null}
            {showConnection && (showShare || showTags || showEdit) ? <DropdownMenuSeparator /> : null}
            {showShare ? (
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onShare?.()
                }}
              >
                <Share2 className="mr-2 h-4 w-4" />
                {shareTitle ?? t('common.share')}
              </DropdownMenuItem>
            ) : null}
            {showTags && tags ? (
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  setTagsOpen(true)
                }}
              >
                <Tag className="mr-2 h-4 w-4" />
                {tagsTitle ?? 'Manage tags'}
              </DropdownMenuItem>
            ) : null}
            {showEdit ? (
              <DropdownMenuItem
                disabled={editDisabled}
                onClick={(e) => {
                  e.stopPropagation()
                  if (!editDisabled) {
                    onEdit?.()
                  }
                }}
              >
                <Pencil className="mr-2 h-4 w-4" />
                {editTitle ?? t('common.edit')}
              </DropdownMenuItem>
            ) : null}
            {showDelete ? (
              <>
                {showConnection || showShare || showTags || showEdit ? <DropdownMenuSeparator /> : null}
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  disabled={deleteDisabled}
                  onClick={(e) => {
                    e.stopPropagation()
                    if (!deleteDisabled) {
                      onDelete?.()
                    }
                  }}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {deleteTitle ?? t('common.delete')}
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {showTags && tags ? (
        <TagBindingsDialog
          resourceType={tags.resourceType}
          resourceId={tags.resourceId}
          title={tags.resourceTitle}
          canManage={tags.canManage}
          canRead={tags.canRead}
          onTagsUpdated={tags.onTagsUpdated}
          open={tagsOpen}
          onOpenChange={setTagsOpen}
        />
      ) : null}
    </>
  )
}
