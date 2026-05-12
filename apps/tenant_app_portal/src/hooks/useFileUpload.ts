import { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from './useAuth'
import api, { getApiErrorMessage } from '@/lib/api'
import { isValidFileType, SUPPORTED_DOCUMENT_TYPES_DESCRIPTION } from '@/constants/documents'
import i18n from '@/i18n/config'

export interface UploadProgress {
  fileName: string
  progress: number
  status: 'uploading' | 'success' | 'error' | 'duplicate'
  error?: string
}

/**
 * Custom hook for handling file uploads with progress tracking and validation
 */
export function useFileUpload(collectionId?: number) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<UploadProgress[]>([])

  const handleFileUpload = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = event.target.files
      if (!files || files.length === 0) return

      // Validate file types before uploading
      const invalidFiles = Array.from(files).filter((file) => !isValidFileType(file.name))
      if (invalidFiles.length > 0) {
        const errorItems: UploadProgress[] = invalidFiles.map((file) => ({
          fileName: file.name,
          progress: 0,
          status: 'error' as const,
          error: i18n.t('components.csvUploadDialog.unsupportedType', { types: SUPPORTED_DOCUMENT_TYPES_DESCRIPTION }),
        }))
        setUploadProgress(errorItems)

        // Clear error messages after 5 seconds
        setTimeout(() => {
          setUploadProgress([])
        }, 5000)

        // Reset input
        event.target.value = ''
        return
      }

      if (!collectionId) return

      setUploading(true)

      // Initialize progress for each file
      const initialProgress: UploadProgress[] = Array.from(files).map((file) => ({
        fileName: file.name,
        progress: 0,
        status: 'uploading' as const,
      }))
      setUploadProgress(initialProgress)

      // Upload files one by one with progress updates
      for (let i = 0; i < files.length; i++) {
        const file = files[i]

        try {
          // Update to uploading
          setUploadProgress((prev) =>
            prev.map((item, idx) =>
              idx === i ? { ...item, progress: 50, status: 'uploading' } : item
            )
          )

          const formData = new FormData()
          formData.append('file', file)
          formData.append('collection_id', String(collectionId))

          await api.post('/documents/upload', formData, {
            headers: {
              'Content-Type': 'multipart/form-data',
            },
          })

          // Mark as success
          setUploadProgress((prev) =>
            prev.map((item, idx) =>
              idx === i ? { ...item, progress: 100, status: 'success' } : item
            )
          )
        } catch (error: unknown) {
          const axiosError = error as {
            response?: { status?: number; data?: { code?: string } }
            apiError?: { code?: string }
          }
          const isDuplicate = axiosError.response?.status === 409
          const isTooLarge =
            axiosError.response?.status === 413 ||
            axiosError.apiError?.code === 'PAYLOAD_TOO_LARGE' ||
            axiosError.response?.data?.code === 'PAYLOAD_TOO_LARGE'
          const errorMsg = getApiErrorMessage(
            error,
            isTooLarge
              ? i18n.t('knowledgeBase.fileTooLarge')
              : i18n.t('components.csvUploadDialog.uploadFailed')
          )

          setUploadProgress((prev) =>
            prev.map((item, idx) =>
              idx === i
                ? {
                    ...item,
                    progress: 0,
                    status: isDuplicate ? 'duplicate' : 'error',
                    error: errorMsg,
                  }
                : item
            )
          )
          console.error(`Failed to upload ${file.name}:`, error)
        }
      }

      setUploading(false)
      event.target.value = ''

      // Refresh document list to show newly uploaded documents
      queryClient.invalidateQueries({ queryKey: ['documents', user?.tenantId] })

      setTimeout(() => {
        setUploadProgress([])
      }, 3000)
    },
    [user?.tenantId, queryClient, collectionId]
  )

  return {
    uploading,
    uploadProgress,
    handleFileUpload,
  }
}
