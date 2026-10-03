import ContainerDetailHeader from '@/components/ContainerDetailHeader'
import ListDetailToolbar from '@/components/ListDetailToolbar'
import { modelsRegistryKey, registerModelsRegistryI18n } from '@/components/models-registry/i18n'
import ProfileFormDialog from '@/components/models-registry/ProfileFormDialog'
import ProviderFormDialog from '@/components/models-registry/ProviderFormDialog'
import {
  defaultBadgesForProfile,
  presetDisplayName,
  unregisteredCatalogModels,
} from '@/components/models-registry/utils'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
  createRegistryProfile,
  deleteRegistryProfile,
  getRegistryDefaults,
  listCatalogProviders,
  listRegistryProfiles,
  listRegistryProviders,
  testRegistryProviderConnection,
  type LLMDefaults,
  type LLMModelProfile,
  type LLMProvider,
} from '@/lib/llmConfigApi'
import { AlertCircle, Loader2, MoreHorizontal } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'

export default function SettingsProviderDetailPage() {
  registerModelsRegistryI18n()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { providerId } = useParams<{ providerId: string }>()
  const numericProviderId = Number(providerId)
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
  const [profileDialogOpen, setProfileDialogOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const provider = providers.find((item) => item.id === numericProviderId)
  const providerProfiles = useMemo(
    () => profiles.filter((profile) => profile.provider_id === numericProviderId),
    [profiles, numericProviderId]
  )
  const filteredProfiles = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) {
      return providerProfiles
    }
    return providerProfiles.filter((profile) => profile.model_id.toLowerCase().includes(query))
  }, [providerProfiles, searchQuery])

  const catalogSuggestions = provider ? unregisteredCatalogModels(provider, profiles, catalog) : []

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
  }, [numericProviderId])

  const removeProfile = async (profileId: number) => {
    if (!window.confirm(t('common.deleteConfirm'))) {
      return
    }
    try {
      await deleteRegistryProfile(profileId)
      showSuccess(t(modelsRegistryKey('profileDeleted')))
      await loadAll()
    } catch (err) {
      showError(err instanceof Error ? err.message : t(modelsRegistryKey('loadFailed')))
    }
  }

  const quickAddCatalogModel = async (modelKey: string, modelId: string, modelName: string, category: string) => {
    if (!provider) {
      return
    }
    setBusy(true)
    try {
      await createRegistryProfile({
        provider_id: provider.id,
        name: modelName,
        category: category === 'embedding' ? 'embedding' : 'llm',
        model_id: modelId,
        catalog_model_key: modelKey,
        source: 'preset',
      })
      showSuccess(t(modelsRegistryKey('profileSaved')))
      await loadAll()
    } catch (err) {
      showError(err instanceof Error ? err.message : t(modelsRegistryKey('loadFailed')))
    } finally {
      setBusy(false)
    }
  }

  const testConnection = async () => {
    if (!provider) {
      return
    }
    try {
      const result = await testRegistryProviderConnection(provider.id, {})
      showSuccess(result.message || t(modelsRegistryKey('testSuccess')))
    } catch (err) {
      showError(err instanceof Error ? err.message : t(modelsRegistryKey('testFailed')))
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        {t('common.loading')}
      </div>
    )
  }

  if (!provider) {
    return (
      <div className="space-y-4">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{t(modelsRegistryKey('loadFailed'))}</AlertDescription>
        </Alert>
        <Button variant="outline" onClick={() => navigate('/settings/models')}>
          {t(modelsRegistryKey('providers'))}
        </Button>
      </div>
    )
  }

  const presetName = presetDisplayName(provider, catalog)

  return (
    <div className="space-y-6">
      <ContainerDetailHeader
        parentLabel={t(modelsRegistryKey('providers'))}
        onParentNavigate={() => navigate('/settings/models')}
        title={provider.display_name}
        meta={
          <div className="space-y-1">
            <p>{presetName !== '—' ? presetName : t(modelsRegistryKey('customPreset'))}</p>
            <p className="font-mono text-xs truncate">{provider.api_base}</p>
            <p>
              {t(modelsRegistryKey('apiKey'))}: {provider.api_key_masked}
            </p>
          </div>
        }
      />

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => setProviderDialogOpen(true)}>
          {t(modelsRegistryKey('editCredentials'))}
        </Button>
        <Button variant="outline" size="sm" onClick={() => void testConnection()}>
          {t(modelsRegistryKey('test'))}
        </Button>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {catalogSuggestions.length > 0 ? (
        <div className="rounded-lg border border-dashed bg-card px-4 py-3 space-y-2">
          <p className="text-xs font-medium text-muted-foreground">{t(modelsRegistryKey('catalogModels'))}</p>
          <div className="flex flex-wrap gap-2">
            {catalogSuggestions.map((model) => (
              <Button
                key={model.key}
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() =>
                  void quickAddCatalogModel(
                    model.key,
                    model.model_id,
                    model.name,
                    model.category || 'llm'
                  )
                }
              >
                + {model.name}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="space-y-4">
        <ListDetailToolbar
          searchQuery={searchQuery}
          searchPlaceholder={t(modelsRegistryKey('searchModels'))}
          onSearchQueryChange={setSearchQuery}
          onClearSearchQuery={() => setSearchQuery('')}
          primaryAction={{
            label: t(modelsRegistryKey('addModel')),
            onClick: () => setProfileDialogOpen(true),
          }}
        />

        {filteredProfiles.length === 0 ? (
          <div className="rounded-lg border bg-card py-12 text-center">
            <p className="text-sm text-muted-foreground">
              {searchQuery ? t('common.noResults') : t(modelsRegistryKey('noProfiles'))}
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border bg-card">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-10">{t(modelsRegistryKey('modelId'))}</TableHead>
                  <TableHead className="h-10 w-28">{t(modelsRegistryKey('category'))}</TableHead>
                  <TableHead className="h-10 w-40">{t(modelsRegistryKey('usedAsCol'))}</TableHead>
                  <TableHead className="h-10 w-16 text-right">{t('common.operation')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredProfiles.map((profile) => (
                  <TableRow key={profile.id}>
                    <TableCell className="py-2.5 font-mono text-xs">{profile.model_id}</TableCell>
                    <TableCell className="py-2.5">
                      <Badge variant="outline" className="font-normal">
                        {profile.category === 'embedding'
                          ? t(modelsRegistryKey('categoryEmbedding'))
                          : t(modelsRegistryKey('categoryLlm'))}
                      </Badge>
                    </TableCell>
                    <TableCell className="py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {defaultBadgesForProfile(profile.id, defaults, t).map((badge) => (
                          <Badge key={badge} variant="secondary" className="font-normal">
                            {badge}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="py-2.5 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                            <span className="sr-only">{t('common.action')}</span>
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={() => void removeProfile(profile.id)}
                          >
                            {t(modelsRegistryKey('removeModel'))}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <ProviderFormDialog
        open={providerDialogOpen}
        onOpenChange={setProviderDialogOpen}
        catalog={catalog}
        editingProvider={provider}
        onSaved={async () => {
          showSuccess(t(modelsRegistryKey('providerSaved')))
          await loadAll()
        }}
      />

      <ProfileFormDialog
        open={profileDialogOpen}
        onOpenChange={setProfileDialogOpen}
        providers={providers}
        catalog={catalog}
        fixedProviderId={provider.id}
        onSaved={async () => {
          showSuccess(t(modelsRegistryKey('profileSaved')))
          await loadAll()
        }}
      />
    </div>
  )
}
