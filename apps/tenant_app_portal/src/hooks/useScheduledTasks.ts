import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import i18n from '@/i18n/config'

import { useNotification } from '@/hooks/useNotification'
import {
  cancelScheduledTask,
  deleteScheduledTask,
  getScheduledTask,
  getTaskRunLogs,
  listScheduledTaskRuns,
  listScheduledTasks,
  pauseScheduledTask,
  resumeScheduledTask,
  runScheduledTask,
  type LogStream,
  type ScheduledTask
} from '@/lib/scheduledTasksApi'

export function useScheduledTasks(taskStatus?: string) {
  return useQuery<ScheduledTask[]>({
    queryKey: ['scheduled-tasks', taskStatus],
    queryFn: () => listScheduledTasks({ status: taskStatus, limit: 200 }),
  })
}

export function useScheduledTaskDetail(taskId: number | null) {
  return useQuery<ScheduledTask>({
    queryKey: ['scheduled-task-detail', taskId],
    queryFn: () => {
      if (!taskId) {
        throw new Error('Invalid scheduled task id')
      }
      return getScheduledTask(taskId)
    },
    enabled: !!taskId,
  })
}

export function useScheduledTaskRuns(taskId: number | null, page: number = 1, pageSize: number = 20) {
  return useQuery({
    queryKey: ['scheduled-task-runs', taskId, page, pageSize],
    queryFn: () => {
      if (!taskId) {
        throw new Error('Invalid scheduled task id')
      }
      return listScheduledTaskRuns(taskId, page, pageSize)
    },
    enabled: !!taskId,
  })
}

function invalidateScheduledTaskQueries(queryClient: ReturnType<typeof useQueryClient>, taskId?: number) {
  queryClient.invalidateQueries({ queryKey: ['scheduled-tasks'] })
  if (taskId) {
    queryClient.invalidateQueries({ queryKey: ['scheduled-task-detail', taskId] })
    queryClient.invalidateQueries({ queryKey: ['scheduled-task-runs', taskId] })
  }
}

export function usePauseScheduledTask() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (taskId: number) => pauseScheduledTask(taskId),
    onSuccess: (_data, taskId) => {
      invalidateScheduledTaskQueries(queryClient, taskId)
      showSuccess(i18n.t('common.updateSuccess'))
    },
    onError: () => showError(i18n.t('common.failedToLoad')),
  })
}

export function useResumeScheduledTask() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (taskId: number) => resumeScheduledTask(taskId),
    onSuccess: (_data, taskId) => {
      invalidateScheduledTaskQueries(queryClient, taskId)
      showSuccess(i18n.t('common.updateSuccess'))
    },
    onError: () => showError(i18n.t('common.failedToLoad')),
  })
}

export function useCancelScheduledTask() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (taskId: number) => cancelScheduledTask(taskId),
    onSuccess: (_data, taskId) => {
      invalidateScheduledTaskQueries(queryClient, taskId)
      showSuccess(i18n.t('common.updateSuccess'))
    },
    onError: () => showError(i18n.t('common.failedToLoad')),
  })
}

export function useDeleteScheduledTask() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (taskId: number) => deleteScheduledTask(taskId),
    onSuccess: (_data, taskId) => {
      invalidateScheduledTaskQueries(queryClient, taskId)
      showSuccess(i18n.t('common.deleteSuccess'))
    },
    onError: () => showError(i18n.t('common.failedToLoad')),
  })
}

export function useRunScheduledTask() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: (taskId: number) => runScheduledTask(taskId),
    onSuccess: (_data, taskId) => {
      invalidateScheduledTaskQueries(queryClient, taskId)
      showSuccess('任务已开始执行')
    },
    onError: () => showError('立即执行失败，请重试'),
  })
}

export function useTaskRunLogs(taskId: number | null, runId: number | null, stream: LogStream) {
  return useQuery({
    queryKey: ['task-run-logs', taskId, runId, stream],
    queryFn: () => {
      if (!taskId || !runId) throw new Error('Invalid taskId or runId')
      return getTaskRunLogs(taskId, runId, stream)
    },
    enabled: !!taskId && !!runId,
    retry: false,
  })
}
