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
import {
  catalogModelsForProvider,
  createRegistryProfile,
  CUSTOM_CATALOG_MODEL_KEY,
  type CatalogProvider,
  type LLMProvider,
  type ModelProfileCategory,
} from '@/lib/llmConfigApi'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { modelsRegistryKey, registerModelsRegistryI18n } from './i18n'

const emptyForm = (category: ModelProfileCategory, providerId: string) => ({
  provider_id: providerId,
  name: '',
  category,
  model_id: '',
  catalog_model_key: '',
  source: 'preset' as 'preset' | 'custom',
})

interface ProfileFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  providers: LLMProvider[]
  catalog: CatalogProvider[]
  fixedProviderId?: number
  onSaved: () => Promise<void> | void
}

export default function ProfileFormDialog({
  open,
  onOpenChange,
  providers,
  catalog,
  fixedProviderId,
  onSaved,
}: ProfileFormDialogProps) {
  registerModelsRegistryI18n()
  const { t } = useTranslation()
  const [category, setCategory] = useState<ModelProfileCategory>('llm')
  const [form, setForm] = useState(emptyForm('llm', fixedProviderId ? String(fixedProviderId) : ''))
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) {
      return
    }
    setCategory('llm')
    setForm(emptyForm('llm', fixedProviderId ? String(fixedProviderId) : ''))
  }, [open, fixedProviderId])

  const selectedProvider = providers.find((item) => String(item.id) === form.provider_id)
  const catalogModels = selectedProvider ? catalogModelsForProvider(selectedProvider, catalog, category) : []
  const useCatalogPicker = catalogModels.length > 0
  const isCustomModel = form.catalog_model_key === CUSTOM_CATALOG_MODEL_KEY || !useCatalogPicker

  const providerLocked = fixedProviderId !== undefined

  const save = async () => {
    setBusy(true)
    try {
      await createRegistryProfile({
        provider_id: Number(form.provider_id),
        name: form.name.trim(),
        category,
        model_id: form.model_id.trim(),
        catalog_model_key:
          form.catalog_model_key === CUSTOM_CATALOG_MODEL_KEY ? null : form.catalog_model_key || null,
        source: form.source,
      })
      onOpenChange(false)
      await onSaved()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(modelsRegistryKey('addModel'))}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t(modelsRegistryKey('category'))}</Label>
            <Select
              value={category}
              onValueChange={(value) => {
                const next = value as ModelProfileCategory
                setCategory(next)
                setForm((current) => ({
                  ...current,
                  category: next,
                  catalog_model_key: '',
                  model_id: '',
                }))
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="llm">{t(modelsRegistryKey('categoryLlm'))}</SelectItem>
                <SelectItem value="embedding">{t(modelsRegistryKey('categoryEmbedding'))}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {!providerLocked ? (
            <div className="space-y-2">
              <Label>{t(modelsRegistryKey('provider'))}</Label>
              <Select
                value={form.provider_id}
                onValueChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    provider_id: value,
                    model_id: '',
                    catalog_model_key: '',
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder={t(modelsRegistryKey('selectProvider'))} />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.id} value={String(provider.id)}>
                      {provider.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          <div className="space-y-2">
            <Label>{t(modelsRegistryKey('profileName'))}</Label>
            <Input
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            />
          </div>
          {useCatalogPicker ? (
            <div className="space-y-2">
              <Label>{t(modelsRegistryKey('selectModel'))}</Label>
              <Select
                value={form.catalog_model_key || undefined}
                onValueChange={(value) => {
                  if (value === CUSTOM_CATALOG_MODEL_KEY) {
                    setForm((current) => ({
                      ...current,
                      catalog_model_key: CUSTOM_CATALOG_MODEL_KEY,
                      model_id: '',
                      source: 'custom',
                    }))
                    return
                  }
                  const model = catalogModels.find((item) => item.key === value)
                  setForm((current) => ({
                    ...current,
                    catalog_model_key: value,
                    model_id: model?.model_id || '',
                    name: current.name.trim() || model?.name || current.name,
                    source: 'preset',
                  }))
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t(modelsRegistryKey('selectModel'))} />
                </SelectTrigger>
                <SelectContent>
                  {catalogModels.map((model) => (
                    <SelectItem key={model.key} value={model.key}>
                      {model.name} ({model.model_id})
                    </SelectItem>
                  ))}
                  <SelectItem value={CUSTOM_CATALOG_MODEL_KEY}>{t(modelsRegistryKey('customModel'))}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ) : null}
          {isCustomModel ? (
            <div className="space-y-2">
              <Label>{t(modelsRegistryKey('modelId'))}</Label>
              <Input
                value={form.model_id}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    model_id: event.target.value,
                    catalog_model_key: CUSTOM_CATALOG_MODEL_KEY,
                    source: 'custom',
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">{t(modelsRegistryKey('customModelHint'))}</p>
            </div>
          ) : form.model_id ? (
            <div className="space-y-1">
              <Label>{t(modelsRegistryKey('modelId'))}</Label>
              <p className="font-mono text-sm text-muted-foreground">{form.model_id}</p>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t(modelsRegistryKey('cancel'))}
          </Button>
          <Button
            onClick={() => void save()}
            disabled={busy || !form.provider_id || !form.name.trim() || !form.model_id.trim()}
          >
            {t(modelsRegistryKey('save'))}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
