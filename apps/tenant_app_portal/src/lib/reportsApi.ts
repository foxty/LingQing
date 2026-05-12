import api from './api'

export interface Report {
  id: number
  owner_id?: number | null
  title: string
  content: string
  format: 'markdown' | 'plaintext' | 'html'
  source_thread_id?: string | null
  metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
  owner_username?: string | null
}

export async function listReports(): Promise<Report[]> {
  const response = await api.get<Report[]>('/reports')
  return response.data
}

export async function getReport(reportId: number): Promise<Report> {
  const response = await api.get<Report>(`/reports/${reportId}`)
  return response.data
}

export async function deleteReport(reportId: number): Promise<void> {
  await api.delete(`/reports/${reportId}`)
}
