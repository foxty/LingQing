import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { buttonVariants } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

i18n.addResourceBundle('en', 'translation', {
  components: {
    confirmationDialog: {
      processing: 'Processing...',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    confirmationDialog: {
      processing: '处理中...',
    },
  },
}, true, true)

export interface ConfirmationDialogProps<T> {
  open: boolean
  item: T | null
  isLoading: boolean
  title: string
  description: (item: T) => React.ReactNode
  cancelText?: string
  confirmText?: string
  isDangerous?: boolean
  onConfirm: (item: T) => Promise<void> | void
  onCancel: () => void
}

/**
 * Reusable confirmation dialog component
 * Generic to support different item types and operations
 */
export function ConfirmationDialog<T>({
  open,
  item,
  isLoading,
  title,
  description,
  cancelText,
  confirmText,
  isDangerous = false,
  onConfirm,
  onCancel,
}: ConfirmationDialogProps<T>) {
  const { t } = useTranslation()
  const cancelLabel = cancelText ?? t('common.cancel')
  const confirmLabel = confirmText ?? t('common.confirm')
  if (!item) return null

  return (
    <AlertDialog open={open} onOpenChange={onCancel}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description(item)}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              onConfirm(item)
              e.preventDefault() // Prevents dialog from closing automatically
            }}
            disabled={isLoading}
            className={isDangerous ? buttonVariants({ variant: 'destructive' }) : undefined}
          >
            {isLoading ? t('components.confirmationDialog.processing') : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
