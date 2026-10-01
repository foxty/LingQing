import i18n from '@/i18n/config'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import PaginationBar from '@/components/PaginationBar'
import PipelineStatusBadge from '@/components/PipelineStatusBadge'
import { getIndexPipelineStatus, getParsePipelineStatus } from '@/lib/documentPipelineStatus'
import type { Document } from '@/types'
import type { PaginatedResponse } from '@/lib/documentsApi'

i18n.addResourceBundle('en', 'translation', {
  knowledgeBase: {
    noMatchingDocs: 'No documents match your search',
    noDocuments: 'No documents yet',
    selectAll: 'Select all',
    documentId: 'ID',
    filename: 'Filename',
    documentIdLabel: 'Document #{{id}}',
    uploader: 'Uploader',
    size: 'Size',
    uploadTime: 'Upload Time',
    indexStatus: 'Index Status',
    parseStatus: 'Parse Status',
    statusParsed: 'Parsed',
    statusIndexed: 'Indexed',
    statusQueued: 'Queued',
    statusParsing: 'Parsing',
    statusIndexing: 'Indexing',
    statusPending: 'Pending',
    statusError: 'Error',
    retryParse: 'Retry parse',
    queueReparse: 'Queue re-parse',
    queueReindex: 'Queue re-index',
    reparseQueued: 'Queued for re-parse',
    reindexQueued: 'Queued for re-index',
    processing: 'Processing',
    selectDocument: 'Select {{name}}',
    viewParsed: 'View parsed content',
    confirmDelete: 'Confirm Delete',
    confirmDeleteDesc: 'Are you sure you want to delete "{{name}}"?',
    irreversible: 'This action cannot be undone.',
    sourceDrive: 'Drive',
    sourceUpload: 'Upload',
    sourceColumn: 'Source',
    openInDrive: 'Open in Google Drive',
    driveDeleteWarning:
      'This document is synced from Google Drive. It may reappear after the next sync.',
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  knowledgeBase: {
    noMatchingDocs: '没有匹配的文档',
    noDocuments: '暂无文档',
    selectAll: '全选',
    documentId: 'ID',
    filename: '文件名',
    documentIdLabel: '文档 #{{id}}',
    uploader: '上传者',
    size: '大小',
    uploadTime: '上传时间',
    indexStatus: '索引状态',
    parseStatus: '解析状态',
    statusParsed: '已解析',
    statusIndexed: '已索引',
    statusQueued: '排队中',
    statusParsing: '解析中',
    statusIndexing: '索引中',
    statusPending: '待处理',
    statusError: '错误',
    retryParse: '重试解析',
    queueReparse: '排队重新解析',
    queueReindex: '排队重新索引',
    reparseQueued: '已加入重新解析队列',
    reindexQueued: '已加入重新索引队列',
    processing: '处理中',
    selectDocument: '选择 {{name}}',
    viewParsed: '查看解析内容',
    confirmDelete: '确认删除',
    confirmDeleteDesc: '确定要删除"{{name}}"？',
    irreversible: '此操作不可撤销。',
    sourceDrive: 'Drive',
    sourceUpload: '上传',
    sourceColumn: '来源',
    openInDrive: '在 Google Drive 中打开',
    driveDeleteWarning: '此文档来自 Google Drive 同步，下次同步后可能会重新出现。',
  },
}, true, true)
import { DocumentParsedPreview } from '@/components/DocumentParsedPreview'
import { useDeleteDocuments, useReindexDocument, useReparseDocument } from '@/hooks/useDocuments'
import { useConfirmation } from '@/hooks/useConfirmation'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { Badge } from '@/components/ui/badge'
import { driveFileViewUrl } from '@/lib/documentsApi'
import { Cloud, Database, FileText, RefreshCw, Trash2, Upload } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { actionRules } from '@/lib/permissionRules'
import { formatDate } from '@/lib/dateTime'

interface DocumentTableProps {
  data: PaginatedResponse<Document> | undefined
  isLoading: boolean
  onPageChange: (page: number) => void
  searchQuery?: string
  selectedIds?: Set<number>
  onSelectionChange?: (selectedIds: Set<number>) => void
}

export function DocumentTable({
  data,
  isLoading,
  onPageChange,
  searchQuery = '',
  selectedIds: externalSelectedIds,
  onSelectionChange,
}: DocumentTableProps) {
  const { t } = useTranslation()
  const deleteMutation = useDeleteDocuments()
  const reparseMutation = useReparseDocument()
  const reindexMutation = useReindexDocument()
  const { hasAny } = useAuth()
  const [internalSelectedIds, setInternalSelectedIds] = useState<Set<number>>(new Set())
  const deleteConfirm = useConfirmation<Document | null>(null)
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)
  const documents = data?.items
  const total = data?.total || 0
  const totalPages = data?.total_pages || 0
  const currentPage = data?.page || 1
  const itemsPerPage = data?.page_size || 10

  const selectedIds = externalSelectedIds ?? internalSelectedIds
  const setSelectedIds = onSelectionChange ?? setInternalSelectedIds

  const canWrite = hasAny(actionRules.canUploadDocument())
  const canDelete = hasAny(actionRules.canDeleteDocument())
  const showActions = canWrite || canDelete
  const queuePending = reparseMutation.isPending || reindexMutation.isPending

  const handleSelectAll = (checked: boolean) => {
    if (checked && documents) {
      setSelectedIds(new Set(documents.map((doc) => doc.id)))
    } else {
      setSelectedIds(new Set())
    }
  }

  const handleSelectOne = (docId: number, checked: boolean) => {
    const newSelected = new Set(selectedIds)
    if (checked) {
      newSelected.add(docId)
    } else {
      newSelected.delete(docId)
    }
    setSelectedIds(newSelected)
  }

  const handleDeleteClick = (doc: Document) => {
    deleteConfirm.open(doc)
  }

  const handleDeleteConfirm = (doc: Document | null) => {
    if (doc === null) return
    deleteConfirm.setLoading(true)
    deleteMutation.mutateAsync(doc.id).finally(() => {
      deleteConfirm.setLoading(false)
      deleteConfirm.close()
    })
  }

  const isAllSelected = documents && documents.length > 0 && selectedIds.size === documents.length
  const isSomeSelected = selectedIds.size > 0 && selectedIds.size < (documents?.length || 0)

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
  }

  const renderParseStatus = (doc: Document) => {
    const view = getParsePipelineStatus(doc)
    return (
      <PipelineStatusBadge
        state={view.state}
        label={t(view.labelKey)}
        title={t('knowledgeBase.parseStatus')}
        timestamp={doc.parsedAt}
        error={doc.parseError}
      />
    )
  }

  const renderSourceBadge = (doc: Document) => {
    const isDrive = doc.intakeSource === 'drive_sync'
    const driveUrl = doc.externalFileId ? driveFileViewUrl(doc.externalFileId) : undefined
    const badge = (
      <Badge
        variant="outline"
        className="h-5 shrink-0 gap-1 px-1.5 text-[11px] font-normal"
        title={
          driveUrl
            ? t('knowledgeBase.openInDrive')
            : isDrive
              ? t('knowledgeBase.sourceDrive')
              : t('knowledgeBase.sourceUpload')
        }
      >
        {isDrive ? <Cloud className="h-3 w-3" /> : <Upload className="h-3 w-3" />}
        {isDrive ? t('knowledgeBase.sourceDrive') : t('knowledgeBase.sourceUpload')}
      </Badge>
    )

    if (driveUrl) {
      return (
        <a
          href={driveUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex rounded-md hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={t('knowledgeBase.openInDrive')}
        >
          {badge}
        </a>
      )
    }

    return badge
  }

  const renderIndexStatus = (doc: Document) => {
    const view = getIndexPipelineStatus(doc)
    return (
      <PipelineStatusBadge
        state={view.state}
        label={t(view.labelKey)}
        title={t('knowledgeBase.indexStatus')}
        timestamp={doc.lastVectorSyncedAt}
        error={doc.lastVectorSyncError}
      />
    )
  }

  if (isLoading) {
    return <p className="text-center text-sm text-muted-foreground py-8">{t('common.loading')}</p>
  }

  if (!documents || documents.length === 0) {
    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <FileText className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-50" />
        <p className="text-sm text-muted-foreground">
          {searchQuery ? t('knowledgeBase.noMatchingDocs') : t('knowledgeBase.noDocuments')}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="h-10 w-12">
                <Checkbox
                  checked={isAllSelected}
                  onCheckedChange={handleSelectAll}
                  aria-label={t('knowledgeBase.selectAll')}
                  className={isSomeSelected ? 'data-[state=checked]:bg-primary/50' : ''}
                />
              </TableHead>
              <TableHead className="h-10 w-16">{t('knowledgeBase.documentId')}</TableHead>
              <TableHead className="h-10">{t('knowledgeBase.filename')}</TableHead>
              <TableHead className="h-10 w-24">{t('knowledgeBase.sourceColumn')}</TableHead>
              <TableHead className="h-10 w-32">{t('knowledgeBase.uploader')}</TableHead>
              <TableHead className="h-10 w-24">{t('knowledgeBase.size')}</TableHead>
              <TableHead className="h-10 w-40">{t('knowledgeBase.uploadTime')}</TableHead>
              <TableHead className="h-10 w-40">{t('common.updateTime')}</TableHead>
              <TableHead className="h-10 w-32">{t('knowledgeBase.parseStatus')}</TableHead>
              <TableHead className="h-10 w-32">{t('knowledgeBase.indexStatus')}</TableHead>
              {showActions && (
                <TableHead className="h-10 w-28 text-right">{t('common.action')}</TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((doc) => (
              <TableRow key={doc.id}>
                <TableCell className="py-2.5">
                  <Checkbox
                    checked={selectedIds.has(doc.id)}
                    onCheckedChange={(checked) => handleSelectOne(doc.id, checked as boolean)}
                    aria-label={t('knowledgeBase.selectDocument', { name: doc.filename })}
                  />
                </TableCell>
                <TableCell className="py-2.5">
                  <span
                    className="font-mono text-xs text-muted-foreground tabular-nums"
                    title={t('knowledgeBase.documentIdLabel', { id: doc.id })}
                  >
                    #{doc.id}
                  </span>
                </TableCell>
                <TableCell className="py-2.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    <button
                      type="button"
                      className="text-sm truncate text-left hover:underline min-w-0"
                      title={t('knowledgeBase.viewParsed')}
                      onClick={() => setPreviewDoc(doc)}
                    >
                      {doc.filename}
                    </button>
                  </div>
                </TableCell>
                <TableCell className="py-2.5">{renderSourceBadge(doc)}</TableCell>
                <TableCell className="py-2.5 text-sm">{doc.ownerUsername || '—'}</TableCell>
                <TableCell className="py-2.5 text-sm">{formatFileSize(doc.fileSize)}</TableCell>
                <TableCell className="py-2.5 text-sm">{formatDate(doc.uploadDate)}</TableCell>
                <TableCell className="py-2.5 text-sm">{formatDate(doc.updatedAt)}</TableCell>
                <TableCell className="py-2.5 text-sm">{renderParseStatus(doc)}</TableCell>
                <TableCell className="py-2.5 text-sm">{renderIndexStatus(doc)}</TableCell>
                {showActions && (
                  <TableCell className="py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {canWrite && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            disabled={queuePending}
                            onClick={() => reparseMutation.mutate(doc.id)}
                            aria-label={t('knowledgeBase.queueReparse')}
                            title={t('knowledgeBase.queueReparse')}
                          >
                            <RefreshCw className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            disabled={queuePending || doc.status === 'processing'}
                            onClick={() => reindexMutation.mutate(doc.id)}
                            aria-label={t('knowledgeBase.queueReindex')}
                            title={t('knowledgeBase.queueReindex')}
                          >
                            <Database className="w-4 h-4" />
                          </Button>
                        </>
                      )}
                      {canDelete && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          onClick={() => handleDeleteClick(doc)}
                          disabled={deleteMutation.isPending}
                          aria-label={t('common.delete')}
                          title={t('common.delete')}
                        >
                          <Trash2 className="w-4 h-4 text-destructive" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <PaginationBar
        page={currentPage}
        pageSize={itemsPerPage}
        total={total}
        totalPages={totalPages}
        onPageChange={onPageChange}
      />

      <ConfirmationDialog<Document | null>
        open={deleteConfirm.isOpen}
        item={deleteConfirm.item}
        isLoading={deleteConfirm.isLoading}
        title={t('knowledgeBase.confirmDelete')}
        description={(doc) => (
          <>
            {doc ? (
              <span className="font-mono text-xs text-muted-foreground block mb-1">
                {t('knowledgeBase.documentIdLabel', { id: doc.id })}
              </span>
            ) : null}
            {t('knowledgeBase.confirmDeleteDesc', { name: doc?.filename })}
            {doc?.intakeSource === 'drive_sync' ? (
              <>
                <br />
                <span className="text-amber-600">{t('knowledgeBase.driveDeleteWarning')}</span>
              </>
            ) : null}
            <br />
            <span className="text-red-600">{t('knowledgeBase.irreversible')}</span>
          </>
        )}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={handleDeleteConfirm}
        onCancel={deleteConfirm.close}
      />

      <DocumentParsedPreview
        document={previewDoc}
        open={previewDoc != null}
        onOpenChange={(open) => {
          if (!open) setPreviewDoc(null)
        }}
      />
    </div>
  )
}
