import { useEffect, useRef, useState } from 'react'
import { syncApiConnectorPack } from '@/lib/apiConnectorApi'
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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
import { PackagePlus } from 'lucide-react'

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
  const [syncingPack, setSyncingPack] = useState(false)
  const [showPackUpdateConfirm, setShowPackUpdateConfirm] = useState(false)
  const showPackUpdate =
    mode === 'edit' &&
    Boolean(connector?.pack_update_available && connector?.can_write && connector.pack_ref)
  const installedPackVersionLabel =
    connector?.installed_pack_version?.trim() ||
    t('components.addApiConnectorDialog.packUpdateInstalledUnknown')
  const catalogPackVersionLabel = connector?.pack_catalog_version?.trim() || '—'
  const submitErrorRef = useRef<HTMLDivElement>(null)

  const form = useApiConnectorForm({ open, connector, mode })

  useEffect(() => {
    if (!form.submitError) return
    submitErrorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [form.submitError])

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

  const handlePackSync = async () => {
    if (!connector || syncingPack) return
    try {
      setSyncingPack(true)
      form.setSubmitError(null)
      const result = await syncApiConnectorPack(connector.id)
      showSuccess(t('components.addApiConnectorDialog.packUpdateSuccess'))
      if (result.summary.scopes_expanded) {
        showSuccess(t('components.addApiConnectorDialog.packUpdateReconnect'))
      }
      onUpdated?.(result.connector)
      setShowPackUpdateConfirm(false)
    } catch (err: unknown) {
      form.setSubmitError(
        getApiErrorMessage(err, t('components.addApiConnectorDialog.submitFailed'))
      )
    } finally {
      setSyncingPack(false)
    }
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
            {showPackUpdate ? (
              <Alert
                variant="default"
                className="border-primary bg-primary/5 text-foreground ring-1 ring-primary/25 [&>svg]:text-primary"
              >
                <PackagePlus className="h-4 w-4" aria-hidden />
                <AlertTitle>{t('components.addApiConnectorDialog.packUpdateTitle')}</AlertTitle>
                <AlertDescription className="space-y-3">
                  <p>
                    {t('components.addApiConnectorDialog.packUpdateAvailable', {
                      catalog: catalogPackVersionLabel,
                      installed: installedPackVersionLabel,
                    })}
                  </p>
                  <Button
                    type="button"
                    variant="default"
                    size="sm"
                    disabled={syncingPack || submitting}
                    onClick={() => setShowPackUpdateConfirm(true)}
                  >
                    {syncingPack
                      ? t('components.addApiConnectorDialog.packUpdateApplying')
                      : t('components.addApiConnectorDialog.packUpdateApply')}
                  </Button>
                </AlertDescription>
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
                oauthScopeSuggestions={form.oauthScopeSuggestions}
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

          <DialogFooter className="gap-3 sm:flex-col sm:items-stretch sm:space-x-0">
            {form.submitError ? (
              <Alert ref={submitErrorRef} variant="destructive" className="text-left">
                <AlertDescription>{form.submitError}</AlertDescription>
              </Alert>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
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
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={showPackUpdateConfirm} onOpenChange={setShowPackUpdateConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('components.addApiConnectorDialog.packUpdateConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('components.addApiConnectorDialog.packUpdateConfirmDesc', {
                catalog: catalogPackVersionLabel,
                installed: installedPackVersionLabel,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={syncingPack}>
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={syncingPack}
              onClick={(event) => {
                event.preventDefault()
                void handlePackSync()
              }}
            >
              {syncingPack
                ? t('components.addApiConnectorDialog.packUpdateApplying')
                : t('components.addApiConnectorDialog.packUpdateConfirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
