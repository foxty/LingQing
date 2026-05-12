import { useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    skills: {
      pageTitle: 'Skills',
      description: 'Reusable capabilities the agent can invoke.',
      upload: 'Upload Skill',
      importFromUrl: 'Import from URL',
      importing: 'Importing...',
      uploading: 'Uploading...',
      loading: 'Loading...',
      loadFailed: 'Failed to load skills',
      loadFailedHint: 'Something went wrong while loading skills. Try again.',
      createFailed: 'Failed to upload skill',
      importFailed: 'Failed to import skill',
      deleteFailed: 'Failed to delete skill',
      toggleFailed: 'Failed to update skill',
      envVarsFailed: 'Failed to update environment variables',
      noSkills: 'No skills',
      noTenantSkills: 'No tenant skills yet',
      noPersonalSkills: 'No personal skills yet',
      uploadHintTenant: 'Upload a .zip skill package or import from GitHub / skills.sh to share with your tenant.',
      uploadHintPersonal: 'Upload a .zip skill package or import from GitHub / skills.sh for your account only.',
      all: 'All',
      builtin: 'Built-in',
      tenant: 'Tenant',
      personal: 'Personal',
      enabled: 'Enabled',
      disabled: 'Disabled',
      envVars: 'env var(s)',
      createdBy: 'Created by',
      updatedAt: 'Updated',
      deleteConfirmTitle: 'Confirm Delete',
      deleteConfirmMessage:
        'Are you sure you want to delete skill {{name}}? This action cannot be undone.',
      deleteCancel: 'Cancel',
      deleteConfirm: 'Delete',
      deleting: 'Deleting...',
      builtinType: 'Built-in',
      tenantType: 'Tenant',
      personalType: 'Personal',
      viewDetail: 'View details',
      enable: 'Enable',
      disable: 'Disable',
      saving: 'Saving...',
      envVarKey: 'Key',
      envVarValue: 'Value',
      envVarAdd: 'Add Variable',
      envVarSave: 'Save Env Vars',
      envVarTitle: 'Environment Variables',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    skills: {
      pageTitle: '技能',
      description: '智能体可调用的可复用能力。',
      upload: '上传技能',
      importFromUrl: '从 URL 导入',
      importing: '导入中...',
      uploading: '上传中...',
      loading: '加载中...',
      loadFailed: '加载技能失败',
      loadFailedHint: '加载技能时出错，请重试。',
      createFailed: '上传技能失败',
      importFailed: '导入技能失败',
      deleteFailed: '删除技能失败',
      toggleFailed: '更新技能失败',
      envVarsFailed: '更新环境变量失败',
      noSkills: '暂无技能',
      noTenantSkills: '暂无租户技能',
      noPersonalSkills: '暂无个人技能',
      uploadHintTenant: '上传 .zip 技能包或从 GitHub / skills.sh 导入，供本租户所有成员使用。',
      uploadHintPersonal: '上传 .zip 技能包或从 GitHub / skills.sh 导入，仅供你的账号使用。',
      all: '全部',
      builtin: '内置',
      tenant: '租户',
      personal: '个人',
      enabled: '启用',
      disabled: '禁用',
      envVars: '个环境变量',
      createdBy: '创建者',
      updatedAt: '更新',
      deleteConfirmTitle: '确认删除',
      deleteConfirmMessage: '确定要删除技能 {{name}} 吗？此操作不可恢复。',
      deleteCancel: '取消',
      deleteConfirm: '删除',
      deleting: '删除中...',
      builtinType: '内置',
      tenantType: '租户',
      personalType: '个人',
      viewDetail: '查看详情',
      enable: '启用',
      disable: '禁用',
      saving: '保存中...',
      envVarKey: '变量名',
      envVarValue: '变量值',
      envVarAdd: '添加变量',
      envVarSave: '保存环境变量',
      envVarTitle: '环境变量',
    },
  },
  true,
  true
)
import {
  useSkills,
  useCreateSkill,
  useImportSkill,
  useDeleteSkill,
  useToggleSkillEnabled,
  useSkillEnvVars,
  useUpdateEnvVars,
} from '@/hooks/useSkills'
import ImportSkillDialog from '@/components/ImportSkillDialog'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import EmptyState from '@/components/EmptyState'
import { useConfirmation } from '@/hooks/useConfirmation'
import { Can } from '@/components/Can'
import { useAuth } from '@/hooks/useAuth'
import { actionRules } from '@/lib/permissionRules'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Code, Upload, Download, Trash2, Settings2, Plus } from 'lucide-react'
import type { Skill } from '@/types'

type TabType = 'all' | 'builtin' | 'tenant' | 'personal'

export default function SkillsPage() {
  const { t } = useTranslation()
  const { hasAny } = useAuth()
  const canUpload = hasAny(actionRules.canUploadSkill())
  const [activeTab, setActiveTab] = useState<TabType>('all')
  const { data, isLoading, isError, refetch } = useSkills()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [envVarSkill, setEnvVarSkill] = useState<Skill | null>(null)
  const [importOpen, setImportOpen] = useState(false)

  const skills = data?.items ?? []
  const deleteConfirm = useConfirmation<{ name: string; type: string }>()
  const deleteMutation = useDeleteSkill()
  const createMutation = useCreateSkill()
  const importMutation = useImportSkill()
  const toggleMutation = useToggleSkillEnabled()

  const grouped = groupSkillsByType(skills)
  const tabLabels: Record<TabType, string> = {
    all: t('skills.all'),
    builtin: t('skills.builtin'),
    tenant: t('skills.tenant'),
    personal: t('skills.personal'),
  }
  const tabs: { key: TabType; count: number }[] = [
    { key: 'all', count: skills.length },
    { key: 'builtin', count: grouped.builtin.length },
    { key: 'tenant', count: grouped.tenant.length },
    { key: 'personal', count: grouped.personal.length },
  ]

  const handleDelete = async (item: { name: string; type: string }) => {
    deleteConfirm.setLoading(true)
    try {
      await deleteMutation.mutateAsync(item)
      deleteConfirm.close()
    } finally {
      deleteConfirm.setLoading(false)
    }
  }

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const type = activeTab === 'personal' ? 'personal' : 'tenant'
    await createMutation.mutateAsync({ type, file })
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const triggerUpload = () => {
    fileInputRef.current?.click()
  }

  const skillType = activeTab === 'personal' ? 'personal' : 'tenant'
  const isBusy = createMutation.isPending || importMutation.isPending

  const handleImport = async (url: string) => {
    await importMutation.mutateAsync({ type: skillType, url })
  }

  const handleToggle = async (skill: Skill) => {
    if (skill.type === 'builtin') return
    await toggleMutation.mutateAsync({
      scope: skill.type,
      name: skill.name,
      enabled: !skill.enabled,
    })
  }

  const displayedSkills = activeTab === 'all' ? skills : grouped[activeTab]
  const canUploadHere = canUpload && (activeTab === 'tenant' || activeTab === 'personal')
  const visibleTabs = tabs.filter((tab) => {
    if (tab.key === 'all') return true
    if (tab.key === 'builtin') return tab.count > 0
    return canUpload || tab.count > 0
  })

  const emptyState =
    activeTab === 'tenant' && canUpload
      ? { title: t('skills.noTenantSkills'), description: t('skills.uploadHintTenant') }
      : activeTab === 'personal' && canUpload
        ? { title: t('skills.noPersonalSkills'), description: t('skills.uploadHintPersonal') }
        : { title: t('skills.noSkills'), description: t('skills.description') }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t('skills.pageTitle')}</h1>
          <p className="text-sm text-muted-foreground">{t('skills.description')}</p>
        </div>
        <Can any={actionRules.canUploadSkill()}>
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={handleFileSelect}
            />
            <Button
              variant="outline"
              onClick={() => setImportOpen(true)}
              disabled={isBusy || !canUploadHere}
            >
              <Download className="w-4 h-4 mr-2" />
              {importMutation.isPending ? t('skills.importing') : t('skills.importFromUrl')}
            </Button>
            <Button onClick={triggerUpload} disabled={isBusy || !canUploadHere}>
              <Upload className="w-4 h-4 mr-2" />
              {createMutation.isPending ? t('skills.uploading') : t('skills.upload')}
            </Button>
          </div>
        </Can>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {visibleTabs.map((tab) => (
          <Button
            key={tab.key}
            variant={activeTab === tab.key ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setActiveTab(tab.key)}
          >
            {tabLabels[tab.key]}
            {tab.count > 0 ? ` ${tab.count}` : ''}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-muted-foreground">{t('skills.loading')}</div>
      ) : isError ? (
        <EmptyState
          title={t('skills.loadFailed')}
          description={t('skills.loadFailedHint')}
          action={
            <Button variant="outline" onClick={() => refetch()}>
              {t('common.retry')}
            </Button>
          }
        />
      ) : displayedSkills.length === 0 ? (
        <EmptyState
          title={emptyState.title}
          description={emptyState.description}
          action={
            canUploadHere ? (
              <div className="flex items-center gap-2">
                <Button variant="outline" onClick={() => setImportOpen(true)} disabled={isBusy}>
                  <Download className="mr-2 h-4 w-4" />
                  {importMutation.isPending ? t('skills.importing') : t('skills.importFromUrl')}
                </Button>
                <Button onClick={triggerUpload} disabled={isBusy}>
                  <Upload className="mr-2 h-4 w-4" />
                  {createMutation.isPending ? t('skills.uploading') : t('skills.upload')}
                </Button>
              </div>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-4">
          {displayedSkills.map((skill) => (
            <SkillCard
              key={`${skill.type}-${skill.name}`}
              skill={skill}
              t={t}
              onToggle={handleToggle}
              onDelete={(name, type) => deleteConfirm.open({ name, type })}
              onEnvVars={(s) => setEnvVarSkill(s)}
              toggleDisabled={toggleMutation.isPending}
            />
          ))}
        </div>
      )}

      {envVarSkill && (
        <EnvVarDialog skill={envVarSkill} t={t} onClose={() => setEnvVarSkill(null)} />
      )}

      <ImportSkillDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        disabled={isBusy || !canUploadHere}
        onImport={handleImport}
      />

      <ConfirmationDialog
        open={deleteConfirm.isOpen}
        item={deleteConfirm.item}
        isLoading={deleteConfirm.isLoading}
        title={t('skills.deleteConfirmTitle')}
        description={(item) => t('skills.deleteConfirmMessage', { name: item.name })}
        confirmText={t('skills.deleteConfirm')}
        isDangerous
        onConfirm={handleDelete}
        onCancel={deleteConfirm.close}
      />
    </div>
  )
}

function EnvVarDialog({
  skill,
  t,
  onClose,
}: {
  skill: Skill
  t: (key: string, options?: any) => string
  onClose: () => void
}) {
  const { data: envVars = {}, isLoading } = useSkillEnvVars(skill.type, skill.name)
  const updateMutation = useUpdateEnvVars(skill.type, skill.name)
  const [entries, setEntries] = useState<[string, string][]>([])
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [loaded, setLoaded] = useState(false)

  if (!loaded && !isLoading && envVars) {
    setEntries(Object.entries(envVars))
    setLoaded(true)
  }

  const handleSave = async () => {
    const allEntries = [...entries]
    if (newKey.trim()) {
      allEntries.push([newKey.trim(), newValue])
    }
    const obj = Object.fromEntries(allEntries)
    await updateMutation.mutateAsync(obj)
    onClose()
  }

  const removeEntry = (key: string) => {
    setEntries(entries.filter(([k]) => k !== key))
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <Card className="w-[480px]">
        <CardHeader>
          <CardTitle>
            {skill.name} - {t('skills.envVars')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">{t('skills.loading')}</p>
          ) : (
            <>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {entries.map(([key, value]) => (
                  <div key={key} className="flex items-center gap-2">
                    <Input value={key} readOnly className="w-40 text-xs" />
                    <Input value={value} readOnly className="flex-1 text-xs" type="password" />
                    <Button variant="ghost" size="sm" onClick={() => removeEntry(key)}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2 pt-2 border-t">
                <Input
                  placeholder="KEY"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  className="w-40 text-xs"
                />
                <Input
                  placeholder="VALUE"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  className="flex-1 text-xs"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    if (newKey.trim()) {
                      setEntries([...entries, [newKey.trim(), newValue]])
                      setNewKey('')
                      setNewValue('')
                    }
                  }}
                >
                  <Plus className="w-3 h-3" />
                </Button>
              </div>
            </>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={onClose}>
              {t('skills.deleteCancel')}
            </Button>
            <Button onClick={handleSave} disabled={updateMutation.isPending}>
              {updateMutation.isPending ? t('skills.saving', 'Saving...') : t('common.save')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function SkillCard({
  skill,
  t,
  onToggle,
  onDelete,
  onEnvVars,
  toggleDisabled,
}: {
  skill: Skill
  t: (key: string, options?: any) => string
  onToggle: (skill: Skill) => void
  onDelete: (name: string, type: string) => void
  onEnvVars: (skill: Skill) => void
  toggleDisabled: boolean
}) {
  const typeLabels: Record<string, string> = {
    builtin: t('skills.builtinType'),
    tenant: t('skills.tenantType'),
    personal: t('skills.personalType'),
  }
  const typeLabel = typeLabels[skill.type] || skill.type

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Code className="w-4 h-4 text-muted-foreground shrink-0" />
              <span className="font-medium">{skill.name}</span>
              <Badge variant="secondary">{typeLabel}</Badge>
            </div>
            <p className="text-sm text-muted-foreground break-words">{skill.description}</p>
            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
              {skill.envVarKeys.length > 0 && (
                <span>
                  {skill.envVarKeys.length} {t('skills.envVars')}
                </span>
              )}
              {skill.createdBy && (
                <span>
                  {t('skills.createdBy')}: {skill.createdBy}
                </span>
              )}
              {skill.updatedAt && (
                <span>
                  {t('skills.updatedAt')}: {new Date(skill.updatedAt).toLocaleDateString()}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {skill.type !== 'builtin' && (
              <>
                <Switch
                  checked={skill.enabled}
                  onCheckedChange={() => onToggle(skill)}
                  disabled={toggleDisabled}
                  title={skill.enabled ? t('skills.enabled') : t('skills.disabled')}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onEnvVars(skill)}
                  title={t('skills.envVars')}
                >
                  <Settings2 className="w-4 h-4" />
                </Button>
                <Can any={actionRules.canDeleteSkill()}>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(skill.name, skill.type)}
                    title={t('common.delete')}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </Can>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function groupSkillsByType(skills: Skill[]) {
  return {
    builtin: skills.filter((s) => s.type === 'builtin'),
    tenant: skills.filter((s) => s.type === 'tenant'),
    personal: skills.filter((s) => s.type === 'personal'),
  }
}
