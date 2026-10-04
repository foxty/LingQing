import { useCallback } from 'react'
import { toast } from 'sonner'

export type NotificationType = 'success' | 'error' | 'info' | 'warning'

export interface Notification {
  id: string
  type: NotificationType
  message: string
}

const DEFAULT_DURATIONS: Record<NotificationType, number> = {
  success: 3000,
  error: 5000,
  info: 3000,
  warning: 4000,
}

/**
 * Transient user feedback via Sonner. For channel selection rules see DESIGN.md §5.
 * Do not import `sonner` directly in pages or feature hooks.
 */
export function useNotification() {
  const showNotification = useCallback((
    type: NotificationType,
    message: string,
    duration?: number
  ) => {
    const resolvedDuration = duration ?? DEFAULT_DURATIONS[type]
    switch (type) {
      case 'success':
        return toast.success(message, { duration: resolvedDuration })
      case 'error':
        return toast.error(message, { duration: resolvedDuration })
      case 'info':
        return toast.info(message, { duration: resolvedDuration })
      case 'warning':
        return toast.warning(message, { duration: resolvedDuration })
      default:
        return toast(message, { duration: resolvedDuration })
    }
  }, [])

  const showSuccess = useCallback((message: string, duration?: number) => {
    return toast.success(message, { duration: duration ?? DEFAULT_DURATIONS.success })
  }, [])

  const showError = useCallback((message: string, duration?: number) => {
    return toast.error(message, { duration: duration ?? DEFAULT_DURATIONS.error })
  }, [])

  const showInfo = useCallback((message: string, duration?: number) => {
    return toast.info(message, { duration: duration ?? DEFAULT_DURATIONS.info })
  }, [])

  const showWarning = useCallback((message: string, duration?: number) => {
    return toast.warning(message, { duration: duration ?? DEFAULT_DURATIONS.warning })
  }, [])

  const dismissNotification = useCallback((id: string | number) => {
    toast.dismiss(id)
  }, [])

  return {
    showNotification,
    showSuccess,
    showError,
    showInfo,
    showWarning,
    dismissNotification,
  }
}
