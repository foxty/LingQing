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
import { useDashboards, useDeleteDashboard } from '@/hooks/useDashboard'
import { useNotification } from '@/hooks/useNotification'
import { actionRules, canDeleteOwnedArtifact } from '@/lib/permissionRules'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import { formatDate } from '@/lib/dateTime'
import type { DashboardListItem } from '@/lib/dashboardApi'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { useConfirmation } from '@/hooks/useConfirmation'
import { LayoutDashboard, Share2, Trash2 } from 'lucide-react'
import { useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  dashboards: {
    description: 'Create and manage visual dashboards',
    noDashboards: 'No dashboards yet',
    noDashboardsHint: 'Ask the workbench agent to build a dashboard from a query, or wait until one is shared with you.',
    openWorkbench: 'Open workbench',
    nameCol: 'Name',
    ownerCol: 'Owner',
    updatedCol: 'Last Updated',
    actionsCol: 'Actions',
    share: 'Share',
    confirmDeleteTitle: 'Delete dashboard',
    confirmDelete: 'Are you sure you want to delete "{{name}}"?',
    deleteSuccess: 'Dashboard deleted successfully',
    deleteFailed: 'Failed to delete dashboard',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  dashboards: {
    description: '创建和管理可视化仪表盘',
    noDashboards: '暂无仪表盘',
    noDashboardsHint: '在工作台让 Agent 根据查询生成仪表盘，或等待他人分享给你。',
    openWorkbench: '打开工作台',
    nameCol: '名称',
    ownerCol: '所有者',
    updatedCol: '最后更新',
    actionsCol: '操作',
    share: '分享',
    confirmDeleteTitle: '删除仪表盘',
    confirmDelete: '确定要删除"{{name}}"吗？',
    deleteSuccess: '仪表盘删除成功',
    deleteFailed: '删除仪表盘失败',
  }
}, true, true)
import { Link } from 'react-router-dom'

export default function DashboardsPage() {
  const { t } = useTranslation()
  const { user, hasAny } = useAuth()
  const canManageAllArtifacts = hasAny(actionRules.canManageAllArtifacts())
  const { data: dashboards = [], isLoading } = useDashboards()
  const deleteMutation = useDeleteDashboard()
  const { showError, showSuccess } = useNotification()
  const [sharingDashboard, setSharingDashboard] = useState<DashboardListItem | null>(null)
  const deleteConfirm = useConfirmation<DashboardListItem>()

  const handleDelete = async (dashboard: DashboardListItem) => {
    deleteConfirm.setLoading(true)
    try {
      await deleteMutation.mutateAsync(dashboard.id)
      showSuccess(t('dashboards.deleteSuccess'))
      deleteConfirm.close()
    } catch {
      showError(t('dashboards.deleteFailed'))
      deleteConfirm.setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold inline-flex items-center gap-2">
          <LayoutDashboard className="w-6 h-6" />
          {t('sidebar.dashboards')}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">{t('dashboards.description')}</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
          {t('common.loading')}
        </div>
      ) : dashboards.length === 0 ? (
        <EmptyState
          title={t('dashboards.noDashboards')}
          description={t('dashboards.noDashboardsHint')}
          action={
            <Button asChild>
              <Link to="/workbench">{t('dashboards.openWorkbench')}</Link>
            </Button>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{t('dashboards.nameCol')}</TableHead>
                <TableHead className="w-24">{t('dashboards.ownerCol')}</TableHead>
                <TableHead className="w-40">{t('dashboards.updatedCol')}</TableHead>
                <TableHead className="w-28 text-right">{t('dashboards.actionsCol')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {dashboards.map((dashboard) => (
                <TableRow key={dashboard.id}>
                  <TableCell className="font-medium">
                    <Link to={`/dashboards/${dashboard.id}`} className="hover:underline">
                      {dashboard.name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {dashboard.owner_username ?? dashboard.owner_id}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(dashboard.updated_at, { precision: 'datetime' })}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        title={t('dashboards.share')}
                        onClick={() => setSharingDashboard(dashboard)}
                      >
                        <Share2 className="w-3.5 h-3.5" />
                      </Button>
                      {canDeleteOwnedArtifact(dashboard.owner_id, user?.id, canManageAllArtifacts) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          title={t('common.delete')}
                          onClick={() => deleteConfirm.open(dashboard)}
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
        title={t('dashboards.confirmDeleteTitle')}
        description={(item) => t('dashboards.confirmDelete', { name: item.name })}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={handleDelete}
        onCancel={deleteConfirm.close}
      />

      {sharingDashboard && (
        <ResourceAclShareDialog
          open={Boolean(sharingDashboard)}
          onOpenChange={(open) => {
            if (!open) {
              setSharingDashboard(null)
            }
          }}
          resourceType={ACL_SHARE_RESOURCE_TYPES.DASHBOARD}
          resourceId={sharingDashboard.id}
          resourceTitle={sharingDashboard.name}
        />
      )}
    </div>
  )
}
