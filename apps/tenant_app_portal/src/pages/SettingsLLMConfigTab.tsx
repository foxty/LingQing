import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useNotification } from '@/hooks/useNotification'
import {
  copyAgentToMini,
  getLLMProviders,
  getTenantLLMConfig,
  testLLMConnection,
  updateAgentModelConfig,
  updateMiniAgentModelConfig,
  findPresetByModel,
  resolvePresetApiBase,
  isEditableApiBase,
  type PresetModel,
  type PresetProvider,
  type TenantLLMConfigResponse,
  type UpdateLLMConfigRequest,
} from '@/lib/tenantApi'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import ModelConfigCard from '@/components/ModelConfigCard'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    llmConfigTab: {
      agentModel: 'Agent Model',
      agentModelDesc: 'Configure the LLM model for the Agent',
      agentSaveSuccess: 'Agent model saved',
      agentSaveFailed: 'Agent save failed',
      miniModel: 'Mini Agent Model',
      miniModelDesc: 'Configure the LLM model for the Mini Agent',
      miniSaveSuccess: 'Mini Agent model saved',
      miniSaveFailed: 'Mini Agent save failed',
      testSuccess: 'Connection test successful',
      testFailed: 'Test failed: {{label}}',
      pleaseConfigureAgent: 'Please configure the model first',
      copiedToMini: 'Agent config copied to Mini Agent',
      copyFailed: 'Copy failed',
      copyAgentToMini: 'Copy to Mini Agent',
      replacePlaceholder: 'Replace <workspace> in the API Base URL',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    llmConfigTab: {
      agentModel: 'Agent 模型',
      agentModelDesc: '配置 Agent 的 LLM 模型',
      agentSaveSuccess: 'Agent 模型已保存',
      agentSaveFailed: 'Agent 保存失败',
      miniModel: 'Mini Agent 模型',
      miniModelDesc: '配置 Mini Agent 的 LLM 模型',
      miniSaveSuccess: 'Mini Agent 模型已保存',
      miniSaveFailed: 'Mini Agent 保存失败',
      testSuccess: '连接测试成功',
      testFailed: '测试失败: {{label}}',
      pleaseConfigureAgent: '请先配置模型',
      copiedToMini: 'Agent 配置已复制到 Mini Agent',
      copyFailed: '复制失败',
      copyAgentToMini: '复制到 Mini Agent',
      replacePlaceholder: '请将 API Base 中的 <workspace> 替换为实际工作区',
    }
  }
}, true, true)

interface ModelFormState {
  name: string
  type: string
  api_base: string
  api_key: string
  model_id: string
  api_key_masked?: string
  params?: {
    temperature?: number
    max_tokens?: number
    top_p?: number
  }
}

type ModelSourceType = 'preset' | 'custom'

export default function SettingsLLMConfigTab() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()

  const [providers, setProviders] = useState<PresetProvider[]>([])
  const [, setExistingConfig] = useState<TenantLLMConfigResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testingAgent, setTestingAgent] = useState(false)
  const [testingMini, setTestingMini] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [agentTestStatus, setAgentTestStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const [miniTestStatus, setMiniTestStatus] = useState<{ ok: boolean; message: string } | null>(null)

  const [agentModel, setAgentModel] = useState<ModelFormState>({
    name: '',
    type: 'openai-compatible',
    api_base: '',
    api_key: '',
    model_id: '',
    api_key_masked: '',
    params: { temperature: 0.1 },
  })
  const [miniAgentModel, setMiniAgentModel] = useState<ModelFormState>({
    name: '',
    type: 'openai-compatible',
    api_base: '',
    api_key: '',
    model_id: '',
    api_key_masked: '',
    params: { temperature: 0.1 },
  })

  const [agentSourceType, setAgentSourceType] = useState<ModelSourceType>('preset')
  const [miniSourceType, setMiniSourceType] = useState<ModelSourceType>('preset')

  const [selectedAgentProvider, setSelectedAgentProvider] = useState<string>('')
  const [selectedAgentModel, setSelectedAgentModel] = useState<string>('')
  const [selectedMiniProvider, setSelectedMiniProvider] = useState<string>('')
  const [selectedMiniModel, setSelectedMiniModel] = useState<string>('')

  const [customAgentBase, setCustomAgentBase] = useState('')
  const [customAgentModelId, setCustomAgentModelId] = useState('')
  const [customMiniBase, setCustomMiniBase] = useState('')
  const [customMiniModelId, setCustomMiniModelId] = useState('')

  const [showAgentKey, setShowAgentKey] = useState(false)
  const [showMiniKey, setShowMiniKey] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [providersData, configData] = await Promise.all([
        getLLMProviders(),
        getTenantLLMConfig().catch(() => null),
      ])
      setProviders(providersData)
      setExistingConfig(configData)

      if (configData) {
        const agent = configData.agent_model
        const mini = configData.mini_agent_model

        const findProviderByModelId = (modelId: string, apiBase: string) =>
          findPresetByModel(providersData, modelId, apiBase)

        setAgentModel({
          name: agent.name,
          type: agent.type,
          api_base: agent.api_base,
          api_key: '',
          model_id: agent.model_id,
          api_key_masked: agent.api_key_masked,
          params: agent.params || { temperature: 0.1 },
        })
        setMiniAgentModel({
          name: mini.name,
          type: mini.type,
          api_base: mini.api_base,
          api_key: '',
          model_id: mini.model_id,
          api_key_masked: mini.api_key_masked,
          params: mini.params || { temperature: 0.1 },
        })

        const hasAgentConfig = agent.model_id && agent.model_id.trim()
        if (hasAgentConfig) {
          const found = findProviderByModelId(agent.model_id, agent.api_base)
          if (found) {
            setSelectedAgentProvider(found.providerKey)
            setSelectedAgentModel(found.modelKey)
            setAgentSourceType('preset')
          } else {
            setAgentSourceType('custom')
            setCustomAgentBase(agent.api_base)
            setCustomAgentModelId(agent.model_id)
          }
        }

        const hasMiniConfig = mini.model_id && mini.model_id.trim()
        if (hasMiniConfig) {
          const found = findProviderByModelId(mini.model_id, mini.api_base)
          if (found) {
            setSelectedMiniProvider(found.providerKey)
            setSelectedMiniModel(found.modelKey)
            setMiniSourceType('preset')
          } else {
            setMiniSourceType('custom')
            setCustomMiniBase(mini.api_base)
            setCustomMiniModelId(mini.model_id)
          }
        }
      }
    } catch (err: any) {
      setError(err.message || t('settings.llmConfigTab.agentSaveFailed'))
    } finally {
      setLoading(false)
    }
  }

  const findModel = (modelKey: string): { provider: PresetProvider; model: PresetModel } | null => {
    for (const provider of providers) {
      const model = provider.models.find((m) => m.key === modelKey)
      if (model) return { provider, model }
    }
    return null
  }

  const handleAgentProviderSelect = (providerKey: string) => {
    setSelectedAgentProvider(providerKey)
    setSelectedAgentModel('')
    const provider = providers.find((p) => p.provider === providerKey)
    if (provider) {
      setAgentModel((prev) => ({
        ...prev,
        type: provider.type || 'openai-compatible',
        api_base: resolvePresetApiBase(provider.api_base, prev.api_base),
      }))
    }
  }

  const handleAgentModelSelect = (modelKey: string) => {
    setSelectedAgentModel(modelKey)
    const found = findModel(modelKey)
    if (found) {
      setAgentModel((prev) => ({
        name: found.model.name,
        type: found.provider.type || 'openai-compatible',
        api_base: resolvePresetApiBase(found.provider.api_base, prev.api_base),
        api_key: '',
        model_id: found.model.model_id,
        api_key_masked: prev.api_key_masked,
        params: found.model.default_params || { temperature: 0.1 },
      }))
    }
  }

  const handleMiniProviderSelect = (providerKey: string) => {
    setSelectedMiniProvider(providerKey)
    setSelectedMiniModel('')
    const provider = providers.find((p) => p.provider === providerKey)
    if (provider) {
      setMiniAgentModel((prev) => ({
        ...prev,
        type: provider.type || 'openai-compatible',
        api_base: resolvePresetApiBase(provider.api_base, prev.api_base),
      }))
    }
  }

  const handleMiniModelSelect = (modelKey: string) => {
    setSelectedMiniModel(modelKey)
    const found = findModel(modelKey)
    if (found) {
      setMiniAgentModel((prev) => ({
        name: found.model.name,
        type: found.provider.type || 'openai-compatible',
        api_base: resolvePresetApiBase(found.provider.api_base, prev.api_base),
        api_key: '',
        model_id: found.model.model_id,
        api_key_masked: prev.api_key_masked,
        params: found.model.default_params || { temperature: 0.1 },
      }))
    }
  }

  const handleAgentCustomChange = (base: string, modelId: string) => {
    setCustomAgentBase(base)
    setCustomAgentModelId(modelId)
    setAgentModel((prev) => ({
      ...prev,
      api_base: base,
      model_id: modelId,
      type: 'openai-compatible',
      name: modelId || 'Custom Model',
    }))
  }

  const handleMiniCustomChange = (base: string, modelId: string) => {
    setCustomMiniBase(base)
    setCustomMiniModelId(modelId)
    setMiniAgentModel((prev) => ({
      ...prev,
      api_base: base,
      model_id: modelId,
      type: 'openai-compatible',
      name: modelId || 'Custom Model',
    }))
  }

  const validateModel = (
    formState: ModelFormState,
    label: string,
    allowEmptyKey: boolean = false
  ): string | null => {
    if (!formState.api_base) return `${label}: ${t('settings.llmConfigTab.pleaseConfigureAgent')}`
    if (isEditableApiBase(formState.api_base)) {
      return `${label}: ${t('settings.llmConfigTab.replacePlaceholder')}`
    }
    if (!allowEmptyKey && !formState.api_key) return `${label}: ${t('settings.llmConfigTab.pleaseConfigureAgent')}`
    if (!formState.model_id) return `${label}: ${t('settings.llmConfigTab.pleaseConfigureAgent')}`
    return null
  }

  const buildAgentRequest = (): UpdateLLMConfigRequest['agent_model'] => ({
    name: agentModel.name,
    type: agentModel.type,
    api_base: agentModel.api_base,
    api_key: agentModel.api_key,
    model_id: agentModel.model_id,
    params: agentModel.params,
  })

  const buildMiniRequest = (): UpdateLLMConfigRequest['mini_agent_model'] => ({
    name: miniAgentModel.name,
    type: miniAgentModel.type,
    api_base: miniAgentModel.api_base,
    api_key: miniAgentModel.api_key,
    model_id: miniAgentModel.model_id,
    params: miniAgentModel.params,
  })

  const handleTestConnection = async (
    formState: ModelFormState,
    label: string,
    setTesting: (v: boolean) => void,
    setStatus: (v: { ok: boolean; message: string } | null) => void
  ) => {
    const allowEmptyKey = !!formState.api_key_masked && !formState.api_key
    const validationError = validateModel(formState, label, allowEmptyKey)
    if (validationError) {
      setStatus({ ok: false, message: validationError })
      return
    }
    setTesting(true)
    setStatus(null)
    try {
      await testLLMConnection({
        api_base: formState.api_base,
        model_id: formState.model_id,
        api_key: formState.api_key,
      })
      setStatus({ ok: true, message: t('settings.llmConfigTab.testSuccess') })
    } catch (err: any) {
      setStatus({
        ok: false,
        message: err.message || t('settings.llmConfigTab.testFailed', { label }),
      })
    } finally {
      setTesting(false)
    }
  }

  const handleSaveAgent = async () => {
    const allowEmptyKey = !!agentModel.api_key_masked && !agentModel.api_key
    const agentError = validateModel(agentModel, t('settings.llmConfigTab.agentModel'), allowEmptyKey)
    if (agentError) {
      showError(agentError)
      return
    }
    setSaving(true)
    try {
      await updateAgentModelConfig(buildAgentRequest())
      showSuccess(t('settings.llmConfigTab.agentSaveSuccess'))
      await loadData()
    } catch (err: any) {
      showError(err.message || t('settings.llmConfigTab.agentSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveMini = async () => {
    const allowEmptyKey = !!miniAgentModel.api_key_masked && !miniAgentModel.api_key
    const miniError = validateModel(miniAgentModel, t('settings.llmConfigTab.miniModel'), allowEmptyKey)
    if (miniError) {
      showError(miniError)
      return
    }
    setSaving(true)
    try {
      await updateMiniAgentModelConfig(buildMiniRequest())
      showSuccess(t('settings.llmConfigTab.miniSaveSuccess'))
      await loadData()
    } catch (err: any) {
      showError(err.message || t('settings.llmConfigTab.miniSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleCopyToMini = async () => {
    if (!agentModel.model_id) {
      showError(t('settings.llmConfigTab.pleaseConfigureAgent'))
      return
    }
    setSaving(true)
    try {
      await copyAgentToMini()
      showSuccess(t('settings.llmConfigTab.copiedToMini'))
      await loadData()
    } catch (err: any) {
      showError(err.message || t('settings.llmConfigTab.copyFailed'))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
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

      <ModelConfigCard
        title={t('settings.llmConfigTab.agentModel')}
        description={t('settings.llmConfigTab.agentModelDesc')}
        formState={agentModel}
        setFormState={setAgentModel}
        sourceType={agentSourceType}
        setSourceType={setAgentSourceType}
        selectedProvider={selectedAgentProvider}
        selectedModelKey={selectedAgentModel}
        providers={providers}
        onProviderSelect={handleAgentProviderSelect}
        onModelSelect={handleAgentModelSelect}
        customBase={customAgentBase}
        customModelId={customAgentModelId}
        onCustomChange={handleAgentCustomChange}
        showKey={showAgentKey}
        setShowKey={setShowAgentKey}
        testing={testingAgent}
        saving={saving}
        testStatus={agentTestStatus}
        onTest={() =>
          handleTestConnection(
            agentModel,
            t('settings.llmConfigTab.agentModel'),
            setTestingAgent,
            setAgentTestStatus
          )
        }
        onSave={handleSaveAgent}
        extraActions={
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopyToMini}
            disabled={saving || !agentModel.model_id}
          >
            {t('settings.llmConfigTab.copyAgentToMini')}
          </Button>
        }
      />

      <ModelConfigCard
        title={t('settings.llmConfigTab.miniModel')}
        description={t('settings.llmConfigTab.miniModelDesc')}
        formState={miniAgentModel}
        setFormState={setMiniAgentModel}
        sourceType={miniSourceType}
        setSourceType={setMiniSourceType}
        selectedProvider={selectedMiniProvider}
        selectedModelKey={selectedMiniModel}
        providers={providers}
        onProviderSelect={handleMiniProviderSelect}
        onModelSelect={handleMiniModelSelect}
        customBase={customMiniBase}
        customModelId={customMiniModelId}
        onCustomChange={handleMiniCustomChange}
        showKey={showMiniKey}
        setShowKey={setShowMiniKey}
        testing={testingMini}
        saving={saving}
        testStatus={miniTestStatus}
        onTest={() =>
          handleTestConnection(
            miniAgentModel,
            t('settings.llmConfigTab.miniModel'),
            setTestingMini,
            setMiniTestStatus
          )
        }
        onSave={handleSaveMini}
      />
    </div>
  )
}