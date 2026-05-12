import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Alert, AlertDescription } from '@/components/ui/alert'

i18n.addResourceBundle('en', 'translation', {
  components: {
    uploadProgress: {
      success: 'Uploaded',
      duplicate: 'Duplicate',
      failed: 'Failed',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    uploadProgress: {
      success: '上传成功',
      duplicate: '重复文件',
      failed: '上传失败',
    },
  },
}, true, true)
import { Progress } from '@/components/ui/progress'
import { AlertCircle, CheckCircle, Upload } from 'lucide-react'
import type { UploadProgress } from '@/hooks/useFileUpload'

interface UploadProgressNotificationsProps {
  items: UploadProgress[]
}

/**
 * Displays upload progress notifications for multiple files
 */
export function UploadProgressNotifications({ items }: UploadProgressNotificationsProps) {
  const { t } = useTranslation()
  if (items.length === 0) {
    return null
  }

  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <Alert
          key={index}
          variant={item.status === 'error' ? 'destructive' : 'default'}
          className="py-3"
        >
          <div className="flex items-start gap-3 w-full">
            {item.status === 'success' ? (
              <CheckCircle className="h-4 w-4 mt-0.5 flex-shrink-0 text-green-500" />
            ) : item.status === 'duplicate' ? (
              <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-500" />
            ) : item.status === 'error' ? (
              <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
            ) : (
              <Upload className="h-4 w-4 mt-0.5 flex-shrink-0 animate-pulse" />
            )}
            <div className="flex-1 space-y-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <AlertDescription className="font-medium truncate">
                  {item.fileName}
                </AlertDescription>
                <span className="text-xs text-muted-foreground flex-shrink-0">
                  {item.status === 'uploading' && `${item.progress}%`}
                  {item.status === 'success' && `✓ ${t('components.uploadProgress.success')}`}
                  {item.status === 'duplicate' && `⚠ ${t('components.uploadProgress.duplicate')}`}
                  {item.status === 'error' && `✗ ${t('components.uploadProgress.failed')}`}
                </span>
              </div>
              {item.status === 'uploading' && <Progress value={item.progress} className="h-1" />}
              {item.error && <p className="text-xs text-muted-foreground">{item.error}</p>}
            </div>
          </div>
        </Alert>
      ))}
    </div>
  )
}
