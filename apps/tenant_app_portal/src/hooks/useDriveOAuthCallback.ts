import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'

/** Handle ?drive=connected|error after Google Drive OAuth redirect. */
export function useDriveOAuthCallback() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const { user } = useAuth()

  useEffect(() => {
    const drive = searchParams.get('drive')
    if (drive === 'connected') {
      showSuccess(t('knowledgeBase.driveConnected'))
      queryClient.invalidateQueries({ queryKey: ['document-sync', 'connections', user?.tenantId] })
      setSearchParams({}, { replace: true })
    } else if (drive === 'error') {
      showError(t('knowledgeBase.driveConnectError'))
      setSearchParams({}, { replace: true })
    }
  }, [queryClient, searchParams, setSearchParams, showError, showSuccess, t, user?.tenantId])
}
