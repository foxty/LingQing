import api from './api'

export interface LiveAppDeploymentState {
  dev: string | null
  test: string | null
  prod: string | null
}

export interface LiveApp {
  app_id: number
  name: string
  description: string | null
  owner_name?: string | null
  entry_file: string
  sdk_version: string
  status: string
  data_source_id: number | null
  deployment_state: LiveAppDeploymentState
  updated_at: string | null
}

export interface LiveAppListPayload {
  apps: LiveApp[]
  count: number
}

interface LiveAppsListResponse {
  data: LiveAppListPayload
}

export async function listLiveApps(): Promise<LiveApp[]> {
  const response = await api.get<LiveAppsListResponse>('/apps')
  return response.data.data.apps
}
