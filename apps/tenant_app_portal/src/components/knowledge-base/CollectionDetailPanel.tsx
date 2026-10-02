import { DocumentTable } from '@/components/DocumentTable'
import EmptyState from '@/components/EmptyState'
import CollectionSyncPanel from '@/components/knowledge-base/CollectionSyncPanel'
import ListDetailToolbar, { type ListDetailOverflowItem } from '@/components/ListDetailToolbar'
import { Button } from '@/components/ui/button'
import { UploadProgressNotifications } from '@/components/UploadProgressNotifications'
import { ACCEPT_FILE_TYPES } from '@/constants/documents'
import type { CollectionDocumentsData } from '@/hooks/useCollectionDocumentsPage'
import type { UploadProgress } from '@/hooks/useFileUpload'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { useAuth } from '@/hooks/useAuth'
import { actionRules } from '@/lib/permissionRules'
import { Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface CollectionDetailPanelProps {
  collection: DocumentCollection
  data: CollectionDocumentsData
  isLoading: boolean
  normalizedQuery?: string
  searchQuery: string
  selectedIds: Set<number>
  canUpload: boolean
  canDelete: boolean
  canManageCollectionSync: boolean
  uploading: boolean
  onUpload: () => void
  onBatchDelete: () => void
  overflowItems?: ListDetailOverflowItem[]
  uploadProgress: UploadProgress[]
  onSearchQueryChange: (value: string) => void
  onClearSearchQuery: () => void
  onSelectionChange: (ids: Set<number>) => void
  onPageChange: (page: number) => void
  onFileUpload: (event: React.ChangeEvent<HTMLInputElement>) => void
}

export default function CollectionDetailPanel({
  collection,
  data,
  isLoading,
  normalizedQuery,
  searchQuery,
  selectedIds,
  canUpload,
  canDelete,
  canManageCollectionSync,
  uploading,
  uploadProgress,
  onUpload,
  onBatchDelete,
  overflowItems,
  onSearchQueryChange,
  onClearSearchQuery,
  onSelectionChange,
  onPageChange,
  onFileUpload,
}: CollectionDetailPanelProps) {
  const { t } = useTranslation()
  const { hasAny } = useAuth()
  const canReadDocuments = hasAny(actionRules.canReadDocuments())

  const showEmptyCollection =
    !isLoading &&
    !normalizedQuery &&
    (data?.total ?? 0) === 0 &&
    collection.document_count === 0

  return (
    <div className="space-y-4 min-w-0">
      {canReadDocuments ? (
        <CollectionSyncPanel
          collectionId={collection.id}
          documentCount={collection.document_count}
          canManageCollection={canManageCollectionSync}
        />
      ) : null}

      <input
        id="file-upload"
        type="file"
        className="hidden"
        multiple
        accept={ACCEPT_FILE_TYPES}
        onChange={onFileUpload}
        disabled={uploading}
      />

      <ListDetailToolbar
        searchQuery={searchQuery}
        searchPlaceholder={t('knowledgeBase.searchPlaceholder')}
        onSearchQueryChange={onSearchQueryChange}
        onClearSearchQuery={onClearSearchQuery}
        primaryAction={
          canUpload
            ? {
                label: t('knowledgeBase.uploadDocument'),
                onClick: onUpload,
                icon: Upload,
                disabled: uploading,
              }
            : undefined
        }
        batchAction={
          canDelete && selectedIds.size > 0
            ? {
                label: t('knowledgeBase.deleteSelected', { count: selectedIds.size }),
                onClick: onBatchDelete,
              }
            : undefined
        }
        overflowItems={overflowItems}
      />

      <UploadProgressNotifications items={uploadProgress} />

      {showEmptyCollection ? (
        <EmptyState
          title={t('knowledgeBase.noDocuments')}
          description={t('knowledgeBase.emptyCollectionDesc')}
          action={
            canUpload ? (
              <Button variant="outline" onClick={onUpload} disabled={uploading}>
                <Upload className="w-4 h-4 mr-2" />
                {t('knowledgeBase.uploadFirstDocument')}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <DocumentTable
          data={data}
          isLoading={isLoading}
          onPageChange={onPageChange}
          searchQuery={searchQuery}
          selectedIds={selectedIds}
          onSelectionChange={onSelectionChange}
        />
      )}
    </div>
  )
}
