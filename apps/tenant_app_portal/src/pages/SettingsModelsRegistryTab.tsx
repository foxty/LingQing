import SettingsListToolbar from '@/components/SettingsListToolbar'
import SettingsPageShell from '@/components/SettingsPageShell'
import SettingsRowActions from '@/components/SettingsRowActions'
import SettingsSection from '@/components/SettingsSection'
import { modelsRegistryKey, registerModelsRegistryI18n } from '@/components/models-registry/i18n'
import ProviderFormDialog from '@/components/models-registry/ProviderFormDialog'
import RuntimeDefaultsPanel from '@/components/models-registry/RuntimeDefaultsPanel'
import { modelCountLabel, presetDisplayName } from '@/components/models-registry/utils'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useNotification } from '@/hooks/useNotification'
import {
  deleteRegistryProvider,
  getRegistryDefaults,
  listCatalogProviders,
  listRegistryProfiles,
  listRegistryProviders,
  updateRegistryDefaults,
  type LLMDefaults,
  type LLMModelProfile,
  type LLMProvider,
} from '@/lib/llmConfigApi'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

export default function SettingsModelsRegistryTab() {
  registerModelsRegistryI18n()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showSuccess, showError } = useNotification()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [catalog, setCatalog] = useState<Awaited<ReturnType<typeof listCatalogProviders>>>([])
  const [providers, setProviders] = useState<LLMProvider[]>([])
  const [profiles, setProfiles] = useState<LLMModelProfile[]>([])
  const [defaults, setDefaults] = useState<LLMDefaults>({
    agent_profile_id: null,
    mini_agent_profile_id: null,
    embedding_profile_id: null,
  })
  const [providerDialogOpen, setProviderDialogOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState<LLMProvider | null>(null)
  const [busy, setBusy] = useState(false)

  const llmProfiles = useMemo(
    () => profiles.filter((profile) => profile.category === 'llm'),
    [profiles]
  )
  const embeddingProfiles = useMemo(
    () => profiles.filter((profile) => profile.category === 'embedding'),
    [profiles]
  )

  const filteredProviders = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) {
      return providers
    }
    return providers.filter(
      (provider) =>
        provider.display_name.toLowerCase().includes(query) ||
        provider.api_base.toLowerCase().includes(query) ||
        presetDisplayName(provider, catalog).toLowerCase().includes(query)
    )
  }, [providers, searchQuery, catalog])

  const loadAll = async () => {
    setLoading(true)
    setError(null)
    try {
      const [catalogData, providerData, profileData, defaultsData] = await Promise.all([
        listCatalogProviders(),
        listRegistryProviders(),
        listRegistryProfiles(),
        getRegistryDefaults(),
      ])
      setCatalog(catalogData)
      setProviders(providerData)
      setProfiles(profileData)
      setDefaults(defaultsData)
    } catch (err) {
      setError(err instanceof Error ? err.message : t(modelsRegistryKey('loadFailed')))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAll()
  }, [])

  const openCreateProvider = () => {
    setEditingProvider(null)
    setProviderDialogOpen(true)
  }

  const openEditProvider = (provider: LLMProvider) => {
    setEditingProvider(provider)
    setProviderDialogOpen(true)
  }

  const removeProvider = async (providerId: number) => {
    if (!window.confirm(t('common.deleteConfirm'))) {
      return
    }
    try {
      await deleteRegistryProvider(providerId)
      showSuccess(t(modelsRegistryKey('providerDeleted')))
      await loadAll()
    } catch (err) {
      showError(err instanceof Error ? err.message : t(modelsRegistryKey('loadFailed')))
    }
  }

  const saveDefaults = async () => {
    setBusy(true)
    try {
      const updated = await updateRegistryDefaults(defaults)
      setDefaults(updated)
      showSuccess(t(modelsRegistryKey('defaultsSaved')))
    } catch (err) {
      showError(err instanceof Error ? err.message : t(modelsRegistryKey('loadFailed')))
    } finally {
      setBusy(false)
    }
  }

  const handleProviderSaved = async () => {
    showSuccess(t(modelsRegistryKey('providerSaved')))
    await loadAll()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        {t('common.loading')}
      </div>
    )
  }

  return (
    <SettingsPageShell>
      {error ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <SettingsSection
        title={t(modelsRegistryKey('defaults'))}
        description={t(modelsRegistryKey('defaultsHint'))}
      >
        <RuntimeDefaultsPanel
          defaults={defaults}
          llmProfiles={llmProfiles}
          embeddingProfiles={embeddingProfiles}
          providers={providers}
          busy={busy}
          onChange={setDefaults}
          onSave={() => void saveDefaults()}
        />
      </SettingsSection>

      <SettingsSection
        title={t(modelsRegistryKey('providers'))}
        description={t(modelsRegistryKey('providersDesc'))}
        contentClassName="space-y-4 p-4 pt-0"
      >
        <SettingsListToolbar
          search={{
            query: searchQuery,
            placeholder: t(modelsRegistryKey('searchProviders')),
            onQueryChange: setSearchQuery,
            onClear: () => setSearchQuery(''),
          }}
          onRefresh={() => void loadAll()}
          refreshing={loading}
          refreshLabel={t('common.refresh')}
          primaryAction={{
            label: t(modelsRegistryKey('addProvider')),
            onClick: openCreateProvider,
          }}
        />

        {filteredProviders.length === 0 ? (
          <div className="rounded-lg border py-12 text-center">
            <p className="text-sm text-muted-foreground">
              {searchQuery ? t('common.noResults') : t(modelsRegistryKey('noProviders'))}
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-10">{t(modelsRegistryKey('displayName'))}</TableHead>
                  <TableHead className="h-10 w-40">{t(modelsRegistryKey('presetCol'))}</TableHead>
                  <TableHead className="h-10 w-32">{t(modelsRegistryKey('modelCountCol'))}</TableHead>
                  <TableHead className="h-10 w-28">{t(modelsRegistryKey('statusCol'))}</TableHead>
                  <TableHead className="h-10 w-24 text-right">{t('common.operation')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredProviders.map((provider) => (
                  <TableRow key={provider.id}>
                    <TableCell className="py-2.5">
                      <button
                        type="button"
                        onClick={() => navigate(`/settings/models/providers/${provider.id}`)}
                        className="text-left text-sm font-medium hover:underline"
                      >
                        {provider.display_name}
                      </button>
                    </TableCell>
                    <TableCell className="py-2.5 text-sm text-muted-foreground">
                      {presetDisplayName(provider, catalog) === '—'
                        ? t(modelsRegistryKey('customPreset'))
                        : presetDisplayName(provider, catalog)}
                    </TableCell>
                    <TableCell className="py-2.5 text-sm tabular-nums">
                      {modelCountLabel(profiles, provider.id)}
                    </TableCell>
                    <TableCell className="py-2.5">
                      <Badge variant={provider.status === 'active' ? 'outline' : 'secondary'}>
                        {provider.status === 'active'
                          ? t(modelsRegistryKey('statusActive'))
                          : t(modelsRegistryKey('statusDisabled'))}
                      </Badge>
                    </TableCell>
                    <TableCell className="py-2.5 text-right">
                      <SettingsRowActions
                        onEdit={() => openEditProvider(provider)}
                        onDelete={() => void removeProvider(provider.id)}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </SettingsSection>

      <ProviderFormDialog
        open={providerDialogOpen}
        onOpenChange={setProviderDialogOpen}
        catalog={catalog}
        editingProvider={editingProvider}
        onSaved={handleProviderSaved}
      />
    </SettingsPageShell>
  )
}
