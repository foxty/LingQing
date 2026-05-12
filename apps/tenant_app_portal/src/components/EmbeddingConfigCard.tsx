import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import SettingsSection from '@/components/SettingsSection'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { PresetModel, PresetProvider } from '@/lib/tenantApi'
import { Eye, EyeOff, Loader2, Plug, Save } from 'lucide-react'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      embeddingConfigCard: {
        configMode: 'Config Mode',
        presetModel: 'Preset Model',
        customModel: 'Custom Model',
        selectProvider: 'Select Provider',
        selectModel: 'Select Model',
        apiKey: 'API Key',
        currentKey: 'Current: {{key}}',
        testing: 'Testing...',
        testConnection: 'Test Connection',
        saving: 'Saving...',
        save: 'Save',
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
    components: {
      embeddingConfigCard: {
        configMode: '配置模式',
        presetModel: '预设模型',
        customModel: '自定义模型',
        selectProvider: '选择提供商',
        selectModel: '选择模型',
        apiKey: 'API 密钥',
        currentKey: '当前: {{key}}',
        testing: '测试中...',
        testConnection: '测试连接',
        saving: '保存中...',
        save: '保存',
      },
    },
  },
  true,
  true
)

export interface EmbeddingFormState {
  name: string
  type: string
  api_base: string
  api_key: string
  model_id: string
  api_key_masked?: string
}

export type EmbeddingSourceType = 'preset' | 'custom'

interface EmbeddingConfigCardProps {
  title: string
  description: string
  formState: EmbeddingFormState
  setFormState: (state: EmbeddingFormState) => void
  sourceType: EmbeddingSourceType
  setSourceType: (type: EmbeddingSourceType) => void
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
  testStatus?: { ok: boolean; message: string } | null
}

export default function EmbeddingConfigCard({
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
  testStatus,
}: EmbeddingConfigCardProps) {
  const { t } = useTranslation()
  const availableModels = providers.find((p) => p.provider === selectedProvider)?.models || []
  const isPreset = sourceType === 'preset'
  const canTest = Boolean(formState.model_id && formState.api_base && formState.api_key)
  const canSave = Boolean(formState.model_id && formState.api_base && (formState.api_key || formState.api_key_masked))

  return (
    <SettingsSection title={title} description={description}>
      <div className="space-y-4">

      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <Label className="min-w-[100px] shrink-0">{t('components.embeddingConfigCard.configMode')}</Label>
        <Select value={sourceType} onValueChange={(v) => setSourceType(v as EmbeddingSourceType)}>
          <SelectTrigger className="flex-1">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="preset">{t('components.embeddingConfigCard.presetModel')}</SelectItem>
            <SelectItem value="custom">{t('components.embeddingConfigCard.customModel')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isPreset ? (
        <>
          {selectedProvider ? (
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <Label className="min-w-[100px] shrink-0">{t('components.embeddingConfigCard.selectProvider')}</Label>
              <Select value={selectedProvider} onValueChange={onProviderSelect}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder={t('components.embeddingConfigCard.selectProvider')} />
                </SelectTrigger>
                <SelectContent>
                  {providers
                    .filter((provider) => provider.models.length > 0)
                    .map((provider) => (
                      <SelectItem key={provider.provider} value={provider.provider}>
                        {provider.name || provider.provider}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              <Label className="min-w-[60px] shrink-0 sm:ml-2">
                {t('components.embeddingConfigCard.selectModel')}
              </Label>
              <Select value={selectedModelKey} onValueChange={onModelSelect}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder={t('components.embeddingConfigCard.selectModel')} />
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
              <Label className="min-w-[100px] shrink-0">{t('components.embeddingConfigCard.selectProvider')}</Label>
              <Select value={selectedProvider} onValueChange={onProviderSelect}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder={t('components.embeddingConfigCard.selectProvider')} />
                </SelectTrigger>
                <SelectContent>
                  {providers
                    .filter((provider) => provider.models.length > 0)
                    .map((provider) => (
                      <SelectItem key={provider.provider} value={provider.provider}>
                        {provider.name || provider.provider}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {selectedModelKey && (
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <Label className="min-w-[100px] shrink-0">{t('components.embeddingConfigCard.apiKey')}</Label>
              <div className="flex-1 relative">
                <Input
                  type={showKey ? 'text' : 'password'}
                  value={formState.api_key}
                  onChange={(e) => setFormState({ ...formState, api_key: e.target.value })}
                  placeholder={t('components.embeddingConfigCard.apiKey')}
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
                  {t('components.embeddingConfigCard.currentKey', { key: formState.api_key_masked })}
                </p>
              )}
            </div>
          )}
        </>
      ) : (
        <>
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
              placeholder="text-embedding-3-small"
              className="flex-1"
            />
          </div>

          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
            <Label className="min-w-[100px] shrink-0">{t('components.embeddingConfigCard.apiKey')}</Label>
            <div className="flex-1 relative">
              <Input
                type={showKey ? 'text' : 'password'}
                value={formState.api_key}
                onChange={(e) => setFormState({ ...formState, api_key: e.target.value })}
                placeholder={t('components.embeddingConfigCard.apiKey')}
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
                {t('components.embeddingConfigCard.currentKey', { key: formState.api_key_masked })}
              </p>
            )}
          </div>
        </>
      )}

      <div className="flex gap-2 pt-2">
        <Button variant="outline" onClick={onTest} disabled={testing || !canTest} className="flex-1">
          {testing ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('components.embeddingConfigCard.testing')}
            </>
          ) : (
            <>
              <Plug className="mr-2 h-4 w-4" />
              {t('components.embeddingConfigCard.testConnection')}
            </>
          )}
        </Button>

        <Button
          onClick={onSave}
          disabled={saving || !canSave}
          className="flex-1"
        >
          {saving ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('components.embeddingConfigCard.saving')}
            </>
          ) : (
            <>
              <Save className="mr-2 h-4 w-4" />
              {t('components.embeddingConfigCard.save')}
            </>
          )}
        </Button>
      </div>
      {testStatus ? (
        <p className={`text-sm ${testStatus.ok ? 'text-success' : 'text-destructive'}`}>
          {testStatus.message}
        </p>
      ) : null}
      </div>
    </SettingsSection>
  )
}
