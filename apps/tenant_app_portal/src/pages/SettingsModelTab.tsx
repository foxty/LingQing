import i18n from '@/i18n/config'
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useTenantSettings, useAvailableModels } from '@/hooks/useTenantSettings'
import { useNotification } from '@/hooks/useNotification'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Loader2, Save, AlertCircle } from 'lucide-react'
import { ModelInfo, TenantSettings } from '@/lib/tenantApi'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    modelTab: {
      title: 'Default Models',
      description: 'Set default models for Agent and Mini Agent',
      selectModel: 'Select a model',
      defaultAgent: 'Default Agent Model',
      defaultMini: 'Default Mini Agent Model',
      saveSuccess: 'Settings saved',
      saveFailed: 'Save failed',
      saving: 'Saving...',
      saveSettings: 'Save Settings',
      changesReverted: 'Changes reverted',
      modelCatalog: 'Model Catalog',
      modelCatalogDesc: 'Available models from configured providers',
      setAsAgent: 'Set as Agent',
      setAsMini: 'Set as Mini',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    modelTab: {
      title: '默认模型',
      description: '设置 Agent 和 Mini Agent 的默认模型',
      selectModel: '选择模型',
      defaultAgent: '默认 Agent 模型',
      defaultMini: '默认 Mini Agent 模型',
      saveSuccess: '设置已保存',
      saveFailed: '保存失败',
      saving: '保存中...',
      saveSettings: '保存设置',
      changesReverted: '更改已还原',
      modelCatalog: '模型目录',
      modelCatalogDesc: '来自已配置提供商的可用模型',
      setAsAgent: '设为 Agent',
      setAsMini: '设为 Mini',
    }
  }
}, true, true)

export default function SettingsModelTab() {
  const { t } = useTranslation()
  const { showSuccess, showError, showInfo } = useNotification()
  const {
    settings: currentSettings,
    loading: settingsLoading,
    error: settingsError,
    fetchSettings,
    saveSettings,
  } = useTenantSettings()

  const { modelGroups, models, loading: modelsLoading, fetchModels } = useAvailableModels()

  const [formSettings, setFormSettings] = useState<TenantSettings>({
    default_agent_model: '',
    default_mini_agent_model: '',
  })

  const [saving, setSaving] = useState(false)

  // Load data on mount
  useEffect(() => {
    fetchSettings()
    fetchModels()
  }, [])

  // Update form when settings load
  useEffect(() => {
    if (currentSettings) {
      setFormSettings(currentSettings)
    }
  }, [currentSettings])

  const handleSave = async () => {
    setSaving(true)
    try {
      await saveSettings(formSettings)
      showSuccess(t('settings.modelTab.saveSuccess'))
    } catch (error: any) {
      showError(error.message || t('settings.modelTab.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const getModelInfo = (key: string): ModelInfo | undefined => models.find((m) => m.key === key)

  const renderModelSummary = (modelKey: string) => {
    const model = getModelInfo(modelKey)
    if (!model) {
      return null
    }

    return (
      <div className="mt-2 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
        <p className="mb-1 font-medium text-foreground">{model.name}</p>
        {model.description && <p>{model.description}</p>}
      </div>
    )
  }

  const renderModelSelect = (
    id: string,
    label: string,
    selectedKey: string,
    onValueChange: (value: string) => void
  ) => (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select value={selectedKey} onValueChange={onValueChange}>
        <SelectTrigger id={id}>
          <SelectValue placeholder={t('settings.modelTab.selectModel')} />
        </SelectTrigger>
        <SelectContent>
          {modelGroups.map((group, groupIndex) => (
            <div key={group.provider}>
              <SelectGroup>
                <SelectLabel>{group.provider}</SelectLabel>
                {group.models.map((model) => (
                  <SelectItem key={model.key} value={model.key}>
                    <div className="flex flex-col">
                      <span className="font-medium">{model.name}</span>
                      <span className="text-xs text-muted-foreground">{model.key}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectGroup>
              {groupIndex < modelGroups.length - 1 && <SelectSeparator />}
            </div>
          ))}
        </SelectContent>
      </Select>
      {selectedKey && renderModelSummary(selectedKey)}
    </div>
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.modelTab.title')}</CardTitle>
        <CardDescription>{t('settings.modelTab.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {settingsError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{settingsError}</AlertDescription>
          </Alert>
        )}

        {settingsLoading || modelsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div className="space-y-6">
              {renderModelSelect(
                'default_agent_model',
                t('settings.modelTab.defaultAgent'),
                formSettings.default_agent_model,
                (value) => setFormSettings({ ...formSettings, default_agent_model: value })
              )}

              {renderModelSelect(
                'default_mini_agent_model',
                t('settings.modelTab.defaultMini'),
                formSettings.default_mini_agent_model,
                (value) => setFormSettings({ ...formSettings, default_mini_agent_model: value })
              )}

              <div className="flex justify-end space-x-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    if (currentSettings) {
                      setFormSettings(currentSettings)
                      showInfo(t('settings.modelTab.changesReverted'), 2000)
                    }
                  }}
                  disabled={saving}
                >
                  {t('common.cancel')}
                </Button>
                <Button onClick={handleSave} disabled={saving}>
                  {saving ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {t('settings.modelTab.saving')}
                    </>
                  ) : (
                    <>
                      <Save className="mr-2 h-4 w-4" />
                      {t('settings.modelTab.saveSettings')}
                    </>
                  )}
                </Button>
              </div>
            </div>

            <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
              <div>
                <p className="text-sm font-semibold">{t('settings.modelTab.modelCatalog')}</p>
                <p className="text-xs text-muted-foreground">
                  {t('settings.modelTab.modelCatalogDesc')}
                </p>
              </div>
              <div className="space-y-4">
                {modelGroups.map((group) => (
                  <div key={group.provider} className="rounded-md border bg-background p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <p className="text-sm font-medium">{group.provider}</p>
                      <Badge variant="secondary">{group.models.length} models</Badge>
                    </div>
                    <div className="space-y-2">
                      {group.models.map((model) => (
                        <div
                          key={model.key}
                          className="rounded-md border border-dashed px-3 py-2 transition-colors hover:border-solid"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-medium">{model.name}</p>
                              <p className="text-xs text-muted-foreground">{model.key}</p>
                            </div>
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() =>
                                  setFormSettings({
                                    ...formSettings,
                                    default_agent_model: model.key,
                                  })
                                }
                              >
                                 {t('settings.modelTab.setAsAgent')}
                                </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() =>
                                  setFormSettings({
                                    ...formSettings,
                                    default_mini_agent_model: model.key,
                                  })
                                }
                              >
                                 {t('settings.modelTab.setAsMini')}
                                </Button>
                            </div>
                          </div>
                          {model.description && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              {model.description}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
