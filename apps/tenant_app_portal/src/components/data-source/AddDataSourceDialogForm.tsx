import DatabricksConnectionForm from '@/components/data-source/DatabricksConnectionForm'
import DataSourceConnectionTests from '@/components/data-source/DataSourceConnectionTests'
import DataSourceFormSectionHeader from '@/components/data-source/DataSourceFormSectionHeader'
import DataSourceUserCredentialAuthSection, {
  type DataSourceUserAuthFieldErrors,
} from '@/components/data-source/DataSourceUserCredentialAuthSection'
import type { DataSourceFormType, DataSourceFormValues } from '@/components/data-source/addDataSourceDialogModel'
import RDBMSConnectionForm from '@/components/data-source/RDBMSConnectionForm'
import {
  type DataSourceConnectionFieldErrors,
  dsFieldLabelClass,
  dsFieldPairRowClass,
  dsFieldRowClass,
  dsFieldRowStartClass,
  resolveConnectionFieldError,
} from '@/components/data-source/formLayout'
import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { DataSource } from '@/lib/dataSourceApi'
import type { OAuth2FormConfig } from '@/components/api-connector/types'
import type { DatabricksUserCredentialAuthType } from '@/lib/dataSourceUserAuth'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import { Database, InfoIcon, RefreshCw } from 'lucide-react'
import type { FieldErrors, UseFormRegister, UseFormWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export type AddDataSourceDialogFormProps = {
  dataSource?: DataSource | null
  selectedType: DataSourceFormType
  isSubmitting: boolean
  saving: boolean
  errors: FieldErrors<DataSourceFormValues>
  register: UseFormRegister<DataSourceFormValues>
  watch: UseFormWatch<DataSourceFormValues>
  setValue: (
    name: 'credentialMode',
    value: 'shared' | 'user',
    options?: { shouldDirty?: boolean },
  ) => void
  watchedCredentialMode: 'shared' | 'user'
  watchedHost: string
  connectionFieldErrors: DataSourceConnectionFieldErrors
  clearConnectionFieldErrors: () => void
  sharedPasswordSecret: SecretCredentialFieldHandle
  syncPasswordSecret: SecretCredentialFieldHandle
  onTypeChange: (type: DataSourceFormType) => void
  userCredentialAuthType: DatabricksUserCredentialAuthType
  onUserCredentialAuthTypeChange: (value: DatabricksUserCredentialAuthType) => void
  oauth2Config: OAuth2FormConfig
  onOauth2ConfigChange: (updater: (prev: OAuth2FormConfig) => OAuth2FormConfig) => void
  oauthClientSecret: SecretCredentialFieldHandle
  userAuthFieldErrors: DataSourceUserAuthFieldErrors
  onClearUserAuthFieldError: (key: keyof DataSourceUserAuthFieldErrors) => void
}

export default function AddDataSourceDialogForm({
  dataSource,
  selectedType,
  isSubmitting,
  saving,
  errors,
  register,
  watch,
  setValue,
  watchedCredentialMode,
  watchedHost,
  connectionFieldErrors,
  clearConnectionFieldErrors,
  sharedPasswordSecret,
  syncPasswordSecret,
  onTypeChange,
  userCredentialAuthType,
  onUserCredentialAuthTypeChange,
  oauth2Config,
  onOauth2ConfigChange,
  oauthClientSecret,
  userAuthFieldErrors,
  onClearUserAuthFieldError,
}: AddDataSourceDialogFormProps) {
  const { t } = useTranslation()

  return (
    <div className="min-h-0 min-w-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto overscroll-contain py-3 pl-0.5 pr-5 [scrollbar-gutter:stable]">
      <div className="grid grid-cols-3 gap-2">
        {(['postgres', 'mysql', 'databricks'] as const).map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => onTypeChange(type)}
            disabled={isSubmitting || !!dataSource}
            className={`p-2 border-2 rounded-lg text-center transition-colors ${
              selectedType === type
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/50'
            } ${isSubmitting || !!dataSource ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            <Database className="w-5 h-5 mx-auto mb-1" />
            <p className="text-xs font-medium">
              {type === 'postgres' ? 'PostgreSQL' : type === 'mysql' ? 'MySQL' : 'Databricks'}
            </p>
          </button>
        ))}
      </div>
      {dataSource ? (
        <p className="text-xs text-muted-foreground">{t('components.addDataSourceDialog.typeChangeDisabled')}</p>
      ) : null}

      <div className="space-y-2.5">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <InfoIcon className="w-4 h-4" />
          {t('components.addDataSourceDialog.basicInfo')}
        </h3>

        <div className={dsFieldRowClass}>
          <Label htmlFor="name" className={dsFieldLabelClass}>
            {t('components.addDataSourceDialog.name')} <span className="text-destructive">*</span>
          </Label>
          <Input
            id="name"
            {...register('name')}
            placeholder={t('components.addDataSourceDialog.namePlaceholder')}
            disabled={isSubmitting}
            className="h-8 text-sm w-full min-w-0"
            errorMsg={errors.name?.message as string}
          />
        </div>

        <div className={dsFieldRowClass}>
          <Label htmlFor="description" className={dsFieldLabelClass}>
            {t('components.addDataSourceDialog.description')}
          </Label>
          <Input
            id="description"
            {...register('description')}
            placeholder={t('components.addDataSourceDialog.descPlaceholder')}
            disabled={isSubmitting}
            className="h-8 text-sm w-full min-w-0"
            errorMsg={errors.description?.message as string}
          />
        </div>

        <CredentialModePicker
          isSubmitting={isSubmitting}
          watchedCredentialMode={watchedCredentialMode}
          setValue={setValue}
          register={register}
        />
      </div>

      <div className="space-y-5">
        <ConnectionSection
          selectedType={selectedType}
          watchedCredentialMode={watchedCredentialMode}
          register={register}
          errors={errors}
          connectionFieldErrors={connectionFieldErrors}
          isSubmitting={isSubmitting}
          watch={watch}
          clearConnectionFieldErrors={clearConnectionFieldErrors}
          sharedPasswordSecret={sharedPasswordSecret}
          dataSource={dataSource}
        />

        {watchedCredentialMode === 'user' ? (
          <DataSourceUserCredentialAuthSection
            dataSourceType={selectedType}
            disabled={isSubmitting}
            host={watchedHost}
            userCredentialAuthType={userCredentialAuthType}
            onUserCredentialAuthTypeChange={onUserCredentialAuthTypeChange}
            oauth2Config={oauth2Config}
            onOauth2ConfigChange={onOauth2ConfigChange}
            oauthClientSecret={oauthClientSecret}
            maskedClientSecret={
              dataSource?.config?.user_oauth?.client_secret
                ? String(dataSource.config.user_oauth.client_secret)
                : null
            }
            fieldErrors={userAuthFieldErrors}
            onClearFieldError={onClearUserAuthFieldError}
          />
        ) : null}

        {watchedCredentialMode === 'user' ? (
          <MetadataSyncSection
            selectedType={selectedType}
            isSubmitting={isSubmitting}
            register={register}
            errors={errors}
            connectionFieldErrors={connectionFieldErrors}
            clearConnectionFieldErrors={clearConnectionFieldErrors}
            syncPasswordSecret={syncPasswordSecret}
            dataSource={dataSource}
          />
        ) : null}

        <DataSourceConnectionTests
          key={`${selectedType}-${watchedCredentialMode}`}
          type={selectedType}
          credentialMode={watchedCredentialMode}
          getFormData={() => watch()}
          disabled={isSubmitting || saving}
          dataSourceId={dataSource?.id}
          sharedPasswordSecret={watchedCredentialMode === 'shared' ? sharedPasswordSecret : undefined}
          syncPasswordSecret={watchedCredentialMode === 'user' ? syncPasswordSecret : undefined}
        />
      </div>
    </div>
  )
}

function CredentialModePicker({
  isSubmitting,
  watchedCredentialMode,
  setValue,
  register,
}: {
  isSubmitting: boolean
  watchedCredentialMode: 'shared' | 'user'
  setValue: AddDataSourceDialogFormProps['setValue']
  register: UseFormRegister<DataSourceFormValues>
}) {
  const { t } = useTranslation()
  return (
    <div className={dsFieldRowStartClass}>
      <Label className={`${dsFieldLabelClass} pt-2`}>{t('components.addDataSourceDialog.credentialMode')}</Label>
      <div className="min-w-0 space-y-1.5">
        <input type="hidden" {...register('credentialMode')} />
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              { value: 'shared' as const, titleKey: 'credentialModeSharedTitle', subtitleKey: 'credentialModeSharedSubtitle' },
              { value: 'user' as const, titleKey: 'credentialModeUserTitle', subtitleKey: 'credentialModeUserSubtitle' },
            ] as const
          ).map((option) => {
            const selected = watchedCredentialMode === option.value
            return (
              <button
                key={option.value}
                type="button"
                disabled={isSubmitting}
                onClick={() => setValue('credentialMode', option.value, { shouldDirty: true })}
                className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                  selected
                    ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                    : 'border-border hover:border-primary/40 hover:bg-muted/40'
                } ${isSubmitting ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <span className="block text-sm font-medium leading-tight">
                  {t(`components.addDataSourceDialog.${option.titleKey}`)}
                </span>
                <span className="block text-xs text-muted-foreground mt-0.5 leading-snug">
                  {t(`components.addDataSourceDialog.${option.subtitleKey}`)}
                </span>
              </button>
            )
          })}
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {watchedCredentialMode === 'user'
            ? t('components.addDataSourceDialog.credentialModeHelpUser')
            : t('components.addDataSourceDialog.credentialModeHelpShared')}
        </p>
      </div>
    </div>
  )
}

function ConnectionSection(props: {
  selectedType: DataSourceFormType
  watchedCredentialMode: 'shared' | 'user'
  register: UseFormRegister<DataSourceFormValues>
  errors: FieldErrors<DataSourceFormValues>
  connectionFieldErrors: DataSourceConnectionFieldErrors
  isSubmitting: boolean
  watch: UseFormWatch<DataSourceFormValues>
  clearConnectionFieldErrors: () => void
  sharedPasswordSecret: SecretCredentialFieldHandle
  dataSource?: DataSource | null
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2.5">
      <DataSourceFormSectionHeader
        icon={Database}
        title={
          props.watchedCredentialMode === 'user'
            ? t('components.addDataSourceDialog.connectionConfigUserTitle')
            : t('components.addDataSourceDialog.connectionConfig')
        }
        description={
          props.watchedCredentialMode === 'user'
            ? t('components.addDataSourceDialog.connectionConfigUserHint')
            : t('components.addDataSourceDialog.connectionConfigSharedHint')
        }
      />
      {props.selectedType === 'databricks' ? (
        <DatabricksConnectionForm
          register={props.register}
          errors={props.errors}
          connectionFieldErrors={props.connectionFieldErrors}
          disabled={props.isSubmitting}
          getFormData={() => props.watch()}
          showTestConnection={false}
          credentialMode={props.watchedCredentialMode}
          onFieldChange={props.clearConnectionFieldErrors}
          sharedPasswordSecret={
            props.watchedCredentialMode === 'shared' ? props.sharedPasswordSecret : undefined
          }
          sharedPasswordMaskedPreview={
            props.watchedCredentialMode === 'shared' && props.dataSource?.config?.password
              ? String(props.dataSource.config.password)
              : null
          }
        />
      ) : (
        <RDBMSConnectionForm
          type={props.selectedType}
          register={props.register}
          errors={props.errors}
          connectionFieldErrors={props.connectionFieldErrors}
          disabled={props.isSubmitting}
          getFormData={() => props.watch()}
          credentialMode={props.watchedCredentialMode}
          showTestConnection={false}
          onFieldChange={props.clearConnectionFieldErrors}
          sharedPasswordSecret={
            props.watchedCredentialMode === 'shared' ? props.sharedPasswordSecret : undefined
          }
          sharedPasswordMaskedPreview={
            props.watchedCredentialMode === 'shared' && props.dataSource?.config?.password
              ? String(props.dataSource.config.password)
              : null
          }
        />
      )}
    </div>
  )
}

function MetadataSyncSection(props: {
  selectedType: DataSourceFormType
  isSubmitting: boolean
  register: UseFormRegister<DataSourceFormValues>
  errors: FieldErrors<DataSourceFormValues>
  connectionFieldErrors: DataSourceConnectionFieldErrors
  clearConnectionFieldErrors: () => void
  syncPasswordSecret: SecretCredentialFieldHandle
  dataSource?: DataSource | null
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2.5 border-t border-border pt-4">
      <DataSourceFormSectionHeader
        icon={RefreshCw}
        title={t('components.addDataSourceDialog.metadataSyncTitle')}
        description={t('components.addDataSourceDialog.metadataSyncHelp')}
      />
      {props.selectedType !== 'databricks' ? (
        <div className={dsFieldPairRowClass}>
          <Label htmlFor="metadataSyncUsername" className={dsFieldLabelClass}>
            {t('components.addDataSourceDialog.metadataSyncUsername')}{' '}
            <span className="text-destructive">*</span>
          </Label>
          <Input
            id="metadataSyncUsername"
            {...props.register('metadataSyncUsername', { onChange: () => props.clearConnectionFieldErrors() })}
            disabled={props.isSubmitting}
            className="h-8 text-sm w-full min-w-0"
            autoComplete="off"
            errorMsg={resolveConnectionFieldError(
              'metadataSyncUsername',
              props.connectionFieldErrors,
              props.errors,
            )}
          />
          <Label htmlFor="metadataSyncPassword" className={dsFieldLabelClass}>
            {t('components.addDataSourceDialog.metadataSyncPassword')}{' '}
            <span className="text-destructive">*</span>
          </Label>
          <SensitiveCredentialField
            id="metadataSyncPassword"
            hideLabel
            label={
              <>
                {t('components.addDataSourceDialog.metadataSyncPassword')}{' '}
                <span className="text-destructive">*</span>
              </>
            }
            binding={props.syncPasswordSecret}
            maskedPreview={
              props.dataSource?.config?.metadata_sync?.password
                ? String(props.dataSource.config.metadata_sync.password)
                : null
            }
            disabled={props.isSubmitting}
            errorMsg={resolveConnectionFieldError(
              'metadataSyncPassword',
              props.connectionFieldErrors,
              props.errors,
            )}
            onStartEdit={props.syncPasswordSecret.startEdit}
            onCancelEdit={props.syncPasswordSecret.cancelEdit}
            onDraftChange={(value) => {
              props.syncPasswordSecret.setDraft(value)
              props.clearConnectionFieldErrors()
            }}
          />
        </div>
      ) : (
        <div className={dsFieldRowClass}>
          <Label htmlFor="metadataSyncPassword" className={dsFieldLabelClass}>
            {t('components.addDataSourceDialog.metadataSyncToken')}{' '}
            <span className="text-destructive">*</span>
          </Label>
          <SensitiveCredentialField
            id="metadataSyncPassword"
            hideLabel
            label={
              <>
                {t('components.addDataSourceDialog.metadataSyncToken')}{' '}
                <span className="text-destructive">*</span>
              </>
            }
            binding={props.syncPasswordSecret}
            maskedPreview={
              props.dataSource?.config?.metadata_sync?.password
                ? String(props.dataSource.config.metadata_sync.password)
                : null
            }
            disabled={props.isSubmitting}
            errorMsg={resolveConnectionFieldError(
              'metadataSyncPassword',
              props.connectionFieldErrors,
              props.errors,
            )}
            onStartEdit={props.syncPasswordSecret.startEdit}
            onCancelEdit={props.syncPasswordSecret.cancelEdit}
            onDraftChange={(value) => {
              props.syncPasswordSecret.setDraft(value)
              props.clearConnectionFieldErrors()
            }}
          />
        </div>
      )}
    </div>
  )
}