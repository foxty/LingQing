import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    addApiConnectorDialog: {
      title: 'Add API Connector',
      editTitle: 'Edit API Connector',
      description: 'Description',
      basicInfo: 'Basic Information',
      name: 'Name',
      descriptionPlaceholder: 'Optional description',
      authConfig: 'Authentication',
      configured: 'Configured',
      authType: 'Auth Type',
      schemaConfig: 'Schema Configuration',
      schemaNote: 'Upload an OpenAPI spec file via the import dialog after creating the connector',
      saving: 'Saving...',
      createSuccess: 'API connector created successfully',
      updateSuccess: 'API connector updated successfully',
      cancelConfirmTitle: 'Discard changes?',
      cancelConfirmDesc: 'You have unsaved changes. Are you sure you want to discard them?',
      continueEditing: 'Continue Editing',
      discard: 'Discard',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    addApiConnectorDialog: {
      title: '添加 API 连接器',
      editTitle: '编辑 API 连接器',
      description: '描述',
      basicInfo: '基本信息',
      name: '名称',
      descriptionPlaceholder: '可选描述',
      authConfig: '认证配置',
      configured: '已配置',
      authType: '认证类型',
      schemaConfig: 'Schema 配置',
      schemaNote: '创建连接器后，通过导入对话框上传 OpenAPI 规范文件',
      saving: '保存中...',
      createSuccess: 'API 连接器创建成功',
      updateSuccess: 'API 连接器更新成功',
      cancelConfirmTitle: '放弃更改？',
      cancelConfirmDesc: '你有未保存的更改，确定要放弃吗？',
      continueEditing: '继续编辑',
      discard: '放弃',
    },
  },
}, true, true)

import {
  ApiKeyAuthConfig,
  BasicAuthConfig,
  BearerAuthConfig,
  CustomAuthConfig,
} from '@/components/auth-configs'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useNotification } from '@/hooks/useNotification'
import type {
  ApiConnector,
  ApiConnectorAuthType,
  ApiConnectorCreateRequest,
  ApiConnectorSchemaSourceType,
  ApiConnectorUpdateRequest,
} from '@/lib/apiConnectorApi'

interface AddApiConnectorDialogProps {
  open: boolean
  submitting?: boolean
  connector?: ApiConnector | null
  onOpenChange: (open: boolean) => void
  onCreate?: (payload: ApiConnectorCreateRequest) => Promise<ApiConnector>
  onUpdate?: (connectorId: number, payload: ApiConnectorUpdateRequest) => Promise<ApiConnector>
  onCreated?: (connector: ApiConnector) => void
  onUpdated?: (connector: ApiConnector) => void
}

interface ApiKeyConfig {
  keyName: string
  keyValue: string
}

interface BearerConfig {
  token: string
}

interface BasicConfig {
  username: string
  password: string
}

interface CustomAuthConfig {
  loginEndpoint: string
  loginMethod: string
  loginPayloadTemplate: string
  tokenExtraction: string
  requestHeaders: string
  extraConfig: string
}

const defaultApiKeyConfig: ApiKeyConfig = {
  keyName: 'X-API-Key',
  keyValue: '',
}

const defaultBearerConfig: BearerConfig = {
  token: '',
}

const defaultBasicConfig: BasicConfig = {
  username: '',
  password: '',
}

const defaultCustomAuthConfig: CustomAuthConfig = {
  loginEndpoint: '',
  loginMethod: 'POST',
  loginPayloadTemplate: '{}',
  tokenExtraction: '{}',
  requestHeaders: '{}',
  extraConfig: '{}',
}

export default function AddApiConnectorDialog({
  open,
  submitting = false,
  connector,
  onOpenChange,
  onCreate,
  onUpdate,
  onCreated,
  onUpdated,
}: AddApiConnectorDialogProps) {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()

  const mode: 'create' | 'edit' = connector && onUpdate ? 'edit' : 'create'
  const initialAuthType = connector?.auth_type ?? 'none'

  // True when the server has a non-empty masked auth config, meaning credentials
  // were previously saved. auth_config_masked keys are present but values are
  // masked (e.g. "****"), so checking object size is sufficient.
  const isAuthConfigured =
    mode === 'edit' &&
    connector?.auth_type !== 'none' &&
    Object.keys(connector?.auth_config_masked ?? {}).length > 0

  const [showCloseConfirm, setShowCloseConfirm] = useState(false)

  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [description, setDescription] = useState('')

  const [authType, setAuthType] = useState<ApiConnectorAuthType>('none')
  const [apiKeyConfig, setApiKeyConfig] = useState<ApiKeyConfig>(defaultApiKeyConfig)
  const [bearerConfig, setBearerConfig] = useState<BearerConfig>(defaultBearerConfig)
  const [basicConfig, setBasicConfig] = useState<BasicConfig>(defaultBasicConfig)
  const [customAuthConfig, setCustomAuthConfig] =
    useState<CustomAuthConfig>(defaultCustomAuthConfig)

  const [schemaSourceType, setSchemaSourceType] = useState<ApiConnectorSchemaSourceType>('manual')
  const [schemaSourceUrl, setSchemaSourceUrl] = useState('')

  useEffect(() => {
    if (!open) {
      return
    }

    if (mode === 'edit' && connector) {
      setName(connector.name)
      setBaseUrl(connector.base_url)
      setDescription(connector.description || '')
      setAuthType(connector.auth_type)
      setSchemaSourceType(connector.schema_source_type)
      setSchemaSourceUrl(connector.schema_source_url || '')
      setApiKeyConfig(defaultApiKeyConfig)
      setBearerConfig(defaultBearerConfig)
      setBasicConfig(defaultBasicConfig)

      // Load custom auth config structure from masked response
      // Note: Sensitive values (credentials) are masked and can't be loaded,
      // but we preserve the configuration structure (endpoints, templates, etc.)
      if (connector.auth_type === 'custom' && connector.auth_config_masked) {
        const masked = connector.auth_config_masked
        setCustomAuthConfig({
          loginEndpoint: masked.login_endpoint || '',
          loginMethod: masked.login_method || 'POST',
          loginPayloadTemplate: JSON.stringify(masked.login_payload_template || {}, null, 2),
          tokenExtraction: JSON.stringify(masked.token_extraction || {}, null, 2),
          requestHeaders: JSON.stringify(masked.request_headers || {}, null, 2),
          extraConfig: JSON.stringify(masked.extra_config || {}, null, 2),
        })
      } else {
        setCustomAuthConfig(defaultCustomAuthConfig)
      }

      return
    }

    resetForm()
  }, [open, mode, connector])

  const authConfig = useMemo<Record<string, any>>(() => {
    if (authType === 'api_key') {
      return {
        auth_method: 'api_key',
        key_name: apiKeyConfig.keyName.trim(),
        key_value: apiKeyConfig.keyValue,
      }
    }

    if (authType === 'bearer') {
      return {
        auth_method: 'bearer',
        token: bearerConfig.token,
      }
    }

    if (authType === 'basic') {
      return {
        auth_method: 'basic',
        username: basicConfig.username,
        password: basicConfig.password,
      }
    }

    if (authType === 'custom') {
      // Parse JSON fields safely - return empty objects for invalid JSON
      // Validation will happen during form submission
      const parseJsonSafely = (jsonString: string, fieldName: string): any => {
        if (!jsonString || !jsonString.trim()) {
          return {}
        }
        try {
          return JSON.parse(jsonString)
        } catch (e) {
          console.warn(`Invalid JSON in ${fieldName}:`, e)
          return {} // Return empty object instead of crashing
        }
      }

      return {
        auth_method: 'custom',
        login_endpoint: customAuthConfig.loginEndpoint.trim(),
        login_method: customAuthConfig.loginMethod || 'POST',
        login_payload_template: parseJsonSafely(
          customAuthConfig.loginPayloadTemplate,
          'login_payload_template'
        ),
        token_extraction: parseJsonSafely(customAuthConfig.tokenExtraction, 'token_extraction'),
        request_headers: parseJsonSafely(customAuthConfig.requestHeaders, 'request_headers'),
        extra_config: parseJsonSafely(customAuthConfig.extraConfig, 'extra_config'),
      }
    }

    return {}
  }, [apiKeyConfig, authType, basicConfig, bearerConfig, customAuthConfig])

  const resetForm = () => {
    setName('')
    setBaseUrl('')
    setDescription('')
    setAuthType('none')
    setApiKeyConfig(defaultApiKeyConfig)
    setBearerConfig(defaultBearerConfig)
    setBasicConfig(defaultBasicConfig)
    setCustomAuthConfig(defaultCustomAuthConfig)
    setSchemaSourceType('manual')
    setSchemaSourceUrl('')
  }

  const hasUnsavedData = () => {
    return !!(
      name.trim() ||
      baseUrl.trim() ||
      description.trim() ||
      schemaSourceUrl.trim() ||
      authType !== 'none' ||
      schemaSourceType !== 'manual' ||
      apiKeyConfig.keyValue.trim() ||
      bearerConfig.token.trim() ||
      basicConfig.username.trim() ||
      basicConfig.password.trim()
    )
  }

  const closeWithoutConfirm = () => {
    setShowCloseConfirm(false)
    onOpenChange(false)
    resetForm()
  }

  const closeWithConfirm = () => {
    if (submitting) {
      return
    }
    if (hasUnsavedData()) {
      setShowCloseConfirm(true)
      return
    }
    closeWithoutConfirm()
  }

  const validateBeforeSubmit = () => {
    if (!name.trim() || !baseUrl.trim()) {
      showError(t('common.failedToLoad'))
      return false
    }

    const authChanged = mode === 'create' || authType !== initialAuthType
    const hasApiKeyInput = apiKeyConfig.keyName.trim() || apiKeyConfig.keyValue.trim()
    const hasBearerInput = bearerConfig.token.trim()
    const hasBasicInput = basicConfig.username.trim() || basicConfig.password.trim()

    if (
      authType === 'api_key' &&
      (authChanged || hasApiKeyInput) &&
      !apiKeyConfig.keyValue.trim()
    ) {
      showError(t('common.failedToLoad'))
      return false
    }

    if (authType === 'bearer' && (authChanged || hasBearerInput) && !bearerConfig.token.trim()) {
      showError(t('common.failedToLoad'))
      return false
    }

    if (
      authType === 'basic' &&
      (authChanged || hasBasicInput) &&
      (!basicConfig.username.trim() || !basicConfig.password.trim())
    ) {
      showError(t('common.failedToLoad'))
      return false
    }

    // Validate custom auth JSON fields
    if (authType === 'custom') {
      const validateJson = (jsonString: string): boolean => {
        if (!jsonString || !jsonString.trim()) {
          return true // Empty is allowed, will use default {}
        }
        try {
          JSON.parse(jsonString)
          return true
        } catch {
          showError(t('common.failedToLoad'))
          return false
        }
      }

      if (!validateJson(customAuthConfig.loginPayloadTemplate)) {
        return false
      }
      if (!validateJson(customAuthConfig.tokenExtraction)) {
        return false
      }
      if (!validateJson(customAuthConfig.requestHeaders)) {
        return false
      }
      if (!validateJson(customAuthConfig.extraConfig)) {
        return false
      }

      // Validate required fields for custom auth
      if (!customAuthConfig.loginEndpoint.trim()) {
        showError(t('common.failedToLoad'))
        return false
      }
    }

    if (schemaSourceType === 'openapi_url' && !schemaSourceUrl.trim()) {
      showError(t('common.failedToLoad'))
      return false
    }

    return true
  }

  const handleSubmit = async () => {
    if (!validateBeforeSubmit()) {
      return
    }

    try {
      if (mode === 'edit' && connector && onUpdate) {
        const payload: ApiConnectorUpdateRequest = {
          name: name.trim(),
          description: description.trim() || undefined,
          base_url: baseUrl.trim(),
          auth_type: authType,
          schema_source_type: schemaSourceType,
          schema_source_url:
            schemaSourceType === 'openapi_url' ? schemaSourceUrl.trim() || null : null,
        }

        const authChanged = authType !== initialAuthType
        const hasAuthInput =
          apiKeyConfig.keyValue.trim() ||
          bearerConfig.token.trim() ||
          basicConfig.username.trim() ||
          basicConfig.password.trim()

        // Include auth_config if auth type changed, standard auth fields have input,
        // or custom auth is selected (since it's always configured via UI)
        const shouldIncludeAuthConfig = authChanged || hasAuthInput || authType === 'custom'

        if (shouldIncludeAuthConfig) {
          payload.auth_config = authConfig
        }

        const updated = await onUpdate(connector.id, payload)
        showSuccess(t('components.addApiConnectorDialog.updateSuccess'))
        onUpdated?.(updated)
      } else {
        if (!onCreate) {
          showError(t('common.failedToLoad'))
          return
        }
        const created = await onCreate({
          name: name.trim(),
          description: description.trim() || undefined,
          base_url: baseUrl.trim(),
          auth_type: authType,
          auth_config: authConfig,
          rate_policy: {},
          schema_source_type: schemaSourceType,
          schema_source_url:
            schemaSourceType === 'openapi_url' ? schemaSourceUrl.trim() || null : null,
        })
        showSuccess(t('components.addApiConnectorDialog.createSuccess'))
        onCreated?.(created)
      }
      closeWithoutConfirm()
    } catch (err: any) {
      showError(err.response?.data?.detail || err.message || t('common.failedToLoad'))
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
        <DialogContent className="sm:max-w-[780px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{mode === 'edit' ? t('components.addApiConnectorDialog.editTitle') : t('components.addApiConnectorDialog.title')}</DialogTitle>
            <DialogDescription>{t('components.addApiConnectorDialog.description')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-5">
            <div className="space-y-3">
              <h3 className="text-sm font-semibold">{t('components.addApiConnectorDialog.basicInfo')}</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="add-connector-name">{t('components.addApiConnectorDialog.name')}</Label>
                  <Input
                    id="add-connector-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="orders-api"
                    disabled={submitting}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="add-connector-base-url">Base URL</Label>
                  <Input
                    id="add-connector-base-url"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="https://api.example.com"
                    disabled={submitting}
                  />
                </div>
              </div>
              <div className="space-y-2">
                  <Label htmlFor="add-connector-description">{t('components.addApiConnectorDialog.description')}</Label>
                <Input
                  id="add-connector-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t('components.addApiConnectorDialog.descriptionPlaceholder')}
                  disabled={submitting}
                />
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold">{t('components.addApiConnectorDialog.authConfig')}</h3>
                {isAuthConfigured && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-xs font-medium text-success ring-1 ring-inset ring-success/20">
                    ✓ {t('components.addApiConnectorDialog.configured')}
                  </span>
                )}
              </div>
              <div className="space-y-2">
                <Label>{t('components.addApiConnectorDialog.authType')}</Label>
                <Select
                  value={authType}
                  onValueChange={(v) => setAuthType(v as ApiConnectorAuthType)}
                  disabled={submitting}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">none</SelectItem>
                    <SelectItem value="api_key">api_key</SelectItem>
                    <SelectItem value="bearer">bearer</SelectItem>
                    <SelectItem value="basic">basic</SelectItem>
                    <SelectItem value="custom">custom (session-based)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {authType === 'api_key' && (
                <ApiKeyAuthConfig
                  keyName={apiKeyConfig.keyName}
                  keyValue={apiKeyConfig.keyValue}
                  isAuthConfigured={isAuthConfigured}
                  submitting={submitting}
                  onKeyNameChange={(value) =>
                    setApiKeyConfig((prev) => ({ ...prev, keyName: value }))
                  }
                  onKeyValueChange={(value) =>
                    setApiKeyConfig((prev) => ({ ...prev, keyValue: value }))
                  }
                />
              )}

              {authType === 'bearer' && (
                <BearerAuthConfig
                  token={bearerConfig.token}
                  isAuthConfigured={isAuthConfigured}
                  submitting={submitting}
                  onTokenChange={(value) => setBearerConfig({ token: value })}
                />
              )}

              {authType === 'basic' && (
                <BasicAuthConfig
                  username={basicConfig.username}
                  password={basicConfig.password}
                  isAuthConfigured={isAuthConfigured}
                  submitting={submitting}
                  onUsernameChange={(value) =>
                    setBasicConfig((prev) => ({ ...prev, username: value }))
                  }
                  onPasswordChange={(value) =>
                    setBasicConfig((prev) => ({ ...prev, password: value }))
                  }
                />
              )}

              {authType === 'custom' && (
                <CustomAuthConfig
                  config={customAuthConfig}
                  submitting={submitting}
                  onChange={setCustomAuthConfig}
                />
              )}
            </div>

            <div className="space-y-3">
              <h3 className="text-sm font-semibold">{t('components.addApiConnectorDialog.schemaConfig')}</h3>
              <div className="space-y-2">
                <Label>Schema Source Type</Label>
                <Select
                  value={schemaSourceType}
                  onValueChange={(v) => setSchemaSourceType(v as ApiConnectorSchemaSourceType)}
                  disabled={submitting}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">manual</SelectItem>
                    <SelectItem value="openapi_url">openapi_url</SelectItem>
                    <SelectItem value="openapi_upload">openapi_upload</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {schemaSourceType === 'openapi_url' && (
                <div className="space-y-2">
                  <Label htmlFor="add-schema-source-url">Schema URL</Label>
                  <Input
                    id="add-schema-source-url"
                    value={schemaSourceUrl}
                    onChange={(e) => setSchemaSourceUrl(e.target.value)}
                    placeholder="https://api.example.com/openapi.json"
                    disabled={submitting}
                  />
                </div>
              )}

              {schemaSourceType === 'openapi_upload' && (
                <div className="space-y-2">
                  <Label htmlFor="add-schema-upload-note">{t('common.description')}</Label>
                  <Textarea
                    id="add-schema-upload-note"
                    value={t('components.addApiConnectorDialog.schemaNote')}
                    readOnly
                    rows={3}
                  />
                </div>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeWithConfirm} disabled={submitting}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting ? t('components.addApiConnectorDialog.saving') : mode === 'edit' ? t('common.saveChanges') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('components.addApiConnectorDialog.cancelConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('components.addApiConnectorDialog.cancelConfirmDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('components.addApiConnectorDialog.continueEditing')}</AlertDialogCancel>
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
