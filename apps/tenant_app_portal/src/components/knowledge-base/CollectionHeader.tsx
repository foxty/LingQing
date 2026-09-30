import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { Database, MoreHorizontal, Pencil, RefreshCw, Share2, Tag, Trash2, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface CollectionHeaderProps {
  collection: DocumentCollection
  canUpload: boolean
  canDelete: boolean
  canWriteCollection: boolean
  canReadTags: boolean
  uploading: boolean
  selectedCount: number
  onUpload: () => void
  onShare: () => void
  onTags: () => void
  onEdit: () => void
  onDelete: () => void
  onBatchDelete?: () => void
  onReparseAll?: () => void
  onReindexAll?: () => void
  queuePending?: boolean
}

export default function CollectionHeader({
  collection,
  canUpload,
  canDelete,
  canWriteCollection,
  canReadTags,
  uploading,
  selectedCount,
  onUpload,
  onShare,
  onTags,
  onEdit,
  onDelete,
  onBatchDelete,
  onReparseAll,
  onReindexAll,
  queuePending = false,
}: CollectionHeaderProps) {
  const { t } = useTranslation()

  const hasMenuItems =
    canWriteCollection ||
    canReadTags ||
    (canDelete && selectedCount > 0 && onBatchDelete != null)

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1">
        <h2 className="text-lg font-medium truncate">{collection.name}</h2>
        {collection.description && (
          <p className="text-sm text-muted-foreground line-clamp-2">{collection.description}</p>
        )}
        {collection.owner_name && (
          <p className="text-xs text-muted-foreground">
            {t('knowledgeBase.ownerLabel', { name: collection.owner_name })}
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {canUpload && (
          <Button disabled={uploading} onClick={onUpload}>
            <Upload className="w-4 h-4 mr-2" />
            {t('knowledgeBase.uploadDocument')}
          </Button>
        )}
        {hasMenuItems ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="icon" className="h-9 w-9">
              <MoreHorizontal className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {canWriteCollection ? (
              <DropdownMenuItem onClick={onShare}>
                <Share2 className="w-4 h-4 mr-2" />
                {t('knowledgeBase.shareCollection')}
              </DropdownMenuItem>
            ) : null}
            {canReadTags && (
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault()
                  onTags()
                }}
              >
                <Tag className="w-4 h-4 mr-2" />
                {t('knowledgeBase.collectionTags')}
              </DropdownMenuItem>
            )}
            {canWriteCollection && onReparseAll && onReindexAll && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem disabled={queuePending} onClick={onReparseAll}>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  {t('knowledgeBase.queueCollectionReparse')}
                </DropdownMenuItem>
                <DropdownMenuItem disabled={queuePending} onClick={onReindexAll}>
                  <Database className="w-4 h-4 mr-2" />
                  {t('knowledgeBase.queueCollectionReindex')}
                </DropdownMenuItem>
              </>
            )}
            {canDelete && selectedCount > 0 && onBatchDelete && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={onBatchDelete}
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  {t('knowledgeBase.deleteSelected', { count: selectedCount })}
                </DropdownMenuItem>
              </>
            )}
            {canWriteCollection ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onEdit}>
                  <Pencil className="w-4 h-4 mr-2" />
                  {t('knowledgeBase.renameCollection')}
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={onDelete}
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  {t('knowledgeBase.deleteCollection')}
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
        ) : null}
      </div>
    </div>
  )
}
