import EmptyState from '@/components/EmptyState'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/hooks/useAuth'
import { useDeleteReport, useReports } from '@/hooks/useReports'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import { actionRules, canDeleteOwnedArtifact } from '@/lib/permissionRules'
import { formatDate } from '@/lib/dateTime'
import type { Report } from '@/lib/reportsApi'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { useConfirmation } from '@/hooks/useConfirmation'
import { FileText, Share2, Trash2 } from 'lucide-react'
import { useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  reports: {
    description: 'View and manage generated reports',
    noReports: 'No reports yet',
    noReportsHint: 'Reports are generated from workbench conversations. Open a conversation and ask the agent to write one.',
    openWorkbench: 'Open workbench',
    nameCol: 'Title',
    ownerCol: 'Owner',
    updatedCol: 'Last Updated',
    actionsCol: 'Actions',
    share: 'Share',
    confirmDeleteTitle: 'Delete report',
    confirmDelete: 'Are you sure you want to delete "{{title}}"?',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  reports: {
    description: '查看和管理生成的报告',
    noReports: '暂无报告',
    noReportsHint: '报告从工作台对话中生成。打开一个会话，让 Agent 撰写报告。',
    openWorkbench: '打开工作台',
    nameCol: '标题',
    ownerCol: '所有者',
    updatedCol: '最后更新',
    actionsCol: '操作',
    share: '分享',
    confirmDeleteTitle: '删除报告',
    confirmDelete: '确定要删除"{{title}}"吗？',
  }
}, true, true)
import { Link } from 'react-router-dom'

export default function ReportsPage() {
  const { t } = useTranslation()
  const { user, hasAny } = useAuth()
  const canManageAllArtifacts = hasAny(actionRules.canManageAllArtifacts())
  const { data: reports = [], isLoading } = useReports()
  const deleteMutation = useDeleteReport()
  const [sharingReport, setSharingReport] = useState<Report | null>(null)
  const deleteConfirm = useConfirmation<Report>()

  const handleDelete = async (report: Report) => {
    deleteConfirm.setLoading(true)
    try {
      await deleteMutation.mutateAsync(report.id)
      deleteConfirm.close()
    } catch {
      deleteConfirm.setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold inline-flex items-center gap-2">
          <FileText className="w-6 h-6" />
          {t('sidebar.reports')}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">{t('reports.description')}</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
          {t('common.loading')}
        </div>
      ) : reports.length === 0 ? (
        <EmptyState
          title={t('reports.noReports')}
          description={t('reports.noReportsHint')}
          action={
            <Button asChild>
              <Link to="/workbench">{t('reports.openWorkbench')}</Link>
            </Button>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{t('reports.nameCol')}</TableHead>
                <TableHead className="w-28">{t('reports.ownerCol')}</TableHead>
                <TableHead className="w-40">{t('reports.updatedCol')}</TableHead>
                <TableHead className="w-28 text-right">{t('reports.actionsCol')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reports.map((report) => (
                <TableRow key={report.id}>
                  <TableCell className="font-medium">
                    <Link to={`/reports/${report.id}`} className="hover:underline">
                      {report.title}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {report.owner_username ?? report.owner_id ?? '—'}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(report.updated_at, { precision: 'datetime' })}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        title={t('reports.share')}
                        onClick={() => setSharingReport(report)}
                      >
                        <Share2 className="w-3.5 h-3.5" />
                      </Button>
                      {canDeleteOwnedArtifact(report.owner_id, user?.id, canManageAllArtifacts) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          title={t('common.delete')}
                          onClick={() => deleteConfirm.open(report)}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <ConfirmationDialog
        open={deleteConfirm.isOpen}
        item={deleteConfirm.item}
        isLoading={deleteConfirm.isLoading}
        title={t('reports.confirmDeleteTitle')}
        description={(item) => t('reports.confirmDelete', { title: item.title })}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={handleDelete}
        onCancel={deleteConfirm.close}
      />

      {sharingReport && (
        <ResourceAclShareDialog
          open={Boolean(sharingReport)}
          onOpenChange={(open) => {
            if (!open) {
              setSharingReport(null)
            }
          }}
          resourceType={ACL_SHARE_RESOURCE_TYPES.REPORT}
          resourceId={sharingReport.id}
          resourceTitle={sharingReport.title}
        />
      )}
    </div>
  )
}
