import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import type { CollectionDocumentsDeleteBatchConfirm, CollectionDocumentsData } from '@/hooks/useCollectionDocumentsPage'
import { Trans, useTranslation } from 'react-i18next'

interface DocumentBatchDeleteDialogProps {
  documentsData: CollectionDocumentsData
  deleteBatchConfirm: CollectionDocumentsDeleteBatchConfirm
  onBatchDeleteConfirm: (docIds: number[]) => void
}

export default function DocumentBatchDeleteDialog({
  documentsData,
  deleteBatchConfirm,
  onBatchDeleteConfirm,
}: DocumentBatchDeleteDialogProps) {
  const { t } = useTranslation()

  return (
    <ConfirmationDialog<number[]>
      open={deleteBatchConfirm.isOpen}
      item={deleteBatchConfirm.item}
      isLoading={deleteBatchConfirm.isLoading}
      title={t('knowledgeBase.confirmBatchDelete')}
      description={(docIds) => {
        const selectedDocs = documentsData?.items.filter((doc) => docIds?.includes(doc.id)) || []
        const driveLinkedCount = selectedDocs.filter((doc) => doc.intakeSource === 'drive_sync').length
        return (
          <>
            <Trans i18nKey="knowledgeBase.confirmBatchDeleteDesc" count={docIds?.length || 0} />
            {driveLinkedCount > 0 ? (
              <span className="text-amber-600 mt-2 block">
                {t('knowledgeBase.batchDriveDeleteWarning', { count: driveLinkedCount })}
              </span>
            ) : null}
            <div className="mt-2 max-h-32 overflow-y-auto text-sm">
              <ul className="list-disc list-inside space-y-1">
                {selectedDocs.slice(0, 5).map((doc) => (
                  <li key={doc.id} className="truncate">
                    <span className="font-mono text-xs text-muted-foreground mr-1.5">#{doc.id}</span>
                    {doc.filename}
                  </li>
                ))}
                {selectedDocs.length > 5 && (
                  <li className="text-muted-foreground">
                    {t('knowledgeBase.andMore', { count: selectedDocs.length - 5 })}
                  </li>
                )}
              </ul>
            </div>
            <span className="text-red-600 mt-2 block">{t('knowledgeBase.irreversible')}</span>
          </>
        )
      }}
      confirmText={t('knowledgeBase.batchDelete')}
      isDangerous
      onConfirm={onBatchDeleteConfirm}
      onCancel={deleteBatchConfirm.close}
    />
  )
}
