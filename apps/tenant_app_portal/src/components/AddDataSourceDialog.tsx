import '@/components/data-source/addDataSourceDialogI18n'
import AddDataSourceDialogForm from '@/components/data-source/AddDataSourceDialogForm'
import { useAddDataSourceDialog } from '@/components/data-source/useAddDataSourceDialog'
import SelectAssetsDialog from '@/components/SelectAssetsDialog'
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
import { Button, buttonVariants } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { DataSource } from '@/lib/dataSourceApi'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

interface AddDataSourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  dataSource?: DataSource | null
  onSuccess?: () => void
}

export default function AddDataSourceDialog({
  open,
  onOpenChange,
  dataSource,
  onSuccess,
}: AddDataSourceDialogProps) {
  const { t } = useTranslation()
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [savedDataSourceId, setSavedDataSourceId] = useState<number | null>(null)
  const [savedDataSourceName, setSavedDataSourceName] = useState<string>('')
  const [selectAssetsDialogOpen, setSelectAssetsDialogOpen] = useState(false)

  const dialog = useAddDataSourceDialog({
    open,
    dataSource,
    onSuccess,
    onClose: () => onOpenChange(false),
  })

  const handleClose = () => {
    if (!dialog.isSubmitting && !dialog.saving) {
      setShowCloseConfirm(false)
      onOpenChange(false)
    }
  }

  const hasUnsavedData = () => {
    const formData = dialog.watch()
    return !!(
      formData.name ||
      formData.description ||
      formData.host ||
      formData.port ||
      formData.database ||
      formData.username ||
      formData.password
    )
  }

  const handleCloseWithConfirm = () => {
    if (dialog.isSubmitting || dialog.saving) {
      return
    }
    if (hasUnsavedData()) {
      setShowCloseConfirm(true)
      return
    }
    handleClose()
  }

  const handleFormSubmit = dialog.handleSubmit(async (data) => {
    const result = await dialog.onSubmit(data)
    if (!result || result.kind === 'error') {
      return
    }
    if (result.kind === 'created') {
      setSavedDataSourceId(result.id)
      setSavedDataSourceName(result.name)
      setSelectAssetsDialogOpen(true)
    }
  })

  return (
    <>
      <Dialog open={open} onOpenChange={handleCloseWithConfirm}>
        <DialogContent className="flex max-h-[85vh] min-h-0 min-w-0 flex-col sm:max-w-[700px]">
          <DialogHeader>
            <DialogTitle>
              {dataSource
                ? t('components.addDataSourceDialog.editTitle')
                : t('components.addDataSourceDialog.title')}
            </DialogTitle>
            <DialogDescription>
              {dataSource
                ? t('components.addDataSourceDialog.editDescription', { name: dataSource.name })
                : t('components.addDataSourceDialog.createDescription')}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleFormSubmit} className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            <AddDataSourceDialogForm
              dataSource={dataSource}
              selectedType={dialog.selectedType}
              isSubmitting={dialog.isSubmitting}
              saving={dialog.saving}
              errors={dialog.errors}
              register={dialog.register}
              watch={dialog.watch}
              setValue={dialog.setValue}
              watchedCredentialMode={dialog.watchedCredentialMode}
              watchedHost={dialog.watchedHost}
              connectionFieldErrors={dialog.connectionFieldErrors}
              clearConnectionFieldErrors={dialog.clearConnectionFieldErrors}
              sharedPasswordSecret={dialog.sharedPasswordSecret}
              syncPasswordSecret={dialog.syncPasswordSecret}
              onTypeChange={dialog.handleTypeChange}
              userCredentialAuthType={dialog.userCredentialAuthType}
              onUserCredentialAuthTypeChange={(value) => {
                dialog.setUserCredentialAuthType(value)
                dialog.setUserAuthFieldErrors({})
              }}
              oauth2Config={dialog.oauth2Config}
              onOauth2ConfigChange={dialog.setOauth2Config}
              oauthClientSecret={dialog.oauthClientSecret}
              userAuthFieldErrors={dialog.userAuthFieldErrors}
              onClearUserAuthFieldError={(key) =>
                dialog.setUserAuthFieldErrors((prev) => {
                  const next = { ...prev }
                  delete next[key]
                  return next
                })
              }
            />

            <DialogFooter className="mt-3 gap-2 flex items-center justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCloseWithConfirm}
                disabled={dialog.isSubmitting || dialog.saving}
                className="h-9"
              >
                {t('common.cancel')}
              </Button>
              <Button type="submit" size="sm" disabled={dialog.isSubmitting || dialog.saving} className="h-9">
                {dialog.saving ? t('common.loading') : dataSource ? t('common.confirm') : t('common.next')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('components.addDataSourceDialog.cancelConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('components.addDataSourceDialog.cancelConfirmDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('components.addDataSourceDialog.continueEditing')}</AlertDialogCancel>
            <AlertDialogAction className={buttonVariants({ variant: 'destructive' })} onClick={handleClose}>
              {t('components.addDataSourceDialog.discard')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {savedDataSourceId !== null ? (
        <SelectAssetsDialog
          open={selectAssetsDialogOpen}
          onOpenChange={setSelectAssetsDialogOpen}
          dataSourceId={savedDataSourceId}
          dataSourceName={savedDataSourceName}
          onSuccess={() => {
            setSelectAssetsDialogOpen(false)
            handleClose()
          }}
        />
      ) : null}
    </>
  )
}