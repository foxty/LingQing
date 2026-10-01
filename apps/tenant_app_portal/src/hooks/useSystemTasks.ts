import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import i18n from '@/i18n/config'

import { useNotification } from '@/hooks/useNotification'
import {
  getSystemTaskRunLogs,
  listSystemTaskRuns,
  listSystemTasks,
  pauseSystemTask,
  resumeSystemTask,
  runSystemTask,
  type LogStream,
  type ScheduledTask,
} from '@/lib/systemTasksApi'

export function useSystemTasks(taskStatus?: string) {
  return useQuery<ScheduledTask[]>({
    queryKey: ['system-tasks', taskStatus],
    queryFn: () => listSystemTasks({ status: taskStatus, limit: 200 }),
  })
}

export function useSystemTaskRuns(taskId: number | null, page: number = 1, pageSize: number = 20) {
  return useQuery({
    queryKey: ['system-task-runs', taskId, page, pageSize],
    queryFn: () => {
      if (!taskId) {
        throw new Error('Invalid system task id')
      }
      return listSystemTaskRuns(taskId, page, pageSize)
    },
    enabled: !!taskId,
  })
}

function invalidateSystemTaskQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  taskId?: number
) {
  queryClient.invalidateQueries({ queryKey: ['system-tasks'] })
  if (taskId) {
    queryClient.invalidateQueries({ queryKey: ['system-task-runs', taskId] })
  }
}

export function usePauseSystemTask() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (taskId: number) => pauseSystemTask(taskId),
    onSuccess: (_data, taskId) => {
      invalidateSystemTaskQueries(queryClient, taskId)
      showSuccess(i18n.t('common.updateSuccess'))
    },
    onError: () => showError(i18n.t('common.failedToLoad')),
  })
}

export function useResumeSystemTask() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (taskId: number) => resumeSystemTask(taskId),
    onSuccess: (_data, taskId) => {
      invalidateSystemTaskQueries(queryClient, taskId)
      showSuccess(i18n.t('common.updateSuccess'))
    },
    onError: () => showError(i18n.t('common.failedToLoad')),
  })
}

export function useRunSystemTask() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (taskId: number) => runSystemTask(taskId),
    onSuccess: (_data, taskId) => {
      invalidateSystemTaskQueries(queryClient, taskId)
      showSuccess(i18n.t('systemJobs.queuedForRun'))
    },
    onError: () => showError(i18n.t('systemJobs.runFailed')),
  })
}

export function useSystemTaskRunLogs(
  taskId: number | null,
  runId: number | null,
  stream: LogStream
) {
  return useQuery({
    queryKey: ['system-task-run-logs', taskId, runId, stream],
    queryFn: () => {
      if (!taskId || !runId) throw new Error('Invalid taskId or runId')
      return getSystemTaskRunLogs(taskId, runId, stream)
    },
    enabled: !!taskId && !!runId,
    retry: false,
  })
}
