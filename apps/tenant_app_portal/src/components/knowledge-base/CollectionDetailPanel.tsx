import { DocumentTable } from '@/components/DocumentTable'
import EmptyState from '@/components/EmptyState'
import CollectionHeader from '@/components/knowledge-base/CollectionHeader'
import DocumentListToolbar from '@/components/knowledge-base/DocumentListToolbar'
import { Button } from '@/components/ui/button'
import { UploadProgressNotifications } from '@/components/UploadProgressNotifications'
import { ACCEPT_FILE_TYPES } from '@/constants/documents'
import type { KnowledgeBaseDocumentsData } from '@/hooks/useKnowledgeBasePage'
import type { UploadProgress } from '@/hooks/useFileUpload'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import { Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface CollectionDetailPanelProps {
  collection: DocumentCollection
  data: KnowledgeBaseDocumentsData
  isLoading: boolean
  normalizedQuery?: string
  searchQuery: string
  selectedIds: Set<number>
  canUpload: boolean
  canDelete: boolean
  canReadTags: boolean
  uploading: boolean
  uploadProgress: UploadProgress[]
  onSearchQueryChange: (value: string) => void
  onClearSearchQuery: () => void
  onSelectionChange: (ids: Set<number>) => void
  onPageChange: (page: number) => void
  onBatchDelete: () => void
  onUpload: () => void
  onShare: () => void
  onTags: () => void
  onEdit: () => void
  onDelete: () => void
  onReparseAll: () => void
  onReindexAll: () => void
  queuePending?: boolean
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
  canReadTags,
  uploading,
  uploadProgress,
  onSearchQueryChange,
  onClearSearchQuery,
  onSelectionChange,
  onPageChange,
  onBatchDelete,
  onUpload,
  onShare,
  onTags,
  onEdit,
  onDelete,
  onReparseAll,
  onReindexAll,
  queuePending = false,
  onFileUpload,
}: CollectionDetailPanelProps) {
  const { t } = useTranslation()

  const showEmptyCollection =
    !isLoading &&
    !normalizedQuery &&
    (data?.total ?? 0) === 0 &&
    collection.document_count === 0

  return (
    <div className="space-y-4 min-w-0">
      <CollectionHeader
        collection={collection}
        canUpload={canUpload}
        canDelete={canDelete}
        canReadTags={canReadTags}
        uploading={uploading}
        selectedCount={selectedIds.size}
        onUpload={onUpload}
        onShare={onShare}
        onTags={onTags}
        onEdit={onEdit}
        onDelete={onDelete}
        onBatchDelete={onBatchDelete}
        onReparseAll={onReparseAll}
        onReindexAll={onReindexAll}
        queuePending={queuePending}
      />

      <input
        id="file-upload"
        type="file"
        className="hidden"
        multiple
        accept={ACCEPT_FILE_TYPES}
        onChange={onFileUpload}
        disabled={uploading}
      />

      <DocumentListToolbar
        searchQuery={searchQuery}
        onSearchQueryChange={onSearchQueryChange}
        onClearSearchQuery={onClearSearchQuery}
      />

      <UploadProgressNotifications items={uploadProgress} />

      {showEmptyCollection ? (
        <EmptyState
          title={t('knowledgeBase.noDocuments')}
          description={t('knowledgeBase.emptyCollectionDesc')}
          action={
            canUpload ? (
              <Button onClick={onUpload} disabled={uploading}>
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
