import { useCallback } from 'react'
import { toast } from 'sonner'

export interface Notification {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
}

/**
 * Custom hook for managing notifications using Sonner toast library
 * Follows Single Responsibility Principle
 * Provides a clean API for showing temporary notifications
 */
export function useNotification() {
  const showNotification = useCallback((
    type: Notification['type'],
    message: string,
    duration: number = 3000
  ) => {
    switch (type) {
      case 'success':
        return toast.success(message, { duration })
      case 'error':
        return toast.error(message, { duration: duration || 5000 })
      case 'info':
        return toast.info(message, { duration })
      default:
        return toast(message, { duration })
    }
  }, [])

  const showSuccess = useCallback((message: string, duration?: number) => {
    return toast.success(message, { duration })
  }, [])

  const showError = useCallback((message: string, duration?: number) => {
    return toast.error(message, { duration: duration || 5000 })
  }, [])

  const showInfo = useCallback((message: string, duration?: number) => {
    return toast.info(message, { duration })
  }, [])

  const dismissNotification = useCallback((id: string | number) => {
    toast.dismiss(id)
  }, [])

  return {
    showNotification,
    showSuccess,
    showError,
    showInfo,
    dismissNotification,
  }
}

