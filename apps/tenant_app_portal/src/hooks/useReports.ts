import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useNotification } from '@/hooks/useNotification'
import { deleteReport, getReport, listReports, type Report } from '@/lib/reportsApi'
import i18n from '@/i18n/config'

export function useReports() {
  return useQuery<Report[]>({
    queryKey: ['reports'],
    queryFn: () => listReports(),
  })
}

export function useReportDetail(id: number | null) {
  return useQuery<Report>({
    queryKey: ['report-detail', id],
    queryFn: async () => {
      if (!id) throw new Error('Invalid report id')
      return getReport(id)
    },
    enabled: !!id,
  })
}

export function useDeleteReport() {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useNotification()

  return useMutation({
    mutationFn: async (reportId: number) => deleteReport(reportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      showSuccess(i18n.t('common.deleteSuccess'))
    },
    onError: () => {
      showError(i18n.t('dashboards.deleteFailed'))
    },
  })
}
