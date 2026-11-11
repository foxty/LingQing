import { catalogModelHasReasoningControl } from '@/components/models-registry/utils'
import ConnectionTestFeedback, { type ConnectionTestResult } from '@/components/ConnectionTestFeedback'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import { getApiErrorMessage } from '@/lib/api'
import {
  catalogModelsForProvider,
  CUSTOM_CATALOG_MODEL_KEY,
  testRegistryProfileConnection,
  updateRegistryProfile,
  type CatalogProvider,
  type LLMModelProfile,
  type LLMProvider,
  type ModelReasoningConfig,
} from '@/lib/llmConfigApi'
import { cn } from '@/lib/utils'
import { AlertCircle, Loader2, Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { modelsRegistryKey, registerModelsRegistryI18n } from './i18n'
import {
  parseOptionalFloat,
  parseOptionalInt,
  profileDefaultThinkingEffort,
  profileReasoningOptionDrafts,
  summarizeConnectionTestMessage,
  type ReasoningOptionDraft,
} from './utils'

function initialCatalogModelKey(
  profile: LLMModelProfile,
  catalogModels: { key: string; model_id: string }[]
): string {
  if (profile.catalog_model_key) {
    return profile.catalog_model_key
  }
  if (profile.source === 'custom') {
    return CUSTOM_CATALOG_MODEL_KEY
  }
  const match = catalogModels.find((model) => model.model_id === profile.model_id)
  return match?.key ?? CUSTOM_CATALOG_MODEL_KEY
}

interface ProfileEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  profile: LLMModelProfile | null
  provider: LLMProvider | null
  catalog: CatalogProvider[]
  onSaved: () => Promise<void> | void
}

export default function ProfileEditDialog({
  open,
  onOpenChange,
  profile,
  provider,
  catalog,
  onSaved,
}: ProfileEditDialogProps) {
  registerModelsRegistryI18n()
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [catalogModelKey, setCatalogModelKey] = useState('')
  const [modelId, setModelId] = useState('')
  const [temperature, setTemperature] = useState('')
  const [maxTokens, setMaxTokens] = useState('')
  const [topP, setTopP] = useState('')
  const [supportsThinking, setSupportsThinking] = useState(false)
  const [reasoningOptions, setReasoningOptions] = useState<ReasoningOptionDraft[]>([
    { value: '', name: '' },
  ])
  const [defaultThinkingEffort, setDefaultThinkingEffort] = useState('')
  const [busy, setBusy] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionTestResult, setConnectionTestResult] = useState<ConnectionTestResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const catalogModels = useMemo(() => {
    if (!profile || !provider) {
      return []
    }
    return catalogModelsForProvider(provider, catalog, profile.category)
  }, [profile, provider, catalog])

  const useCatalogPicker = catalogModels.length > 0
  const isCustomModel = catalogModelKey === CUSTOM_CATALOG_MODEL_KEY || !useCatalogPicker

  useEffect(() => {
    if (!open || !profile) {
      return
    }
    setError(null)
    setConnectionTestResult(null)
    setName(profile.name)
    setModelId(profile.model_id)
    setCatalogModelKey(initialCatalogModelKey(profile, catalogModels))
    const params = profile.params ?? {}
    setTemperature(params.temperature != null ? String(params.temperature) : '')
    setMaxTokens(params.max_tokens != null ? String(params.max_tokens) : '')
    setTopP(params.top_p != null ? String(params.top_p) : '')
    setSupportsThinking(profile.reasoning_config?.supports_thinking === true)
    setReasoningOptions(profileReasoningOptionDrafts(profile))
    setDefaultThinkingEffort(profileDefaultThinkingEffort(profile))
  }, [open, profile?.id, catalogModels])

  const reasoningOptionRows = reasoningOptions
    .map((row) => {
      const value = row.value.trim()
      if (!value) {
        return null
      }
      const label = row.name.trim()
      return { value, name: label || value }
    })
    .filter((row): row is { value: string; name: string } => row !== null)

  const buildParams = (): Record<string, unknown> => {
    const params: Record<string, unknown> = {}
    const temp = parseOptionalFloat(temperature)
    const max = parseOptionalInt(maxTokens)
    const top = parseOptionalFloat(topP)
    if (temp !== undefined) {
      params.temperature = temp
    }
    if (max !== undefined) {
      params.max_tokens = max
    }
    if (top !== undefined) {
      params.top_p = top
    }
    return params
  }

  const buildReasoningConfig = (): ModelReasoningConfig | null => {
    if (profile?.category !== 'llm') {
      return null
    }
    const base = { ...(profile.reasoning_config ?? {}) }
    if (!supportsThinking) {
      return { ...base, supports_thinking: false, thinking_effort_options: [] }
    }
    const thinking_effort_options = reasoningOptionRows
    const result: ModelReasoningConfig = {
      ...base,
      supports_thinking: true,
      thinking_effort_options,
    }
    const defaultWire = defaultThinkingEffort.trim()
    if (
      defaultWire &&
      thinking_effort_options.some((option) => option.value === defaultWire)
    ) {
      result.default_thinking_effort = defaultWire
    } else {
      delete result.default_thinking_effort
    }
    return result
  }

  const buildIdentityPayload = () => {
    const trimmedModelId = modelId.trim()
    const custom = isCustomModel
    return {
      model_id: trimmedModelId,
      catalog_model_key: custom ? null : catalogModelKey || null,
      source: custom ? 'custom' : 'preset',
    }
  }

  const validateReasoning = (): string | null => {
    if (profile?.category !== 'llm' || !supportsThinking) {
      return null
    }
    const hasValue = reasoningOptions.some((row) => row.value.trim())
    if (!hasValue) {
      return t(modelsRegistryKey('reasoningOptionsEmpty'))
    }
    return null
  }

  const validateModelId = (): string | null => {
    if (!modelId.trim()) {
      return t(modelsRegistryKey('modelIdRequired'))
    }
    if (!isCustomModel && !catalogModelKey.trim()) {
      return t(modelsRegistryKey('selectModel'))
    }
    return null
  }

  const persistProfile = async (resetFromCatalog: boolean): Promise<boolean> => {
    if (!profile) {
      return false
    }
    const modelError = validateModelId()
    if (modelError) {
      setError(modelError)
      return false
    }
    if (!resetFromCatalog) {
      const validationError = validateReasoning()
      if (validationError) {
        setError(validationError)
        return false
      }
    }
    setError(null)
    await updateRegistryProfile(profile.id, {
      name: name.trim(),
      ...buildIdentityPayload(),
      params: resetFromCatalog ? undefined : buildParams(),
      reasoning_config: resetFromCatalog ? undefined : buildReasoningConfig(),
      reset_runtime_from_catalog: resetFromCatalog,
    })
    return true
  }

  const testConnection = async () => {
    if (!profile || testingConnection || busy) {
      return
    }
    setTestingConnection(true)
    setConnectionTestResult(null)
    setError(null)
    try {
      const persisted = await persistProfile(false)
      if (!persisted) {
        return
      }
      const result = await testRegistryProfileConnection(profile.id)
      setConnectionTestResult({
        ok: true,
        message: result.message || t(modelsRegistryKey('testSuccess')),
      })
    } catch (err) {
      const raw = getApiErrorMessage(err, t(modelsRegistryKey('testFailed')))
      setConnectionTestResult({
        ok: false,
        message: summarizeConnectionTestMessage(raw),
      })
    } finally {
      setTestingConnection(false)
    }
  }

  const save = async (resetFromCatalog: boolean) => {
    if (!profile) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const persisted = await persistProfile(resetFromCatalog)
      if (!persisted) {
        return
      }
      onOpenChange(false)
      await onSaved()
    } catch (err) {
      setError(getApiErrorMessage(err, t(modelsRegistryKey('saveFailed'))))
    } finally {
      setBusy(false)
    }
  }

  const updateOption = (index: number, patch: Partial<ReasoningOptionDraft>) => {
    setReasoningOptions((rows) => {
      const next = rows.map((row, i) => (i === index ? { ...row, ...patch } : row))
      const values = next.map((row) => row.value.trim()).filter(Boolean)
      setDefaultThinkingEffort((current) => {
        if (current && values.includes(current)) {
          return current
        }
        return values[0] ?? ''
      })
      return next
    })
    setConnectionTestResult(null)
  }

  const addOption = () => {
    setReasoningOptions((rows) => [...rows, { value: '', name: '' }])
    setConnectionTestResult(null)
  }

  const removeOption = (index: number) => {
    setReasoningOptions((rows) => {
      if (rows.length <= 1) {
        return [{ value: '', name: '' }]
      }
      return rows.filter((_, i) => i !== index)
    })
    setConnectionTestResult(null)
  }

  const clearTestOnFieldChange = () => {
    setConnectionTestResult(null)
  }

  const canSave = name.trim() && modelId.trim() && !busy && !testingConnection

  if (!profile) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] w-[calc(100%-2rem)] max-w-2xl flex-col gap-0 overflow-hidden p-0 sm:w-full">
        <DialogHeader className="space-y-1.5 px-6 py-4 text-left">
          <DialogTitle>{t(modelsRegistryKey('editModelProfile'))}</DialogTitle>
          <DialogDescription className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">{t(modelsRegistryKey('profileIdHint'), { id: profile.id })}</span>
            <Badge variant="outline" className="font-normal">
              {profile.category === 'embedding'
                ? t(modelsRegistryKey('categoryEmbedding'))
                : t(modelsRegistryKey('categoryLlm'))}
            </Badge>
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 pb-4">
          {error ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="profile-edit-name">{t(modelsRegistryKey('profileName'))}</Label>
            <Input
              id="profile-edit-name"
              value={name}
              onChange={(event) => {
                setName(event.target.value)
                clearTestOnFieldChange()
              }}
            />
          </div>

          {useCatalogPicker ? (
            <div className="space-y-2">
              <Label>{t(modelsRegistryKey('selectModel'))}</Label>
              <Select
                value={catalogModelKey || undefined}
                onValueChange={(value) => {
                  if (value === CUSTOM_CATALOG_MODEL_KEY) {
                    setCatalogModelKey(CUSTOM_CATALOG_MODEL_KEY)
                    setModelId('')
                    clearTestOnFieldChange()
                    return
                  }
                  const model = catalogModels.find((item) => item.key === value)
                  setCatalogModelKey(value)
                  if (model?.model_id) {
                    setModelId(model.model_id)
                  }
                  clearTestOnFieldChange()
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t(modelsRegistryKey('selectModel'))} />
                </SelectTrigger>
                <SelectContent>
                  {catalogModels.map((model) => (
                    <SelectItem key={model.key} value={model.key}>
                      {model.name} ({model.model_id})
                      {catalogModelHasReasoningControl(model)
                        ? ` · ${t(modelsRegistryKey('badgeReasoningControl'))}`
                        : ''}
                    </SelectItem>
                  ))}
                  <SelectItem value={CUSTOM_CATALOG_MODEL_KEY}>{t(modelsRegistryKey('customModel'))}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ) : null}

          {isCustomModel ? (
            <div className="space-y-2">
              <Label htmlFor="profile-edit-model-id">{t(modelsRegistryKey('modelId'))}</Label>
              <Input
                id="profile-edit-model-id"
                className="font-mono text-sm"
                value={modelId}
                onChange={(event) => {
                  setModelId(event.target.value)
                  if (useCatalogPicker) {
                    setCatalogModelKey(CUSTOM_CATALOG_MODEL_KEY)
                  }
                  clearTestOnFieldChange()
                }}
              />
              <p className="text-xs text-muted-foreground">{t(modelsRegistryKey('customModelHint'))}</p>
            </div>
          ) : modelId ? (
            <div className="space-y-1">
              <Label>{t(modelsRegistryKey('modelId'))}</Label>
              <p className="font-mono text-sm text-muted-foreground">{modelId}</p>
            </div>
          ) : null}

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="profile-edit-temperature">{t(modelsRegistryKey('paramTemperature'))}</Label>
              <Input
                id="profile-edit-temperature"
                inputMode="decimal"
                className="tabular-nums"
                value={temperature}
                onChange={(event) => {
                  setTemperature(event.target.value)
                  clearTestOnFieldChange()
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-edit-max-tokens">{t(modelsRegistryKey('paramMaxTokens'))}</Label>
              <Input
                id="profile-edit-max-tokens"
                inputMode="numeric"
                className="tabular-nums"
                value={maxTokens}
                onChange={(event) => {
                  setMaxTokens(event.target.value)
                  clearTestOnFieldChange()
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-edit-top-p">{t(modelsRegistryKey('paramTopP'))}</Label>
              <Input
                id="profile-edit-top-p"
                inputMode="decimal"
                className="tabular-nums"
                value={topP}
                onChange={(event) => {
                  setTopP(event.target.value)
                  clearTestOnFieldChange()
                }}
              />
            </div>
          </div>

          {profile.category === 'llm' ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="supports-thinking"
                  checked={supportsThinking}
                  onCheckedChange={(checked) => {
                    setSupportsThinking(checked === true)
                    clearTestOnFieldChange()
                  }}
                />
                <Label htmlFor="supports-thinking" className="font-normal">
                  {t(modelsRegistryKey('supportsThinking'))}
                </Label>
              </div>
              {supportsThinking ? (
                <div className="space-y-3 pl-6">
                  <div className="space-y-2">
                    <Label>{t(modelsRegistryKey('reasoningOptions'))}</Label>
                    <div className="space-y-2">
                      {reasoningOptions.map((row, index) => (
                        <div key={index} className="flex items-start gap-2">
                          <div className="grid flex-1 grid-cols-2 gap-2">
                            <Input
                              className="font-mono text-sm"
                              placeholder={t(modelsRegistryKey('reasoningOptionValue'))}
                              value={row.value}
                              onChange={(event) => updateOption(index, { value: event.target.value })}
                            />
                            <Input
                              className="text-sm"
                              placeholder={t(modelsRegistryKey('reasoningOptionName'))}
                              value={row.name}
                              onChange={(event) => updateOption(index, { name: event.target.value })}
                            />
                          </div>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9 shrink-0"
                            aria-label={t(modelsRegistryKey('removeReasoningOption'))}
                            onClick={() => removeOption(index)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      ))}
                    </div>
                    <Button type="button" variant="outline" size="sm" onClick={addOption}>
                      <Plus className="mr-1 h-4 w-4" />
                      {t(modelsRegistryKey('addReasoningOption'))}
                    </Button>
                  </div>
                  {reasoningOptionRows.length > 0 ? (
                    <div className="space-y-2">
                      <Label>{t(modelsRegistryKey('defaultThinkingEffort'))}</Label>
                      <Select
                        value={defaultThinkingEffort || reasoningOptionRows[0]?.value}
                        onValueChange={(value) => {
                          setDefaultThinkingEffort(value)
                          clearTestOnFieldChange()
                        }}
                      >
                        <SelectTrigger className="h-9">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {reasoningOptionRows.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        {t(modelsRegistryKey('reasoningOptionsHint'))}
                      </p>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          <p className="text-xs text-muted-foreground">{t(modelsRegistryKey('runtimeConfigHint'))}</p>
        </div>

        {connectionTestResult ? (
          <div
            className={cn(
              'border-t border-border px-6 py-2.5',
              connectionTestResult.ok ? 'bg-muted/40' : 'bg-destructive/5'
            )}
          >
            <ConnectionTestFeedback
              result={connectionTestResult}
              className="text-sm"
              errorOnNewLine
            />
          </div>
        ) : null}

        <DialogFooter className="gap-2 border-t border-border px-6 py-4 sm:justify-between">
          <Button
            type="button"
            variant="outline"
            disabled={busy || testingConnection}
            onClick={() => void save(true)}
          >
            {t(modelsRegistryKey('resetFromCatalog'))}
          </Button>
          <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row sm:items-center">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t(modelsRegistryKey('cancel'))}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!canSave}
              onClick={() => void testConnection()}
            >
              {testingConnection ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t(modelsRegistryKey('testingConnection'))}
                </>
              ) : (
                t(modelsRegistryKey('test'))
              )}
            </Button>
            <Button type="button" disabled={!canSave} onClick={() => void save(false)}>
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t(modelsRegistryKey('save'))}
                </>
              ) : (
                t(modelsRegistryKey('save'))
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
