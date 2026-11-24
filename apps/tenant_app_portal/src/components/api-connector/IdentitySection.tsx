import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { FieldErrorKey } from '@/components/api-connector/types'

interface IdentitySectionProps {
  submitting: boolean
  packLocked: boolean
  credentialModeLocked: boolean
  name: string
  baseUrl: string
  description: string
  credentialMode: 'shared' | 'user'
  fieldErrors: Partial<Record<FieldErrorKey, string>>
  onNameChange: (value: string) => void
  onBaseUrlChange: (value: string) => void
  onDescriptionChange: (value: string) => void
  onCredentialModeChange: (value: 'shared' | 'user') => void
  clearFieldError: (key: FieldErrorKey) => void
}

export function IdentitySection({
  submitting,
  packLocked,
  credentialModeLocked,
  name,
  baseUrl,
  description,
  credentialMode,
  fieldErrors,
  onNameChange,
  onBaseUrlChange,
  onDescriptionChange,
  onCredentialModeChange,
  clearFieldError,
}: IdentitySectionProps) {
  const { t } = useTranslation()

  return (
    <section className="space-y-3 py-4 first:pt-0">
      <h3 className="text-sm font-semibold tracking-tight">
        {t('components.addApiConnectorDialog.basicInfo')}
      </h3>
      <div className="space-y-3 border-l-2 border-border pl-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="add-connector-name">{t('components.addApiConnectorDialog.name')}</Label>
            <Input
              id="add-connector-name"
              value={name}
              onChange={(e) => {
                onNameChange(e.target.value)
                clearFieldError('name')
              }}
              placeholder="orders-api"
              disabled={submitting}
              errorMsg={fieldErrors.name}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="add-connector-base-url">
              {t('components.addApiConnectorDialog.baseUrl')}
            </Label>
            {packLocked ? (
              <>
                <p className="break-all text-sm text-muted-foreground">{baseUrl || '—'}</p>
                <p className="text-xs text-muted-foreground">
                  {t('components.addApiConnectorDialog.packLockedHint')}
                </p>
              </>
            ) : (
              <Input
                id="add-connector-base-url"
                value={baseUrl}
                onChange={(e) => {
                  onBaseUrlChange(e.target.value)
                  clearFieldError('baseUrl')
                }}
                placeholder="https://api.example.com"
                disabled={submitting}
                errorMsg={fieldErrors.baseUrl}
              />
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="add-connector-credential-mode">
              {t('components.addApiConnectorDialog.credentialMode')}
            </Label>
            {credentialModeLocked ? (
              <>
                <p className="text-sm text-muted-foreground">
                  {credentialMode === 'user'
                    ? t('components.addApiConnectorDialog.credentialModeUser')
                    : t('components.addApiConnectorDialog.credentialModeShared')}
                </p>
                {!packLocked ? (
                  <p className="text-xs text-muted-foreground">
                    {t('components.addApiConnectorDialog.credentialModeOauthLocked')}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {t('components.addApiConnectorDialog.packLockedHint')}
                  </p>
                )}
              </>
            ) : (
              <select
                id="add-connector-credential-mode"
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                value={credentialMode}
                onChange={(e) => onCredentialModeChange(e.target.value as 'shared' | 'user')}
                disabled={submitting}
              >
                <option value="shared">
                  {t('components.addApiConnectorDialog.credentialModeShared')}
                </option>
                <option value="user">
                  {t('components.addApiConnectorDialog.credentialModeUser')}
                </option>
              </select>
            )}
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="add-connector-description">
            {t('components.addApiConnectorDialog.description')}
          </Label>
          <Input
            id="add-connector-description"
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            placeholder={t('components.addApiConnectorDialog.descriptionPlaceholder')}
            disabled={submitting}
          />
        </div>
      </div>
    </section>
  )
}
