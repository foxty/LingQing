import { useQuery } from '@tanstack/react-query'
import { exportFeedbackCsv, getFeedbackStats, listFeedback } from '@/lib/feedbackApi'

export function useFeedbackStats(params?: {
  agent_id?: number
  source?: string
  from?: string
  to?: string
}) {
  return useQuery({
    queryKey: ['feedbackStats', params],
    queryFn: () => getFeedbackStats(params),
  })
}

export function useFeedbackList(params?: {
  agent_id?: number
  rating?: string
  source?: string
  from?: string
  to?: string
  cursor?: number
  limit?: number
}) {
  return useQuery({
    queryKey: ['feedbackList', params],
    queryFn: () => listFeedback(params),
  })
}

export async function downloadFeedbackExport(params?: {
  agent_id?: number
  rating?: string
  source?: string
  from?: string
  to?: string
}) {
  const blob = await exportFeedbackCsv(params)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'message_feedback.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}
