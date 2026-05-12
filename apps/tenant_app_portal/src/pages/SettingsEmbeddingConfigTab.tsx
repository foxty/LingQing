import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { Alert, AlertDescription } from '@/components/ui/alert'
import EmbeddingConfigCard, {
  type EmbeddingFormState,
  type EmbeddingSourceType,
} from '@/components/EmbeddingConfigCard'
import { useNotification } from '@/hooks/useNotification'
import {
  getEmbeddingProviders,
  getTenantEmbeddingConfig,
  testEmbeddingConnection,
  updateTenantEmbeddingConfig,
  findPresetByModel,
  resolvePresetApiBase,
  type PresetModel,
  type PresetProvider,
} from '@/lib/tenantApi'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    settings: {
      embeddingTab: {
        title: 'Embedding Configuration',
        description: 'Configure embedding model for the tenant',
        testSuccess: 'Connection test successful',
        testFailed: 'Test failed: {{label}}',
        saveSuccess: 'Configuration saved',
        saveFailed: 'Save failed',
        pleaseConfigure: 'Please configure API base, model ID, and API key',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    settings: {
      embeddingTab: {
        title: 'Embedding 配置',
        description: '配置租户的 Embedding 模型',
        testSuccess: '连接测试成功',
        testFailed: '测试失败: {{label}}',
        saveSuccess: '配置已保存',
        saveFailed: '保存失败',
        pleaseConfigure: '请配置 API Base、Model ID 和 API Key',
      },
    },
  },
  true,
  true
)

export default function SettingsEmbeddingConfigTab() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()

  const [providers, setProviders] = useState<PresetProvider[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testStatus, setTestStatus] = useState<{ ok: boolean; message: string } | null>(null)

  const [embeddingModel, setEmbeddingModel] = useState<EmbeddingFormState>({
    name: '',
    type: 'openai-compatible',
    api_base: '',
    api_key: '',
    model_id: '',
    api_key_masked: '',
  })

  const [sourceType, setSourceType] = useState<EmbeddingSourceType>('preset')
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedModelKey, setSelectedModelKey] = useState('')
  const [customBase, setCustomBase] = useState('')
  const [customModelId, setCustomModelId] = useState('')
  const [showKey, setShowKey] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const findProviderByModelId = (
    modelId: string,
    apiBase: string,
    providerList: PresetProvider[]
  ) => findPresetByModel(providerList, modelId, apiBase)

  const findModel = (modelKey: string): { provider: PresetProvider; model: PresetModel } | null => {
    for (const provider of providers) {
      const model = provider.models.find((m) => m.key === modelKey)
      if (model) return { provider, model }
    }
    return null
  }

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [providersData, configData] = await Promise.all([
        getEmbeddingProviders(),
        getTenantEmbeddingConfig().catch(() => null),
      ])
      setProviders(providersData)

      if (configData?.embedding_model) {
        const model = configData.embedding_model
        setEmbeddingModel({
          name: model.name,
          type: model.type,
          api_base: model.api_base,
          api_key: '',
          model_id: model.model_id,
          api_key_masked: model.api_key_masked,
        })

        const found = findProviderByModelId(model.model_id, model.api_base, providersData)
        if (found) {
          setSelectedProvider(found.providerKey)
          setSelectedModelKey(found.modelKey)
          setSourceType('preset')
        } else {
          setSourceType('custom')
          setCustomBase(model.api_base)
          setCustomModelId(model.model_id)
        }
      } else if (providersData.length > 0) {
        const firstProvider = providersData.find((p) => p.models.length > 0) ?? providersData[0]
        setSelectedProvider(firstProvider.provider)
      }
    } catch (err: any) {
      setError(err.message || t('settings.embeddingTab.saveFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleProviderSelect = (providerKey: string) => {
    setSelectedProvider(providerKey)
    setSelectedModelKey('')
    const provider = providers.find((p) => p.provider === providerKey)
    if (provider) {
      setEmbeddingModel((prev) => ({
        ...prev,
        type: provider.type || 'openai-compatible',
        api_base: resolvePresetApiBase(provider.api_base, prev.api_base),
      }))
    }
  }

  const handleModelSelect = (modelKey: string) => {
    setSelectedModelKey(modelKey)
    const found = findModel(modelKey)
    if (found) {
      setEmbeddingModel((prev) => ({
        name: found.model.name,
        type: found.provider.type || 'openai-compatible',
        api_base: resolvePresetApiBase(found.provider.api_base, prev.api_base),
        api_key: '',
        model_id: found.model.model_id,
        api_key_masked: prev.api_key_masked,
      }))
    }
  }

  const handleCustomChange = (base: string, modelId: string) => {
    setCustomBase(base)
    setCustomModelId(modelId)
    setEmbeddingModel((prev) => ({
      ...prev,
      api_base: base,
      model_id: modelId,
      type: 'openai-compatible',
      name: modelId || 'Custom Embedding Model',
    }))
  }

  const validateModel = (allowEmptyKey = false): string | null => {
    if (!embeddingModel.api_base || !embeddingModel.model_id) {
      return t('settings.embeddingTab.pleaseConfigure')
    }
    if (!allowEmptyKey && !embeddingModel.api_key) {
      return t('settings.embeddingTab.pleaseConfigure')
    }
    return null
  }

  const handleTest = async () => {
    const validationError = validateModel()
    if (validationError) {
      setTestStatus({ ok: false, message: validationError })
      return
    }

    setTesting(true)
    setTestStatus(null)
    try {
      await testEmbeddingConnection({
        api_base: embeddingModel.api_base,
        model_id: embeddingModel.model_id,
        api_key: embeddingModel.api_key,
      })
      setTestStatus({ ok: true, message: t('settings.embeddingTab.testSuccess') })
    } catch (err: any) {
      setTestStatus({
        ok: false,
        message: err.message || t('settings.embeddingTab.testFailed', { label: 'Embedding' }),
      })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    const allowEmptyKey = Boolean(embeddingModel.api_key_masked && !embeddingModel.api_key)
    const validationError = validateModel(allowEmptyKey)
    if (validationError) {
      showError(validationError)
      return
    }

    setSaving(true)
    try {
      await updateTenantEmbeddingConfig({
        embedding_model: {
          name: embeddingModel.name || embeddingModel.model_id,
          type: embeddingModel.type,
          api_base: embeddingModel.api_base,
          api_key: embeddingModel.api_key,
          model_id: embeddingModel.model_id,
        },
      })
      showSuccess(t('settings.embeddingTab.saveSuccess'))
      await loadData()
    } catch (err: any) {
      showError(err.message || t('settings.embeddingTab.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <EmbeddingConfigCard
        title={t('settings.embeddingTab.title')}
        description={t('settings.embeddingTab.description')}
        formState={embeddingModel}
        setFormState={setEmbeddingModel}
        sourceType={sourceType}
        setSourceType={setSourceType}
        selectedProvider={selectedProvider}
        selectedModelKey={selectedModelKey}
        providers={providers}
        onProviderSelect={handleProviderSelect}
        onModelSelect={handleModelSelect}
        customBase={customBase}
        customModelId={customModelId}
        onCustomChange={handleCustomChange}
        showKey={showKey}
        setShowKey={setShowKey}
        testing={testing}
        saving={saving}
        testStatus={testStatus}
        onTest={handleTest}
        onSave={handleSave}
      />
    </div>
  )
}
