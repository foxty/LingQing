import { Alert, AlertDescription } from '@/components/ui/alert'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useTranslation } from 'react-i18next'

export default function ResetUserPasswordDialog({
  open,
  onOpenChange,
  loading,
  value,
  onValueChange,
  fieldError,
  formError,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  loading: boolean
  value: string
  onValueChange: (value: string) => void
  fieldError: string | undefined
  formError: string | null
  onSubmit: () => void
}) {
  const { t } = useTranslation()

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('settings.usersTab.resetPasswordDialog.title')}</AlertDialogTitle>
          <AlertDialogDescription>{t('settings.usersTab.resetPasswordDialog.description')}</AlertDialogDescription>
        </AlertDialogHeader>
        {formError ? (
          <Alert variant="destructive">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}
        <div className="space-y-2">
          <Label htmlFor="reset-password">{t('settings.usersTab.resetPasswordDialog.newPassword')}</Label>
          <p className="text-xs text-muted-foreground">{t('settings.usersTab.resetPasswordDialog.passwordRequirements')}</p>
          <Input
            id="reset-password"
            type="password"
            value={value}
            onChange={(event) => onValueChange(event.target.value)}
            autoComplete="new-password"
            errorMsg={fieldError}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              event.preventDefault()
              onSubmit()
            }}
            disabled={loading}
          >
            {t('settings.usersTab.resetPasswordDialog.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
