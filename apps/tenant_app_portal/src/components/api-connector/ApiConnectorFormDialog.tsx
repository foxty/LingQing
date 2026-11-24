import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import '@/components/api-connector/formI18n'
import { AuthSection } from '@/components/api-connector/AuthSection'
import { IdentitySection } from '@/components/api-connector/IdentitySection'
import { SchemaSection } from '@/components/api-connector/SchemaSection'
import type { ApiConnectorFormDialogProps } from '@/components/api-connector/types'
import { useApiConnectorForm } from '@/components/api-connector/useApiConnectorForm'
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
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useNotification } from '@/hooks/useNotification'
import { getApiErrorMessage } from '@/lib/api'

export function ApiConnectorFormDialog({
  open,
  submitting = false,
  connector,
  onOpenChange,
  onCreate,
  onUpdate,
  onCreated,
  onUpdated,
}: ApiConnectorFormDialogProps) {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()
  const mode: 'create' | 'edit' = connector && onUpdate ? 'edit' : 'create'
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)

  const form = useApiConnectorForm({ open, connector, mode })

  const closeWithoutConfirm = () => {
    setShowCloseConfirm(false)
    onOpenChange(false)
    form.resetForm()
  }

  const closeWithConfirm = () => {
    if (submitting) return
    if (form.hasUnsavedData()) {
      setShowCloseConfirm(true)
      return
    }
    closeWithoutConfirm()
  }

  const handleSubmit = async () => {
    if (!form.validateBeforeSubmit()) return

    try {
      form.setSubmitError(null)
      if (mode === 'edit' && connector && onUpdate) {
        const updated = await onUpdate(connector.id, form.buildUpdatePayload())
        showSuccess(t('components.addApiConnectorDialog.updateSuccess'))
        onUpdated?.(updated)
      } else {
        if (!onCreate) {
          showError(t('common.failedToLoad'))
          return
        }
        const created = await onCreate(form.buildCreatePayload())
        showSuccess(t('components.addApiConnectorDialog.createSuccess'))
        onCreated?.(created)
      }
      closeWithoutConfirm()
    } catch (err: unknown) {
      form.setSubmitError(
        getApiErrorMessage(err, t('components.addApiConnectorDialog.submitFailed'))
      )
    }
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (nextOpen) {
            onOpenChange(true)
            return
          }
          closeWithConfirm()
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[780px]">
          <DialogHeader>
            <DialogTitle className="flex flex-wrap items-center gap-2">
              <span>
                {mode === 'edit'
                  ? t('components.addApiConnectorDialog.editTitle')
                  : t('components.addApiConnectorDialog.title')}
              </span>
              {connector?.pack_ref ? (
                <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
                  {connector.pack_ref}
                </span>
              ) : null}
            </DialogTitle>
            <DialogDescription>
              {t('components.addApiConnectorDialog.dialogDescription')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {form.submitError ? (
              <Alert variant="destructive">
                <AlertDescription>{form.submitError}</AlertDescription>
              </Alert>
            ) : null}
            <div className="divide-y divide-border">
              <IdentitySection
                submitting={submitting}
                packLocked={form.packLocked}
                credentialModeLocked={form.credentialModeLocked}
                name={form.name}
                baseUrl={form.baseUrl}
                description={form.description}
                credentialMode={form.credentialMode}
                fieldErrors={form.fieldErrors}
                onNameChange={form.setName}
                onBaseUrlChange={form.setBaseUrl}
                onDescriptionChange={form.setDescription}
                onCredentialModeChange={form.setCredentialMode}
                clearFieldError={form.clearFieldError}
              />
              <AuthSection
                submitting={submitting}
                packLocked={form.packLocked}
                isAuthConfigured={form.isAuthConfigured}
                authType={form.authType}
                maskedAuth={form.maskedAuth}
                apiKeyConfig={form.apiKeyConfig}
                basicConfig={form.basicConfig}
                customAuthConfig={form.customAuthConfig}
                oauth2Config={form.oauth2Config}
                scopesText={form.scopesText}
                fieldErrors={form.fieldErrors}
                apiKeyValueSecret={form.apiKeyValueSecret}
                bearerSecret={form.bearerSecret}
                basicPasswordSecret={form.basicPasswordSecret}
                oauthClientSecret={form.oauthClientSecret}
                onAuthTypeChange={form.setAuthType}
                onApiKeyConfigChange={form.setApiKeyConfig}
                onBasicConfigChange={form.setBasicConfig}
                onCustomAuthConfigChange={form.setCustomAuthConfig}
                onOauth2ConfigChange={form.setOauth2Config}
                onScopesTextChange={form.setScopesText}
                clearFieldError={form.clearFieldError}
              />
              <SchemaSection
                submitting={submitting}
                schemaSourceType={form.schemaSourceType}
                schemaSourceUrl={form.schemaSourceUrl}
                fieldErrors={form.fieldErrors}
                onSchemaSourceTypeChange={form.setSchemaSourceType}
                onSchemaSourceUrlChange={form.setSchemaSourceUrl}
                clearFieldError={form.clearFieldError}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeWithConfirm} disabled={submitting}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting
                ? t('components.addApiConnectorDialog.saving')
                : mode === 'edit'
                  ? t('common.saveChanges')
                  : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('components.addApiConnectorDialog.cancelConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('components.addApiConnectorDialog.cancelConfirmDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('components.addApiConnectorDialog.continueEditing')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={closeWithoutConfirm}
              className={buttonVariants({ variant: 'destructive' })}
            >
              {t('components.addApiConnectorDialog.discard')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
