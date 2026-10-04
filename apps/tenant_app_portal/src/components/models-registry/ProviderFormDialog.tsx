import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
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
  createRegistryProvider,
  updateRegistryProvider,
  type CatalogProvider,
  type LLMProvider,
} from '@/lib/llmConfigApi'
import { AlertCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { modelsRegistryKey, registerModelsRegistryI18n } from './i18n'

const emptyForm = () => ({
  display_name: '',
  preset_key: '',
  api_base: '',
  embedding_api_base: '',
  api_key: '',
})

interface ProviderFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  catalog: CatalogProvider[]
  editingProvider: LLMProvider | null
  onSaved: () => Promise<void> | void
}

export default function ProviderFormDialog({
  open,
  onOpenChange,
  catalog,
  editingProvider,
  onSaved,
}: ProviderFormDialogProps) {
  registerModelsRegistryI18n()
  const { t } = useTranslation()
  const [form, setForm] = useState(emptyForm())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    setError(null)
    if (editingProvider) {
      setForm({
        display_name: editingProvider.display_name,
        preset_key: editingProvider.preset_key || '',
        api_base: editingProvider.api_base,
        embedding_api_base: editingProvider.embedding_api_base || '',
        api_key: '',
      })
    } else {
      setForm(emptyForm())
    }
  }, [open, editingProvider])

  const applyPreset = (presetKey: string) => {
    const preset = catalog.find((item) => item.key === presetKey || item.provider === presetKey)
    if (!preset) {
      return
    }
    setForm((current) => ({
      ...current,
      preset_key: preset.key || preset.provider,
      display_name: current.display_name || preset.name,
      api_base: preset.api_base || current.api_base,
    }))
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = {
        display_name: form.display_name.trim(),
        preset_key: form.preset_key || null,
        api_base: form.api_base.trim(),
        embedding_api_base: form.embedding_api_base.trim() || null,
        api_key: form.api_key,
      }
      if (editingProvider) {
        await updateRegistryProvider(editingProvider.id, payload)
      } else {
        await createRegistryProvider(payload)
      }
      onOpenChange(false)
      await onSaved()
    } catch (err) {
      setError(getApiErrorMessage(err, t(modelsRegistryKey('saveFailed'))))
    } finally {
      setBusy(false)
    }
  }

  const isLocalPreset = form.preset_key === 'ollama'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {editingProvider ? t('common.edit') : t(modelsRegistryKey('addProvider'))}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <div className="space-y-2">
            <Label>{t(modelsRegistryKey('preset'))}</Label>
            <Select value={form.preset_key} onValueChange={applyPreset}>
              <SelectTrigger>
                <SelectValue placeholder={t(modelsRegistryKey('selectProvider'))} />
              </SelectTrigger>
              <SelectContent>
                {catalog.map((preset) => (
                  <SelectItem key={preset.provider} value={preset.key || preset.provider}>
                    {preset.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{t(modelsRegistryKey('displayName'))}</Label>
            <Input
              value={form.display_name}
              onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label>{t(modelsRegistryKey('apiBase'))}</Label>
            <Input
              value={form.api_base}
              onChange={(event) => setForm((current) => ({ ...current, api_base: event.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label>{t(modelsRegistryKey('embeddingApiBase'))}</Label>
            <Input
              value={form.embedding_api_base}
              onChange={(event) =>
                setForm((current) => ({ ...current, embedding_api_base: event.target.value }))
              }
            />
          </div>
          <div className="space-y-2">
            <Label>{t(modelsRegistryKey('apiKey'))}</Label>
            <Input
              type="password"
              value={form.api_key}
              onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))}
              placeholder={
                editingProvider
                  ? t(modelsRegistryKey('currentKey'), { key: editingProvider.api_key_masked })
                  : isLocalPreset
                    ? 'ollama'
                    : undefined
              }
            />
            {isLocalPreset && !editingProvider ? (
              <p className="text-xs text-muted-foreground">{t(modelsRegistryKey('apiKeyLocalHint'))}</p>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t(modelsRegistryKey('cancel'))}
          </Button>
          <Button onClick={() => void save()} disabled={busy || !form.display_name.trim()}>
            {t(modelsRegistryKey('save'))}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
