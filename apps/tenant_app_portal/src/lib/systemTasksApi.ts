import api from './api'
import type { LogStream, ScheduledTask, ScheduledTaskRunsResponse } from './scheduledTasksApi'

export type { LogStream, ScheduledTask, ScheduledTaskRunsResponse }

export interface ListSystemTasksParams {
  status?: string
  task_type?: string
  limit?: number
  offset?: number
}

export async function listSystemTasks(params?: ListSystemTasksParams): Promise<ScheduledTask[]> {
  const response = await api.get<ScheduledTask[]>('/admin/system-tasks', { params })
  return response.data
}

export async function getSystemTask(taskId: number): Promise<ScheduledTask> {
  const response = await api.get<ScheduledTask>(`/admin/system-tasks/${taskId}`)
  return response.data
}

export async function listSystemTaskRuns(
  taskId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<ScheduledTaskRunsResponse> {
  const response = await api.get<ScheduledTaskRunsResponse>(`/admin/system-tasks/${taskId}/runs`, {
    params: { page, page_size: pageSize },
  })
  return response.data
}

export async function pauseSystemTask(taskId: number): Promise<void> {
  await api.patch(`/admin/system-tasks/${taskId}/pause`)
}

export async function resumeSystemTask(taskId: number): Promise<void> {
  await api.patch(`/admin/system-tasks/${taskId}/resume`)
}

export async function runSystemTask(taskId: number): Promise<void> {
  await api.patch(`/admin/system-tasks/${taskId}/run`)
}

export async function getSystemTaskRunLogs(
  taskId: number,
  runId: number,
  stream: LogStream
): Promise<string> {
  const response = await api.get<string>(`/admin/system-tasks/${taskId}/runs/${runId}/logs`, {
    params: { stream },
    responseType: 'text',
    transformResponse: [(data: string) => data],
  })
  return response.data
}
