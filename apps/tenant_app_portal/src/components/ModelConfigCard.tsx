import type { Dispatch, ReactNode, SetStateAction } from 'react'
import { useTranslation } from 'react-i18next'
import SettingsSection from '@/components/SettingsSection'
import i18n from '@/i18n/config'
import { Button } from '@/components/ui/button'

i18n.addResourceBundle('en', 'translation', {
  components: {
    modelConfigCard: {
      configMode: 'Config Mode',
      presetModel: 'Preset Model',
      customModel: 'Custom Model',
      selectProvider: 'Select Provider',
      selectModel: 'Select Model',
      apiKey: 'API Key',
      apiBase: 'API Base',
      apiBasePlaceholder: 'https://<workspace>.cloud.databricks.com/ai-gateway/mlflow/v1',
      currentKey: 'Current: {{key}}',
      params: 'Parameters',
      optional: 'Optional',
      testing: 'Testing...',
      testConnection: 'Test Connection',
      saving: 'Saving...',
      save: 'Save',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    modelConfigCard: {
      configMode: '配置模式',
      presetModel: '预设模型',
      customModel: '自定义模型',
      selectProvider: '选择提供商',
      selectModel: '选择模型',
      apiKey: 'API 密钥',
      apiBase: 'API Base',
      apiBasePlaceholder: 'https://<workspace>.cloud.databricks.com/ai-gateway/mlflow/v1',
      currentKey: '当前: {{key}}',
      params: '参数',
      optional: '可选',
      testing: '测试中...',
      testConnection: '测试连接',
      saving: '保存中...',
      save: '保存',
    },
  },
}, true, true)
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { isEditableApiBase, type PresetModel, type PresetProvider } from '@/lib/tenantApi'
import { Eye, EyeOff, Loader2, Plug, Save, Settings2 } from 'lucide-react'

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

interface ModelConfigCardProps {
  title: string
  description: string
  formState: ModelFormState
  setFormState: Dispatch<SetStateAction<ModelFormState>>
  sourceType: ModelSourceType
  setSourceType: (type: ModelSourceType) => void
  selectedProvider: string
  selectedModelKey: string
  providers: PresetProvider[]
  onProviderSelect: (key: string) => void
  onModelSelect: (key: string) => void
  customBase: string
  customModelId: string
  onCustomChange: (base: string, modelId: string) => void
  showKey: boolean
  setShowKey: (v: boolean) => void
  testing: boolean
  saving: boolean
  onTest: () => void
  onSave: () => void
  extraActions?: ReactNode
  testStatus?: { ok: boolean; message: string } | null
}

export default function ModelConfigCard({
  title,
  description,
  formState,
  setFormState,
  sourceType,
  setSourceType,
  selectedProvider,
  selectedModelKey,
  providers,
  onProviderSelect,
  onModelSelect,
  customBase,
  customModelId,
  onCustomChange,
  showKey,
  setShowKey,
  testing,
  saving,
  onTest,
  onSave,
  extraActions,
  testStatus,
}: ModelConfigCardProps) {
  const { t } = useTranslation()
  const selectedProviderMeta = providers.find((p) => p.provider === selectedProvider)
  const availableModels = selectedProviderMeta?.models || []
  const isPreset = sourceType === 'preset'
  const showPresetApiBase = isPreset && !!selectedProvider && isEditableApiBase(selectedProviderMeta?.api_base)

  return (
    <SettingsSection title={title} description={description}>
      <div className="space-y-4">

      {/* Row 1: Config Mode */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <Label className="min-w-[100px] shrink-0">{t('components.modelConfigCard.configMode')}</Label>
        <Select value={sourceType} onValueChange={(v) => setSourceType(v as ModelSourceType)}>
          <SelectTrigger className="flex-1">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="preset">{t('components.modelConfigCard.presetModel')}</SelectItem>
            <SelectItem value="custom">{t('components.modelConfigCard.customModel')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isPreset ? (
        <>
          {/* Row 2: Provider + Model (inline) */}
          {selectedProvider ? (
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <Label className="min-w-[100px] shrink-0">Provider</Label>
              <Select value={selectedProvider} onValueChange={onProviderSelect}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder={t('components.modelConfigCard.selectProvider')} />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.provider} value={provider.provider}>
                      {provider.name || provider.provider}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Label className="min-w-[60px] shrink-0 sm:ml-2">{t('components.modelConfigCard.selectModel')}</Label>
              <Select value={selectedModelKey} onValueChange={onModelSelect}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder={t('components.modelConfigCard.selectModel')} />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((model: PresetModel) => (
                    <SelectItem key={model.key} value={model.key}>
                      <div className="flex flex-col">
                        <span className="font-medium">{model.name}</span>
                        <span className="text-xs text-muted-foreground">{model.model_id}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <Label className="min-w-[100px] shrink-0">{t('components.modelConfigCard.selectProvider')}</Label>
              <Select value={selectedProvider} onValueChange={onProviderSelect}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder={t('components.modelConfigCard.selectProvider')} />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.provider} value={provider.provider}>
                      {provider.name || provider.provider}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {showPresetApiBase && (
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <Label className="min-w-[100px] shrink-0">{t('components.modelConfigCard.apiBase')}</Label>
              <Input
                value={formState.api_base}
                onChange={(e) =>
                  setFormState((prev) => ({ ...prev, api_base: e.target.value }))
                }
                placeholder={
                  selectedProviderMeta?.api_base || t('components.modelConfigCard.apiBasePlaceholder')
                }
                className="flex-1"
              />
            </div>
          )}

          {/* Row 3: API Key */}
          {selectedModelKey && (
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <Label className="min-w-[100px] shrink-0">{t('components.modelConfigCard.apiKey')}</Label>
              <div className="flex-1 relative">
                <Input
                  type={showKey ? 'text' : 'password'}
                  value={formState.api_key}
                  onChange={(e) =>
                    setFormState((prev) => ({ ...prev, api_key: e.target.value }))
                  }
                  placeholder={t('components.modelConfigCard.apiKey')}
                  className="pr-10"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                  onClick={() => setShowKey(!showKey)}
                >
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              {formState.api_key_masked && !formState.api_key && (
                <p className="text-xs text-muted-foreground sm:ml-2 whitespace-nowrap">
                  {t('components.modelConfigCard.currentKey', { key: formState.api_key_masked })}
                </p>
              )}
            </div>
          )}

          {/* Row 4: Model Params */}
          {selectedModelKey && (
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <div className="flex items-center gap-2 min-w-[100px] shrink-0">
                <Settings2 className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">{t('components.modelConfigCard.params')}</span>
              </div>
              <div className="flex-1 grid grid-cols-3 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Temperature</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={formState.params?.temperature ?? 0.1}
                    onChange={(e) =>
                      setFormState((prev) => ({
                        ...prev,
                        params: {
                          ...prev.params,
                          temperature: parseFloat(e.target.value) || 0.1,
                        },
                      }))
                    }
                    placeholder="0.1"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Max Tokens</Label>
                  <Input
                    type="number"
                    min="1"
                    value={formState.params?.max_tokens ?? ''}
                    onChange={(e) =>
                      setFormState((prev) => ({
                        ...prev,
                        params: {
                          ...prev.params,
                          max_tokens: parseInt(e.target.value) || undefined,
                        },
                      }))
                    }
                    placeholder={t('components.modelConfigCard.optional')}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Top P</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min="0"
                    max="1"
                    value={formState.params?.top_p ?? ''}
                    onChange={(e) =>
                      setFormState((prev) => ({
                        ...prev,
                        params: {
                          ...prev.params,
                          top_p: parseFloat(e.target.value) || undefined,
                        },
                      }))
                    }
                    placeholder={t('components.modelConfigCard.optional')}
                  />
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          {/* Row 2: API Base + Model ID (inline) */}
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
            <Label className="min-w-[100px] shrink-0">API Base</Label>
            <Input
              value={customBase}
              onChange={(e) => onCustomChange(e.target.value, customModelId)}
              placeholder="https://api.example.com/v1"
              className="flex-1"
            />

            <Label className="min-w-[60px] shrink-0 sm:ml-2">Model</Label>
            <Input
              value={customModelId}
              onChange={(e) => onCustomChange(customBase, e.target.value)}
              placeholder="gpt-4"
              className="flex-1"
            />
          </div>

          {/* Row 3: API Key */}
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
            <Label className="min-w-[100px] shrink-0">API Key</Label>
            <div className="flex-1 relative">
              <Input
                type={showKey ? 'text' : 'password'}
                value={formState.api_key}
                onChange={(e) =>
                  setFormState((prev) => ({ ...prev, api_key: e.target.value }))
                }
                placeholder={t('components.modelConfigCard.apiKey')}
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </div>

          {/* Row 4: Model Params */}
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
            <div className="flex items-center gap-2 min-w-[100px] shrink-0">
              <Settings2 className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">{t('components.modelConfigCard.params')}</span>
            </div>
            <div className="flex-1 grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Temperature</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={formState.params?.temperature ?? 0.1}
                  onChange={(e) =>
                    setFormState((prev) => ({
                      ...prev,
                      params: {
                        ...prev.params,
                        temperature: parseFloat(e.target.value) || 0.1,
                      },
                    }))
                  }
                  placeholder="0.1"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Max Tokens</Label>
                <Input
                  type="number"
                  min="1"
                  value={formState.params?.max_tokens ?? ''}
                  onChange={(e) =>
                    setFormState((prev) => ({
                      ...prev,
                      params: {
                        ...prev.params,
                        max_tokens: parseInt(e.target.value) || undefined,
                      },
                    }))
                  }
                    placeholder={t('components.modelConfigCard.optional')}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Top P</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min="0"
                    max="1"
                    value={formState.params?.top_p ?? ''}
                    onChange={(e) =>
                      setFormState((prev) => ({
                        ...prev,
                        params: {
                          ...prev.params,
                          top_p: parseFloat(e.target.value) || undefined,
                        },
                      }))
                    }
                    placeholder={t('components.modelConfigCard.optional')}
                />
              </div>
            </div>
          </div>
        </>
      )}

      {/* Inline action buttons */}
      <div className="flex gap-2 pt-2">
        <Button variant="outline" onClick={onTest} disabled={testing || !formState.model_id} className="flex-1">
          {testing ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('components.modelConfigCard.testing')}
            </>
          ) : (
            <>
              <Plug className="mr-2 h-4 w-4" />
              {t('components.modelConfigCard.testConnection')}
            </>
          )}
        </Button>

        <Button onClick={onSave} disabled={saving || !formState.model_id} className="flex-1">
          {saving ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('components.modelConfigCard.saving')}
            </>
          ) : (
            <>
              <Save className="mr-2 h-4 w-4" />
              {t('components.modelConfigCard.save')}
            </>
          )}
        </Button>
      </div>
      {testStatus ? (
        <p className={`text-sm ${testStatus.ok ? 'text-success' : 'text-destructive'}`}>
          {testStatus.message}
        </p>
      ) : null}
      {extraActions ? <div className="pt-1">{extraActions}</div> : null}
      </div>
    </SettingsSection>
  )
}