import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  useCancelScheduledTask,
  useDeleteScheduledTask,
  usePauseScheduledTask,
  useResumeScheduledTask,
  useScheduledTasks,
} from '@/hooks/useScheduledTasks'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import { formatDate } from '@/lib/dateTime'
import type { LiveAppJobTaskConfig, ScheduledTask } from '@/lib/scheduledTasksApi'
import { getScheduledTaskStatusClass } from '@/lib/scheduledTaskUi'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { useConfirmation } from '@/hooks/useConfirmation'
import { CalendarClock, LayoutGrid, Pause, Play, Share2, Trash2, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  scheduledTasks: {
    all: 'All',
    pending: 'Pending',
    running: 'Running',
    paused: 'Paused',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
    description: 'Schedule and manage automated tasks',
    noTasks: 'No scheduled tasks found',
    nameCol: 'Name',
    ownerCol: 'Owner',
    statusCol: 'Status',
    taskTypeCol: 'Task Type',
    scheduleCol: 'Schedule',
    nextRunCol: 'Next Run',
    lastRunCol: 'Last Run',
    actionsCol: 'Actions',
    oneTime: 'One-time',
    cronSchedule: 'Recurring',
    cronHint: 'UTC',
    resume: 'Resume',
    pause: 'Pause',
    cancel: 'Cancel',
    share: 'Share',
    confirmCancelTitle: 'Cancel task',
    confirmCancel: 'Are you sure you want to cancel "{name}"?',
    confirmDeleteTitle: 'Delete task',
    confirmDelete: 'Are you sure you want to delete "{name}"?',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  scheduledTasks: {
    all: '全部',
    pending: '待处理',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    description: '调度和管理自动化任务',
    noTasks: '暂无定时任务',
    nameCol: '名称',
    ownerCol: '所有者',
    statusCol: '状态',
    taskTypeCol: '任务类型',
    scheduleCol: '调度',
    nextRunCol: '下次执行',
    lastRunCol: '上次执行',
    actionsCol: '操作',
    oneTime: '一次性',
    cronSchedule: '周期性',
    cronHint: 'UTC',
    resume: '恢复',
    pause: '暂停',
    cancel: '取消',
    share: '分享',
    confirmCancelTitle: '取消任务',
    confirmCancel: '确定要取消"{name}"吗？',
    confirmDeleteTitle: '删除任务',
    confirmDelete: '确定要删除"{name}"吗？',
  }
}, true, true)
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

function getStatusFilters(t: (key: string) => string) {
  return [
    { label: t('scheduledTasks.all'), value: undefined, route: '/artifacts/scheduled-tasks' },
    {
      label: t('scheduledTasks.pending'),
      value: 'pending',
      route: '/artifacts/scheduled-tasks?status=pending',
    },
    {
      label: t('scheduledTasks.running'),
      value: 'running',
      route: '/artifacts/scheduled-tasks?status=running',
    },
    {
      label: t('scheduledTasks.paused'),
      value: 'paused',
      route: '/artifacts/scheduled-tasks?status=paused',
    },
    {
      label: t('scheduledTasks.completed'),
      value: 'completed',
      route: '/artifacts/scheduled-tasks?status=completed',
    },
    {
      label: t('scheduledTasks.failed'),
      value: 'failed',
      route: '/artifacts/scheduled-tasks?status=failed',
    },
    {
      label: t('scheduledTasks.cancelled'),
      value: 'cancelled',
      route: '/artifacts/scheduled-tasks?status=cancelled',
    },
  ] as const
}

type ToggleAction = 'pause' | 'resume' | null

function getToggleAction(status: string): ToggleAction {
  if (status === 'pending' || status === 'running') return 'pause'
  if (status === 'paused') return 'resume'
  return null
}

function canCancel(status: string): boolean {
  return status !== 'running' && status !== 'completed' && status !== 'cancelled'
}

function canDelete(status: string): boolean {
  return status !== 'running'
}

function getScheduleDisplay(task: ScheduledTask, t: (key: string) => string): string {
  if (task.schedule_type === 'once') return t('scheduledTasks.oneTime')
  const cronExpr = 'cron' in task.schedule_spec ? task.schedule_spec.cron : undefined
  const timezone = 'timezone' in task.schedule_spec ? task.schedule_spec.timezone : undefined
  if (typeof cronExpr !== 'string' || !cronExpr.trim()) return t('scheduledTasks.cronSchedule')
  return timezone ? `${cronExpr} (${timezone})` : cronExpr
}

function isCronTask(task: ScheduledTask): boolean {
  return task.schedule_type === 'cron' && 'cron' in task.schedule_spec
}

function getTaskTypeDisplay(task: ScheduledTask): React.ReactNode {
  if (task.task_type === 'liveapp_job') {
    const config = task.task_config as LiveAppJobTaskConfig
    return (
      <div className="space-y-1">
        <span className="font-medium">{config.job_name}</span>
        <Link to={`/apps/${config.app_id}`} className="text-xs text-foreground hover:underline block">
          App #{config.app_id} ({config.environment})
        </Link>
      </div>
    )
  }
  return <span>{task.task_type}</span>
}

export default function ScheduledTasksPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const status = searchParams.get('status') ?? undefined
  const { data: tasks = [], isLoading } = useScheduledTasks(status)
  const pauseMutation = usePauseScheduledTask()
  const resumeMutation = useResumeScheduledTask()
  const cancelMutation = useCancelScheduledTask()
  const deleteMutation = useDeleteScheduledTask()
  const [sharingTask, setSharingTask] = useState<ScheduledTask | null>(null)
  const cancelConfirm = useConfirmation<ScheduledTask>()
  const deleteConfirm = useConfirmation<ScheduledTask>()

  const statusFilters = useMemo(() => getStatusFilters(t), [t])
  const activeFilter = useMemo(() => statusFilters.find((item) => item.value === status), [status, statusFilters])
  const isMutating =
    pauseMutation.isPending ||
    resumeMutation.isPending ||
    cancelMutation.isPending ||
    deleteMutation.isPending

  const handlePause = async (task: ScheduledTask) => {
    await pauseMutation.mutateAsync(task.id)
  }

  const handleResume = async (task: ScheduledTask) => {
    await resumeMutation.mutateAsync(task.id)
  }

  const handleToggle = async (task: ScheduledTask) => {
    const action = getToggleAction(task.status)
    if (action === 'pause') {
      await handlePause(task)
      return
    }
    if (action === 'resume') {
      await handleResume(task)
    }
  }

  const handleCancel = async (task: ScheduledTask) => {
    cancelConfirm.setLoading(true)
    try {
      await cancelMutation.mutateAsync(task.id)
      cancelConfirm.close()
    } catch {
      cancelConfirm.setLoading(false)
    }
  }

  const handleDelete = async (task: ScheduledTask) => {
    deleteConfirm.setLoading(true)
    try {
      await deleteMutation.mutateAsync(task.id)
      deleteConfirm.close()
    } catch {
      deleteConfirm.setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('sidebar.scheduledTasks')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('scheduledTasks.description')}</p>
      </div>

      <div className="flex gap-2 flex-wrap">
        {statusFilters.map((f) => (
          <Button
            key={f.label}
            variant={activeFilter?.value === f.value ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => navigate(f.route)}
          >
            {f.label}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
          {t('common.loading')}
        </div>
      ) : tasks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
          <LayoutGrid className="w-10 h-10 opacity-30" />
          <p className="text-sm">{t('scheduledTasks.noTasks')}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>ID</TableHead>
                <TableHead>{t('scheduledTasks.nameCol')}</TableHead>
                <TableHead className="w-32">{t('scheduledTasks.ownerCol')}</TableHead>
                <TableHead>{t('scheduledTasks.statusCol')}</TableHead>
                <TableHead>{t('scheduledTasks.taskTypeCol')}</TableHead>
                <TableHead>{t('scheduledTasks.scheduleCol')}</TableHead>
                <TableHead>{t('scheduledTasks.nextRunCol')}</TableHead>
                <TableHead>{t('scheduledTasks.lastRunCol')}</TableHead>
                <TableHead className="text-right">{t('scheduledTasks.actionsCol')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tasks.map((task) => (
                <TableRow key={task.id}>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {task.id}
                  </TableCell>
                  <TableCell className="max-w-[280px] font-medium">
                    <Link
                      to={`/scheduled-tasks/${task.id}`}
                      className="block truncate hover:underline"
                      title={task.name}
                    >
                      {task.name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm">{task.owner_name || t('dataSources.deletedUser')}</span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={getScheduledTaskStatusClass(task.status)}>
                      {task.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{getTaskTypeDisplay(task)}</TableCell>
                  <TableCell>
                    {isCronTask(task) ? (
                      <div className="space-y-1">
                        <code
                          className="inline-block rounded bg-muted px-2 py-0.5 font-mono text-xs text-foreground"
                          title="Cron format: minute hour day-of-month month day-of-week (UTC)"
                        >
                          {getScheduleDisplay(task, t)}
                        </code>
                        <p className="text-[11px] text-muted-foreground">{t('scheduledTasks.cronHint')}</p>
                      </div>
                    ) : (
                      getScheduleDisplay(task, t)
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
                      <CalendarClock className="w-3.5 h-3.5" />
                      {formatDate(task.next_run_at)}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(task.last_run_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        title={getToggleAction(task.status) === 'resume' ? t('scheduledTasks.resume') : t('scheduledTasks.pause')}
                        disabled={!getToggleAction(task.status) || isMutating}
                        onClick={() => handleToggle(task)}
                      >
                        {getToggleAction(task.status) === 'resume' ? (
                          <Play className="w-3.5 h-3.5" />
                        ) : (
                          <Pause className="w-3.5 h-3.5" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-orange-600"
                        title={t('scheduledTasks.cancel')}
                        disabled={!canCancel(task.status) || isMutating}
                        onClick={() => cancelConfirm.open(task)}
                      >
                        <XCircle className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        title={t('scheduledTasks.share')}
                        onClick={() => setSharingTask(task)}
                      >
                        <Share2 className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                        title={t('common.delete')}
                        disabled={!canDelete(task.status) || isMutating}
                        onClick={() => deleteConfirm.open(task)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <ConfirmationDialog
        open={cancelConfirm.isOpen}
        item={cancelConfirm.item}
        isLoading={cancelConfirm.isLoading}
        title={t('scheduledTasks.confirmCancelTitle')}
        description={(item) => t('scheduledTasks.confirmCancel', { name: item.name })}
        confirmText={t('scheduledTasks.cancel')}
        isDangerous
        onConfirm={handleCancel}
        onCancel={cancelConfirm.close}
      />
      <ConfirmationDialog
        open={deleteConfirm.isOpen}
        item={deleteConfirm.item}
        isLoading={deleteConfirm.isLoading}
        title={t('scheduledTasks.confirmDeleteTitle')}
        description={(item) => t('scheduledTasks.confirmDelete', { name: item.name })}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={handleDelete}
        onCancel={deleteConfirm.close}
      />

      {sharingTask && (
        <ResourceAclShareDialog
          open={Boolean(sharingTask)}
          onOpenChange={(open) => {
            if (!open) {
              setSharingTask(null)
            }
          }}
          resourceType={ACL_SHARE_RESOURCE_TYPES.SCHEDULED_TASK}
          resourceId={sharingTask.id}
          resourceTitle={sharingTask.name}
        />
      )}
    </div>
  )
}
