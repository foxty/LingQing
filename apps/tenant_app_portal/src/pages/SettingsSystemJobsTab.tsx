import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
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
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import PaginationBar from '@/components/PaginationBar'
import {
  usePauseSystemTask,
  useResumeSystemTask,
  useRunSystemTask,
  useSystemTaskRuns,
  useSystemTasks,
  useSystemTaskRunLogs,
} from '@/hooks/useSystemTasks'
import { formatDate } from '@/lib/dateTime'
import type { LogStream, ScheduledTask, ScheduledTaskRun } from '@/lib/scheduledTasksApi'
import { getScheduledTaskStatusClass } from '@/lib/scheduledTaskUi'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Braces, CalendarClock, FileText, History, LayoutGrid, Pause, Play, Zap } from 'lucide-react'
import { useMemo, useState } from 'react'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    systemJobs: {
      description: 'Platform-managed background jobs for this tenant',
      noJobs: 'No system jobs found',
      loadFailed: 'Failed to load system jobs. Check your permissions and retry.',
      nameCol: 'Name',
      statusCol: 'Status',
      taskTypeCol: 'Task Type',
      scheduleCol: 'Schedule',
      nextRunCol: 'Next Run',
      lastRunCol: 'Last Run',
      actionsCol: 'Actions',
      resume: 'Resume',
      pause: 'Pause',
      runNow: 'Run now',
      viewRuns: 'View runs',
      confirmRunTitle: 'Run now',
      confirmRun: 'Run "{{name}}" immediately?',
      queuedForRun: 'Job queued for immediate execution',
      runFailed: 'Failed to trigger run, please retry',
      runsTitle: 'Execution records — {{name}} ({{total}})',
      runsLoading: 'Loading execution records...',
      noRuns: 'No execution records yet',
      execStatusCol: 'Status',
      execStartCol: 'Started',
      execEndCol: 'Finished',
      execDurationCol: 'Duration',
      execActionsCol: 'Actions',
      viewLogs: 'Logs',
      viewDetails: 'Result',
      resultTitle: 'Run result — #{{id}}',
      logsTitle: 'Execution logs — Run #{{id}}',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    systemJobs: {
      description: '平台托管的后台系统任务',
      noJobs: '暂无系统任务',
      loadFailed: '加载系统任务失败，请检查权限后重试。',
      nameCol: '名称',
      statusCol: '状态',
      taskTypeCol: '任务类型',
      scheduleCol: '调度',
      nextRunCol: '下次执行',
      lastRunCol: '上次执行',
      actionsCol: '操作',
      resume: '恢复',
      pause: '暂停',
      runNow: '立即执行',
      viewRuns: '执行记录',
      confirmRunTitle: '立即执行',
      confirmRun: '立即执行"{{name}}"？',
      queuedForRun: '任务已加入执行队列',
      runFailed: '触发执行失败，请重试',
      runsTitle: '执行记录 — {{name}} ({{total}})',
      runsLoading: '正在加载执行记录...',
      noRuns: '暂无执行记录',
      execStatusCol: '状态',
      execStartCol: '开始时间',
      execEndCol: '结束时间',
      execDurationCol: '耗时',
      execActionsCol: '操作',
      viewLogs: '日志',
      viewDetails: '结果',
      resultTitle: '执行结果 — #{{id}}',
      logsTitle: '执行日志 — Run #{{id}}',
    },
  },
  true,
  true
)

type ToggleAction = 'pause' | 'resume' | null

function getToggleAction(status: string): ToggleAction {
  if (status === 'pending' || status === 'running') return 'pause'
  if (status === 'paused') return 'resume'
  return null
}

function canRun(status: string): boolean {
  return status === 'pending' || status === 'paused'
}

function formatDuration(durationMs?: number | null): string {
  if (durationMs === null || durationMs === undefined) return '—'
  if (durationMs < 1000) return `${durationMs}ms`
  return `${(durationMs / 1000).toFixed(2)}s`
}

function hasRunResultPayload(run: ScheduledTaskRun): boolean {
  const data = run.result?.data ?? {}
  return Object.keys(data).length > 0 || Boolean(run.error_message)
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
  const { t } = useTranslation()
  const query = useSystemTaskRunLogs(taskId, runId, stream)

  if (query.isLoading) {
    return <p className="text-sm text-muted-foreground py-4">{t('common.loading')}</p>
  }
  if (query.isError) {
    return <p className="text-sm text-destructive py-4">{t('systemJobs.runFailed')}</p>
  }
  const content = (query.data ?? '').trim()
  if (!content) {
    return <p className="text-sm text-muted-foreground py-4">—</p>
  }
  return (
    <pre className="rounded-md border bg-muted/30 p-3 text-xs font-mono whitespace-pre-wrap break-all overflow-auto max-h-[60vh]">
      {content}
    </pre>
  )
}

function RunLogDialog({
  taskId,
  run,
  onClose,
}: {
  taskId: number
  run: ScheduledTaskRun
  onClose: () => void
}) {
  const { t } = useTranslation()
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('systemJobs.logsTitle', { id: run.id })}</DialogTitle>
          <DialogDescription>
            {formatDate(run.started_at)} · {formatDuration(run.duration_ms)}
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="stdout" className="flex-1 min-h-0 flex flex-col">
          <TabsList>
            <TabsTrigger value="stdout">stdout</TabsTrigger>
            <TabsTrigger value="stderr">stderr</TabsTrigger>
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

function RunResultDialog({ run, onClose }: { run: ScheduledTaskRun; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('systemJobs.resultTitle', { id: run.id })}</DialogTitle>
          <DialogDescription>
            <Badge variant="outline" className={getScheduledTaskStatusClass(run.status)}>
              {run.status}
            </Badge>
            <span className="ml-2">
              {formatDate(run.started_at)} · {formatDuration(run.duration_ms)}
            </span>
          </DialogDescription>
        </DialogHeader>
        <div className="flex-1 min-h-0 overflow-auto space-y-3">
          {run.error_message && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {run.error_message}
            </div>
          )}
          <pre className="rounded-md border bg-muted/30 p-4 text-xs font-mono overflow-auto max-h-[60vh] whitespace-pre">
            {JSON.stringify(run.result?.data ?? {}, null, 2)}
          </pre>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function RunsDialog({ task, onClose }: { task: ScheduledTask; onClose: () => void }) {
  const { t } = useTranslation()
  const [runsPage, setRunsPage] = useState(1)
  const runsPageSize = 20
  const runsQuery = useSystemTaskRuns(task.id, runsPage, runsPageSize)
  const [viewingLogRun, setViewingLogRun] = useState<ScheduledTaskRun | null>(null)
  const [viewingResultRun, setViewingResultRun] = useState<ScheduledTaskRun | null>(null)

  const runs = runsQuery.data?.items ?? []
  const totalRuns = runsQuery.data?.total ?? 0
  const totalPages = Math.ceil(totalRuns / runsPageSize)

  return (
    <>
      <Dialog open onOpenChange={(open) => !open && onClose()}>
        <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {t('systemJobs.runsTitle', { name: task.name, total: totalRuns })}
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 min-h-0 overflow-auto">
            {runsQuery.isLoading ? (
              <p className="text-sm text-muted-foreground py-4">{t('systemJobs.runsLoading')}</p>
            ) : runs.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4">{t('systemJobs.noRuns')}</p>
            ) : (
              <div className="space-y-3">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[100px]">ID</TableHead>
                      <TableHead>{t('systemJobs.execStatusCol')}</TableHead>
                      <TableHead>{t('systemJobs.execStartCol')}</TableHead>
                      <TableHead>{t('systemJobs.execEndCol')}</TableHead>
                      <TableHead>{t('systemJobs.execDurationCol')}</TableHead>
                      <TableHead className="w-[140px]">{t('systemJobs.execActionsCol')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {runs.map((run) => (
                      <TableRow key={run.id}>
                        <TableCell className="font-medium">#{run.id}</TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={getScheduledTaskStatusClass(run.status)}
                          >
                            {run.status}
                          </Badge>
                        </TableCell>
                        <TableCell>{formatDate(run.started_at)}</TableCell>
                        <TableCell>{run.finished_at ? formatDate(run.finished_at) : '—'}</TableCell>
                        <TableCell>{formatDuration(run.duration_ms)}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            {hasRunResultPayload(run) && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs"
                                onClick={() => setViewingResultRun(run)}
                              >
                                <Braces className="w-3.5 h-3.5 mr-1" />
                                {t('systemJobs.viewDetails')}
                              </Button>
                            )}
                            {run.result?.has_logs && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs"
                                onClick={() => setViewingLogRun(run)}
                              >
                                <FileText className="w-3.5 h-3.5 mr-1" />
                                {t('systemJobs.viewLogs')}
                              </Button>
                            )}
                          </div>
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
        </DialogContent>
      </Dialog>

      {viewingLogRun && (
        <RunLogDialog taskId={task.id} run={viewingLogRun} onClose={() => setViewingLogRun(null)} />
      )}
      {viewingResultRun && (
        <RunResultDialog run={viewingResultRun} onClose={() => setViewingResultRun(null)} />
      )}
    </>
  )
}

export default function SettingsSystemJobsTab() {
  const { t } = useTranslation()
  const { data: tasks = [], isLoading, isError } = useSystemTasks()
  const pauseMutation = usePauseSystemTask()
  const resumeMutation = useResumeSystemTask()
  const runMutation = useRunSystemTask()
  const [runsTask, setRunsTask] = useState<ScheduledTask | null>(null)
  const [pendingRunTask, setPendingRunTask] = useState<ScheduledTask | null>(null)

  const isMutating = pauseMutation.isPending || resumeMutation.isPending || runMutation.isPending

  const handleToggle = async (task: ScheduledTask) => {
    if (getToggleAction(task.status) === 'pause') {
      await pauseMutation.mutateAsync(task.id)
      return
    }
    await resumeMutation.mutateAsync(task.id)
  }

  const handleRun = async () => {
    if (!pendingRunTask) return
    await runMutation.mutateAsync(pendingRunTask.id)
    setPendingRunTask(null)
  }

  const sortedTasks = useMemo(
    () => [...tasks].sort((a, b) => a.name.localeCompare(b.name)),
    [tasks]
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('settings.systemJobs')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('systemJobs.description')}</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
          {t('common.loading')}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
          <LayoutGrid className="w-10 h-10 opacity-30" />
          <p className="text-sm">{t('systemJobs.loadFailed')}</p>
        </div>
      ) : sortedTasks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
          <LayoutGrid className="w-10 h-10 opacity-30" />
          <p className="text-sm">{t('systemJobs.noJobs')}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>ID</TableHead>
                <TableHead>{t('systemJobs.nameCol')}</TableHead>
                <TableHead>{t('systemJobs.statusCol')}</TableHead>
                <TableHead>{t('systemJobs.taskTypeCol')}</TableHead>
                <TableHead>{t('systemJobs.scheduleCol')}</TableHead>
                <TableHead>{t('systemJobs.nextRunCol')}</TableHead>
                <TableHead>{t('systemJobs.lastRunCol')}</TableHead>
                <TableHead className="text-right">{t('systemJobs.actionsCol')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedTasks.map((task) => (
                <TableRow key={task.id}>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {task.id}
                  </TableCell>
                  <TableCell className="max-w-[280px] font-medium">
                    <button
                      type="button"
                      className="block truncate hover:underline text-left"
                      title={t('systemJobs.viewRuns')}
                      onClick={() => setRunsTask(task)}
                    >
                      {task.name}
                    </button>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={getScheduledTaskStatusClass(task.status)}>
                      {task.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <code className="text-xs">{task.task_type}</code>
                  </TableCell>
                  <TableCell>
                    <code
                      className="inline-block rounded bg-muted px-2 py-0.5 font-mono text-xs text-foreground"
                      title="Cron format: minute hour day-of-month month day-of-week"
                    >
                      {'cron' in task.schedule_spec ? task.schedule_spec.cron : task.schedule_type}
                    </code>
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
                        title={t('systemJobs.viewRuns')}
                        onClick={() => setRunsTask(task)}
                      >
                        <History className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        title={
                          getToggleAction(task.status) === 'resume'
                            ? t('systemJobs.resume')
                            : t('systemJobs.pause')
                        }
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
                        className="h-7 w-7 p-0"
                        title={t('systemJobs.runNow')}
                        disabled={!canRun(task.status) || isMutating}
                        onClick={() => setPendingRunTask(task)}
                      >
                        <Zap className="w-3.5 h-3.5" />
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
        open={Boolean(pendingRunTask)}
        item={pendingRunTask}
        isLoading={runMutation.isPending}
        title={t('systemJobs.confirmRunTitle')}
        description={(item) => t('systemJobs.confirmRun', { name: item.name })}
        confirmText={t('systemJobs.runNow')}
        onConfirm={handleRun}
        onCancel={() => setPendingRunTask(null)}
      />

      {runsTask && <RunsDialog task={runsTask} onClose={() => setRunsTask(null)} />}
    </div>
  )
}
