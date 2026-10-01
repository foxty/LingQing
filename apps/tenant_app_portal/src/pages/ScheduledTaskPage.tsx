import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import PaginationBar from '@/components/PaginationBar'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import {
  useCancelScheduledTask,
  useDeleteScheduledTask,
  usePauseScheduledTask,
  useResumeScheduledTask,
  useRunScheduledTask,
  useScheduledTaskDetail,
  useScheduledTaskRuns,
  useTaskRunLogs,
} from '@/hooks/useScheduledTasks'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import { formatDate } from '@/lib/dateTime'
import { getScheduledTaskStatusClass } from '@/lib/scheduledTaskUi'
import type {
  ScheduledTask,
  ScheduledTaskConfig,
  ScheduledTaskRun,
  LogStream,
} from '@/lib/scheduledTasksApi'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Calendar, Clock3, FileText, Pause, Play, Share2, Trash2, XCircle, Zap } from 'lucide-react'
import { useMemo, useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  scheduledTask: {
    resume: 'Resume',
    pause: 'Pause',
    notFound: 'Task not found',
    createdAt: 'Created: {{date}}',
    nextRunAt: 'Next run: {{date}}',
    taskTypeLabel: 'Task Type',
    ownerLabel: 'Owner',
    scheduleTypeLabel: 'Schedule Type',
    share: 'Share',
    cancel: 'Cancel',
    delete: 'Delete Task',
    sourceSessionLabel: 'Source Session',
    taskDetails: 'Task Details',
    statusLabel: 'Status',
    createdAtLabel: 'Created At',
    updatedAtLabel: 'Updated At',
    nextRunAtLabel: 'Next Run',
    lastRunAtLabel: 'Last Run',
    notifyChannels: 'Notification Channels',
    defaultChannel: 'No notification channels configured',
    execRecords: 'Execution Records',
    execRecordsLoading: 'Loading execution records...',
    noExecRecords: 'No execution records yet',
    execStatusCol: 'Status',
    execStartCol: 'Started',
    execEndCol: 'Finished',
    execDurationCol: 'Duration',
    execActionsCol: 'Actions',
    viewDetails: 'View Details',
    confirmRunTitle: 'Run now',
    confirmRun: 'Run "{{name}}" immediately?',
    confirmCancelTitle: 'Cancel task',
    confirmCancel: 'Cancel "{{name}}"?',
    confirmDeleteTitle: 'Delete task',
    confirmDelete: 'Delete "{{name}}"? This cannot be undone.',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  scheduledTask: {
    resume: '恢复',
    pause: '暂停',
    notFound: '未找到任务',
    createdAt: '创建于：{{date}}',
    nextRunAt: '下次执行：{{date}}',
    taskTypeLabel: '任务类型',
    ownerLabel: '所有者',
    scheduleTypeLabel: '调度类型',
    share: '分享',
    cancel: '取消',
    delete: '删除任务',
    sourceSessionLabel: '来源会话',
    taskDetails: '任务详情',
    statusLabel: '状态',
    createdAtLabel: '创建时间',
    updatedAtLabel: '更新时间',
    nextRunAtLabel: '下次执行',
    lastRunAtLabel: '上次执行',
    notifyChannels: '通知渠道',
    defaultChannel: '未配置通知渠道',
    execRecords: '执行记录',
    execRecordsLoading: '正在加载执行记录...',
    noExecRecords: '暂无执行记录',
    execStatusCol: '状态',
    execStartCol: '开始时间',
    execEndCol: '结束时间',
    execDurationCol: '耗时',
    execActionsCol: '操作',
    viewDetails: '查看详情',
    confirmRunTitle: '立即执行',
    confirmRun: '立即执行“{{name}}”？',
    confirmCancelTitle: '取消任务',
    confirmCancel: '取消“{{name}}”？',
    confirmDeleteTitle: '删除任务',
    confirmDelete: '删除“{{name}}”？此操作不可恢复。',
  }
}, true, true)
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

function formatDuration(durationMs?: number | null): string {
  if (durationMs === null || durationMs === undefined) return '—'
  if (durationMs < 1000) return `${durationMs}ms`
  return `${(durationMs / 1000).toFixed(2)}s`
}

function canPause(status: string): boolean {
  return status === 'pending' || status === 'running'
}

function canResume(status: string): boolean {
  return status === 'paused'
}

function getToggleLabel(status: string, t: (key: string) => string): string {
  return canResume(status) ? t('scheduledTask.resume') : t('scheduledTask.pause')
}

function canCancel(status: string): boolean {
  return status === 'pending' || status === 'paused'
}

function canRun(status: string): boolean {
  return status === 'pending' || status === 'paused'
}

function canDelete(status: string): boolean {
  return status !== 'running'
}

function isSystemTask(task: ScheduledTask): boolean {
  return Boolean(task.is_system)
}

function getOriginThreadId(taskConfig: ScheduledTaskConfig): string | null {
  if ('origin_thread_id' in taskConfig && typeof taskConfig.origin_thread_id === 'string') {
    return taskConfig.origin_thread_id
  }
  return null
}

function LogStreamPanel({
  taskId,
  runId,
  stream,
}: {
  taskId: number
  runId: number
  stream: LogStream
}) {
  const query = useTaskRunLogs(taskId, runId, stream)

  if (query.isLoading) {
    return <p className="text-sm text-muted-foreground py-4">加载中…</p>
  }
  if (query.isError) {
    return <p className="text-sm text-destructive py-4">无法加载日志</p>
  }
  const content = (query.data ?? '').trim()
  if (!content) {
    return <p className="text-sm text-muted-foreground py-4">（空）</p>
  }
  return (
    <pre className="rounded-md border bg-muted/30 p-3 text-xs font-mono whitespace-pre-wrap break-all overflow-auto max-h-[60vh]">
      {content}
    </pre>
  )
}

function TaskRunLogDialog({
  taskId,
  run,
  onClose,
}: {
  taskId: number
  run: ScheduledTaskRun
  onClose: () => void
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>执行日志 — Run #{run.id}</DialogTitle>
          <DialogDescription>
            {run.status === 'failed' ? '❌ 失败' : '✅ 成功'} · {formatDate(run.started_at)} · 耗时{' '}
            {formatDuration(run.duration_ms)}
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="stdout" className="flex-1 min-h-0 flex flex-col">
          <TabsList>
            <TabsTrigger value="stdout">标准输出</TabsTrigger>
            <TabsTrigger value="stderr">错误输出</TabsTrigger>
          </TabsList>
          <TabsContent value="stdout" className="flex-1 min-h-0 overflow-auto">
            <LogStreamPanel taskId={taskId} runId={run.id} stream="stdout" />
          </TabsContent>
          <TabsContent value="stderr" className="flex-1 min-h-0 overflow-auto">
            <LogStreamPanel taskId={taskId} runId={run.id} stream="stderr" />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

export default function ScheduledTaskPage() {
  const { t } = useTranslation()
  const { taskId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const isEmbedView = location.pathname.endsWith('/embed')
  const [sharingTask, setSharingTask] = useState<ScheduledTask | null>(null)
  const [pendingAction, setPendingAction] = useState<'run' | 'cancel' | 'delete' | null>(null)
  const [viewingLogRun, setViewingLogRun] = useState<ScheduledTaskRun | null>(null)
  const [runsPage, setRunsPage] = useState(1)
  const runsPageSize = 20

  const id = useMemo(() => {
    if (!taskId) return null
    const parsed = Number(taskId)
    return Number.isFinite(parsed) ? parsed : null
  }, [taskId])

  const taskQuery = useScheduledTaskDetail(id)
  const runsQuery = useScheduledTaskRuns(id, runsPage, runsPageSize)
  const pauseMutation = usePauseScheduledTask()
  const resumeMutation = useResumeScheduledTask()
  const cancelMutation = useCancelScheduledTask()
  const deleteMutation = useDeleteScheduledTask()
  const runMutation = useRunScheduledTask()

  if (taskQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
        {t('common.loading')}
      </div>
    )
  }

  if (taskQuery.isError || !taskQuery.data) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
        <p className="text-sm">{t('scheduledTask.notFound')}</p>
      </div>
    )
  }

  const task = taskQuery.data
  const originThreadId = getOriginThreadId(task.task_config)
  const runsData = runsQuery.data
  const runs = runsData?.items ?? []
  const totalRuns = runsData?.total ?? 0
  const totalPages = Math.ceil(totalRuns / runsPageSize)
  const isMutating =
    pauseMutation.isPending ||
    resumeMutation.isPending ||
    cancelMutation.isPending ||
    deleteMutation.isPending ||
    runMutation.isPending

  const handlePause = async () => {
    await pauseMutation.mutateAsync(task.id)
  }

  const handleResume = async () => {
    await resumeMutation.mutateAsync(task.id)
  }

  const handleToggle = async () => {
    if (canResume(task.status)) {
      await handleResume()
      return
    }
    if (canPause(task.status)) {
      await handlePause()
    }
  }

  const handleRun = async () => {
    await runMutation.mutateAsync(task.id)
    setPendingAction(null)
  }

  const handleCancel = async () => {
    await cancelMutation.mutateAsync(task.id)
    setPendingAction(null)
  }

  const handleDelete = async () => {
    await deleteMutation.mutateAsync(task.id)
    setPendingAction(null)
    if (!isEmbedView) {
      navigate('/artifacts/scheduled-tasks')
    }
  }

  return (
    <div className={`space-y-5 ${isEmbedView ? 'p-4' : ''}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{task.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" />
              {t('scheduledTask.createdAt', { date: formatDate(task.created_at) })}
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock3 className="w-3.5 h-3.5" />
              {t('scheduledTask.nextRunAt', { date: formatDate(task.next_run_at) })}
            </span>
            <span>
              {t('scheduledTask.taskTypeLabel')}: <code>{task.task_type}</code>
            </span>
            <span>
              {t('scheduledTask.ownerLabel')}: <span className="text-foreground">{task.owner_name || t('dataSources.deletedUser')}</span>
            </span>
            <span>
              {t('scheduledTask.scheduleTypeLabel')}: <code>{task.schedule_type}</code>
            </span>
            <Badge variant="outline" className={getScheduledTaskStatusClass(task.status)}>
              {task.status}
            </Badge>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!isSystemTask(task) && (
            <Button variant="outline" size="sm" onClick={() => setSharingTask(task)}>
              <Share2 className="w-4 h-4 mr-1.5" />
              {t('scheduledTask.share')}
            </Button>
          )}
          <Button
            variant="default"
            size="sm"
            disabled={!canRun(task.status) || isMutating}
            onClick={() => setPendingAction('run')}
          >
            <Zap className="w-4 h-4 mr-1.5" />
            {t('scheduledTask.confirmRunTitle')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={(!canPause(task.status) && !canResume(task.status)) || isMutating}
            onClick={handleToggle}
          >
            {canResume(task.status) ? (
              <Play className="w-4 h-4 mr-1.5" />
            ) : (
              <Pause className="w-4 h-4 mr-1.5" />
            )}
            {getToggleLabel(task.status, t)}
          </Button>
          {!isSystemTask(task) && (
            <Button
              variant="outline"
              size="sm"
              disabled={!canCancel(task.status) || isMutating}
              onClick={() => setPendingAction('cancel')}
            >
              <XCircle className="w-4 h-4 mr-1.5" />
              {t('scheduledTask.cancel')}
            </Button>
          )}
          {!isSystemTask(task) && (
            <Button
              variant="outline"
              size="sm"
              disabled={!canDelete(task.status) || isMutating}
              onClick={() => setPendingAction('delete')}
            >
              <Trash2 className="w-4 h-4 mr-1.5" />
              {t('scheduledTask.delete')}
            </Button>
          )}
        </div>
      </div>

      {originThreadId && (
        <div className="rounded-lg border bg-muted/20 p-3 text-sm">
          {t('scheduledTask.sourceSessionLabel')}:
          <Link
            to={`/workbench/${originThreadId}`}
            className="ml-2 underline underline-offset-2 hover:text-foreground"
          >
            {originThreadId}
          </Link>
        </div>
      )}

      {task.error_message && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {task.error_message}
        </div>
      )}

      <div className="rounded-lg border p-4 space-y-3">
        <p className="text-sm font-medium">{t('scheduledTask.taskDetails')}</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-muted-foreground">Task ID:</span> {task.id}
          </div>
          <div>
            <span className="text-muted-foreground">{t('scheduledTask.statusLabel')}:</span> {task.status}
          </div>
          <div>
            <span className="text-muted-foreground">{t('scheduledTask.taskTypeLabel')}:</span> {task.task_type}
          </div>
          <div>
            <span className="text-muted-foreground">{t('scheduledTask.scheduleTypeLabel')}:</span> {task.schedule_type}
          </div>
          <div>
            <span className="text-muted-foreground">{t('scheduledTask.createdAtLabel')}:</span> {formatDate(task.created_at)}
          </div>
          <div>
            <span className="text-muted-foreground">{t('scheduledTask.updatedAtLabel')}:</span> {formatDate(task.updated_at)}
          </div>
          <div>
            <span className="text-muted-foreground">{t('scheduledTask.nextRunAtLabel')}:</span> {formatDate(task.next_run_at)}
          </div>
          <div>
            <span className="text-muted-foreground">{t('scheduledTask.lastRunAtLabel')}:</span> {formatDate(task.last_run_at)}
          </div>
        </div>

        <div>
          <p className="text-xs text-muted-foreground mb-1">{t('scheduledTask.notifyChannels')}</p>
          {task.notification_channels && task.notification_channels.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {task.notification_channels.map((channel) => (
                <Badge key={channel} variant="outline">
                  {channel}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('scheduledTask.defaultChannel')}</p>
          )}
        </div>

        <div>
          <p className="text-xs text-muted-foreground mb-1">schedule_spec</p>
          <pre className="rounded-md border bg-muted/20 p-3 text-xs overflow-x-auto">
            {JSON.stringify(task.schedule_spec ?? {}, null, 2)}
          </pre>
        </div>

        <div>
          <p className="text-xs text-muted-foreground mb-1">task_config</p>
          <pre className="rounded-md border bg-muted/20 p-3 text-xs overflow-x-auto">
            {JSON.stringify(task.task_config ?? {}, null, 2)}
          </pre>
        </div>
      </div>

      <div className="rounded-lg border p-4">
        <p className="text-sm font-medium mb-3">{t('scheduledTask.execRecords')}</p>
        {runsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">{t('scheduledTask.execRecordsLoading')}</p>
        ) : runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('scheduledTask.noExecRecords')}</p>
        ) : (
          <div className="space-y-3">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[100px]">ID</TableHead>
                  <TableHead>{t('scheduledTask.execStatusCol')}</TableHead>
                  <TableHead>{t('scheduledTask.execStartCol')}</TableHead>
                  <TableHead>{t('scheduledTask.execEndCol')}</TableHead>
                  <TableHead>{t('scheduledTask.execDurationCol')}</TableHead>
                  <TableHead className="w-[150px]">{t('scheduledTask.execActionsCol')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="font-medium">#{run.id}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={getScheduledTaskStatusClass(run.status)}>
                        {run.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatDate(run.started_at)}</TableCell>
                    <TableCell>{run.finished_at ? formatDate(run.finished_at) : '—'}</TableCell>
                    <TableCell>{formatDuration(run.duration_ms)}</TableCell>
                    <TableCell className="flex items-center gap-1.5">
                      {run.result?.has_logs && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs"
                          onClick={() => setViewingLogRun(run)}
                        >
                          <FileText className="w-3.5 h-3.5 mr-1" />
                          日志
                        </Button>
                      )}
                      <details>
                        <summary className="text-xs text-muted-foreground cursor-pointer">
                          {t('scheduledTask.viewDetails')}
                        </summary>
                        <div className="mt-2 space-y-2 text-xs">
                          {run.error_message && (
                            <div className="text-destructive">{run.error_message}</div>
                          )}
                          <pre className="rounded-md border bg-muted/20 p-2 overflow-x-auto">
                            {JSON.stringify(run.result?.data ?? {}, null, 2)}
                          </pre>
                        </div>
                      </details>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <PaginationBar
              page={runsPage}
              pageSize={runsPageSize}
              total={totalRuns}
              totalPages={totalPages}
              onPageChange={setRunsPage}
              showWhenSinglePage={false}
            />
          </div>
        )}
      </div>

      <ConfirmationDialog
        open={pendingAction === 'run'}
        item={task}
        isLoading={runMutation.isPending}
        title={t('scheduledTask.confirmRunTitle')}
        description={(item) => t('scheduledTask.confirmRun', { name: item.name })}
        confirmText={t('scheduledTask.confirmRunTitle')}
        onConfirm={handleRun}
        onCancel={() => setPendingAction(null)}
      />
      <ConfirmationDialog
        open={pendingAction === 'cancel'}
        item={task}
        isLoading={cancelMutation.isPending}
        title={t('scheduledTask.confirmCancelTitle')}
        description={(item) => t('scheduledTask.confirmCancel', { name: item.name })}
        confirmText={t('scheduledTask.cancel')}
        isDangerous
        onConfirm={handleCancel}
        onCancel={() => setPendingAction(null)}
      />
      <ConfirmationDialog
        open={pendingAction === 'delete'}
        item={task}
        isLoading={deleteMutation.isPending}
        title={t('scheduledTask.confirmDeleteTitle')}
        description={(item) => t('scheduledTask.confirmDelete', { name: item.name })}
        confirmText={t('scheduledTask.delete')}
        isDangerous
        onConfirm={handleDelete}
        onCancel={() => setPendingAction(null)}
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

      {viewingLogRun && id && (
        <TaskRunLogDialog taskId={id} run={viewingLogRun} onClose={() => setViewingLogRun(null)} />
      )}
    </div>
  )
}
