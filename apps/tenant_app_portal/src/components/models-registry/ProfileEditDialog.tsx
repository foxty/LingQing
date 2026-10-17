import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { getApiErrorMessage } from '@/lib/api'
import {
  updateRegistryProfile,
  type LLMModelProfile,
  type ModelReasoningConfig,
} from '@/lib/llmConfigApi'
import { AlertCircle, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { modelsRegistryKey, registerModelsRegistryI18n } from './i18n'

type ReasoningOptionDraft = {
  value: string
  name: string
}

function parseOptionalFloat(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) {
    return undefined
  }
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : undefined
}

function parseOptionalInt(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) {
    return undefined
  }
  const parsed = Number.parseInt(trimmed, 10)
  return Number.isFinite(parsed) ? parsed : undefined
}

function draftsFromProfile(profile: LLMModelProfile): ReasoningOptionDraft[] {
  const options = profile.reasoning_config?.thinking_effort_options ?? []
  if (!options.length) {
    return [{ value: '', name: '' }]
  }
  return options.map((option) => ({
    value: option.value,
    name: option.name === option.value ? '' : option.name,
  }))
}

interface ProfileEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  profile: LLMModelProfile | null
  onSaved: () => Promise<void> | void
}

export default function ProfileEditDialog({
  open,
  onOpenChange,
  profile,
  onSaved,
}: ProfileEditDialogProps) {
  registerModelsRegistryI18n()
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [temperature, setTemperature] = useState('')
  const [maxTokens, setMaxTokens] = useState('')
  const [topP, setTopP] = useState('')
  const [supportsThinking, setSupportsThinking] = useState(false)
  const [reasoningOptions, setReasoningOptions] = useState<ReasoningOptionDraft[]>([
    { value: '', name: '' },
  ])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !profile) {
      return
    }
    setError(null)
    setName(profile.name)
    const params = profile.params ?? {}
    setTemperature(params.temperature != null ? String(params.temperature) : '')
    setMaxTokens(params.max_tokens != null ? String(params.max_tokens) : '')
    setTopP(params.top_p != null ? String(params.top_p) : '')
    setSupportsThinking(profile.reasoning_config?.supports_thinking === true)
    setReasoningOptions(draftsFromProfile(profile))
  }, [open, profile])

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
    const thinking_effort_options = reasoningOptions
      .map((row) => {
        const value = row.value.trim()
        if (!value) {
          return null
        }
        const label = row.name.trim()
        return { value, name: label || value }
      })
      .filter((row): row is { value: string; name: string } => row !== null)

    return {
      ...base,
      supports_thinking: true,
      thinking_effort_options,
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

  const save = async (resetFromCatalog: boolean) => {
    if (!profile) {
      return
    }
    if (!resetFromCatalog) {
      const validationError = validateReasoning()
      if (validationError) {
        setError(validationError)
        return
      }
    }
    setBusy(true)
    setError(null)
    try {
      await updateRegistryProfile(profile.id, {
        name: name.trim(),
        params: resetFromCatalog ? undefined : buildParams(),
        reasoning_config: resetFromCatalog ? undefined : buildReasoningConfig(),
        reset_runtime_from_catalog: resetFromCatalog,
      })
      onOpenChange(false)
      await onSaved()
    } catch (err) {
      setError(getApiErrorMessage(err, t(modelsRegistryKey('saveFailed'))))
    } finally {
      setBusy(false)
    }
  }

  const updateOption = (index: number, patch: Partial<ReasoningOptionDraft>) => {
    setReasoningOptions((rows) =>
      rows.map((row, i) => (i === index ? { ...row, ...patch } : row))
    )
  }

  const addOption = () => {
    setReasoningOptions((rows) => [...rows, { value: '', name: '' }])
  }

  const removeOption = (index: number) => {
    setReasoningOptions((rows) => {
      if (rows.length <= 1) {
        return [{ value: '', name: '' }]
      }
      return rows.filter((_, i) => i !== index)
    })
  }

  if (!profile) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t(modelsRegistryKey('editModelProfile'))}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <div className="space-y-2">
            <Label>{t(modelsRegistryKey('profileName'))}</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>{t(modelsRegistryKey('modelId'))}</Label>
            <p className="font-mono text-sm text-muted-foreground">{profile.model_id}</p>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label>{t(modelsRegistryKey('paramTemperature'))}</Label>
              <Input value={temperature} onChange={(event) => setTemperature(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>{t(modelsRegistryKey('paramMaxTokens'))}</Label>
              <Input value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>{t(modelsRegistryKey('paramTopP'))}</Label>
              <Input value={topP} onChange={(event) => setTopP(event.target.value)} />
            </div>
          </div>
          {profile.category === 'llm' ? (
            <div className="space-y-3 rounded-md border p-3">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="supports-thinking"
                  checked={supportsThinking}
                  onCheckedChange={(checked) => setSupportsThinking(checked === true)}
                />
                <Label htmlFor="supports-thinking" className="font-normal">
                  {t(modelsRegistryKey('supportsThinking'))}
                </Label>
              </div>
              {supportsThinking ? (
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
                          className="shrink-0 h-9 w-9"
                          aria-label={t(modelsRegistryKey('removeReasoningOption'))}
                          onClick={() => removeOption(index)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={addOption}>
                    <Plus className="h-4 w-4 mr-1" />
                    {t(modelsRegistryKey('addReasoningOption'))}
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    {t(modelsRegistryKey('reasoningOptionsHint'))}
                  </p>
                </div>
              ) : null}
            </div>
          ) : null}
          <p className="text-xs text-muted-foreground">{t(modelsRegistryKey('runtimeConfigHint'))}</p>
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void save(true)}
          >
            {t(modelsRegistryKey('resetFromCatalog'))}
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t(modelsRegistryKey('cancel'))}
            </Button>
            <Button
              type="button"
              disabled={busy || !name.trim()}
              onClick={() => void save(false)}
            >
              {t(modelsRegistryKey('save'))}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
