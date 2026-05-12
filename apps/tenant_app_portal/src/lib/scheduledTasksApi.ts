import api from './api'

export type ScheduledTaskType = 'agent_run' | 'skill_call' | 'liveapp_job' | 'system'
export type ScheduledTaskScheduleType = 'once' | 'cron'
export type ScheduledTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'cancelled'
export type ScheduledTaskRunStatus = 'running' | 'success' | 'failed'

export interface AgentRunTaskConfig {
  agent_id: number
  task_description: string
  origin_thread_id?: string
}

export interface EtlJobTaskConfig {
  job_id?: string
  params?: Record<string, unknown>
}

export interface LiveAppJobTaskConfig {
  app_id: number
  job_name: string
  entrypoint: string
  job_params?: Record<string, unknown>
  environment: string
}

export type ScheduledTaskConfig = AgentRunTaskConfig | EtlJobTaskConfig | LiveAppJobTaskConfig

export interface OnceScheduleSpec {
  run_at: string
}

export interface CronScheduleSpec {
  cron: string
  timezone?: string
}

export type ScheduledTaskScheduleSpec = OnceScheduleSpec | CronScheduleSpec

export interface ScheduledTask {
  id: number
  name: string
  owner_name?: string | null
  task_type: ScheduledTaskType
  task_config: ScheduledTaskConfig
  schedule_type: ScheduledTaskScheduleType
  schedule_spec: ScheduledTaskScheduleSpec
  status: ScheduledTaskStatus
  next_run_at: string | null
  last_run_at: string | null
  notification_channels: string[] | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface TaskRunResult {
  has_logs: boolean
  stdout_log_path: string | null
  stderr_log_path: string | null
  data: Record<string, any>
}

export interface ScheduledTaskRun {
  id: number
  status: ScheduledTaskRunStatus
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  result: TaskRunResult
  error_message: string | null
}

export interface ListScheduledTasksParams {
  status?: string
  task_type?: string
  limit?: number
  offset?: number
}

export async function listScheduledTasks(params?: ListScheduledTasksParams): Promise<ScheduledTask[]> {
  const response = await api.get<ScheduledTask[]>('/scheduled-tasks', { params })
  return response.data
}

export async function getScheduledTask(taskId: number): Promise<ScheduledTask> {
  const response = await api.get<ScheduledTask>(`/scheduled-tasks/${taskId}`)
  return response.data
}

export interface ScheduledTaskRunsResponse {
  items: ScheduledTaskRun[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export async function listScheduledTaskRuns(
  taskId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<ScheduledTaskRunsResponse> {
  const response = await api.get<ScheduledTaskRunsResponse>(`/scheduled-tasks/${taskId}/runs`, {
    params: { page, page_size: pageSize },
  })
  return response.data
}

export async function pauseScheduledTask(taskId: number): Promise<void> {
  await api.patch(`/scheduled-tasks/${taskId}/pause`)
}

export async function resumeScheduledTask(taskId: number): Promise<void> {
  await api.patch(`/scheduled-tasks/${taskId}/resume`)
}

export async function cancelScheduledTask(taskId: number): Promise<void> {
  await api.patch(`/scheduled-tasks/${taskId}/cancel`)
}

export async function deleteScheduledTask(taskId: number): Promise<void> {
  await api.delete(`/scheduled-tasks/${taskId}`)
}

export async function runScheduledTask(taskId: number): Promise<void> {
  await api.patch(`/scheduled-tasks/${taskId}/run`)
}

export type LogStream = 'stdout' | 'stderr'

export async function getTaskRunLogs(
  taskId: number,
  runId: number,
  stream: LogStream
): Promise<string> {
  const response = await api.get<string>(`/scheduled-tasks/${taskId}/runs/${runId}/logs`, {
    params: { stream },
    responseType: 'text',
    transformResponse: [(data: string) => data],
  })
  return response.data
}
