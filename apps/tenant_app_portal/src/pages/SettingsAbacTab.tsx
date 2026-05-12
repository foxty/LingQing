import i18n from '@/i18n/config'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    abacTab: {
      title: 'ABAC Policies',
      description: 'Configure attribute-based access control policies',
      policyUpdated: 'Policy updated',
      policyCreated: 'Policy created',
      operationFailed: 'Operation failed',
      policyEnabled: 'Policy enabled',
      policyDisabled: 'Policy disabled',
      policyDeleted: 'Policy deleted',
      delete: 'Delete',
      applyDefaultsSuccess: 'Defaults applied ({{created}} created, {{skipped}} skipped)',
      initFailed: 'Failed to initialize',
      applying: 'Applying...',
      applyDefaults: 'Apply Defaults',
      newPolicy: 'New Policy',
      noPolicies: 'No policies configured',
      nameCol: 'Name',
      resourceTypeCol: 'Resource Type',
      actionCol: 'Action',
      expressionCol: 'Expression',
      statusCol: 'Status',
      edit: 'Edit',
      confirmDeleteTitle: 'Confirm Delete',
      confirmDeleteDesc: 'Are you sure you want to delete policy "{{name}}"?',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    abacTab: {
      title: 'ABAC 策略',
      description: '配置基于属性的访问控制策略',
      policyUpdated: '策略已更新',
      policyCreated: '策略已创建',
      operationFailed: '操作失败',
      policyEnabled: '策略已启用',
      policyDisabled: '策略已禁用',
      policyDeleted: '策略已删除',
      delete: '删除',
      applyDefaultsSuccess: '已应用默认值（创建 {{created}}，跳过 {{skipped}}）',
      initFailed: '初始化失败',
      applying: '正在应用...',
      applyDefaults: '应用默认值',
      newPolicy: '新建策略',
      noPolicies: '暂无策略配置',
      nameCol: '名称',
      resourceTypeCol: '资源类型',
      actionCol: '操作',
      expressionCol: '表达式',
      statusCol: '状态',
      edit: '编辑',
      confirmDeleteTitle: '确认删除',
      confirmDeleteDesc: '确定要删除策略"{{name}}"吗？',
    }
  }
}, true, true)

import AbacPolicyFormModal from '@/components/AbacPolicyFormModal'
import SettingsSection from '@/components/SettingsSection'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useNotification } from '@/hooks/useNotification'
import { useAbacPolicies } from '@/hooks/useAbacPolicies'
import type { AbacPolicy, AbacPolicyCreatePayload } from '@/lib/abacPolicyApi'

export default function SettingsAbacTab() {
  const { t } = useTranslation()
  const {
    policies,
    loading,
    error,
    fetchPolicies,
    createOne,
    updateOne,
    removeOne,
    toggleStatus,
    seed,
  } = useAbacPolicies()

  const { showSuccess, showError } = useNotification()

  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<AbacPolicy | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AbacPolicy | null>(null)
  const [seeding, setSeeding] = useState(false)

  useEffect(() => {
    fetchPolicies()
  }, [fetchPolicies])

  const handleSave = async (payload: AbacPolicyCreatePayload) => {
    try {
      if (editTarget) {
        await updateOne(editTarget.id, payload)
        showSuccess(t('settings.abacTab.policyUpdated'))
      } else {
        await createOne(payload)
        showSuccess(t('settings.abacTab.policyCreated'))
      }
    } catch {
      showError(t('settings.abacTab.operationFailed'))
      throw new Error('save failed')
    }
  }

  const handleToggle = async (policy: AbacPolicy) => {
    try {
      await toggleStatus(policy.id, policy.status === 'disabled')
      showSuccess(policy.status === 'disabled' ? t('settings.abacTab.policyEnabled') : t('settings.abacTab.policyDisabled'))
    } catch {
      showError(t('settings.abacTab.operationFailed'))
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await removeOne(deleteTarget.id)
      showSuccess(t('settings.abacTab.policyDeleted'))
    } catch {
      showError(t('settings.abacTab.delete'))
    } finally {
      setDeleteTarget(null)
    }
  }

  const handleSeed = async () => {
    setSeeding(true)
    try {
      const result = await seed()
      showSuccess(t('settings.abacTab.applyDefaultsSuccess', { created: result.created, skipped: result.skipped }))
    } catch {
      showError(t('settings.abacTab.initFailed'))
    } finally {
      setSeeding(false)
    }
  }

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <SettingsSection
        title={t('settings.abacTab.title')}
        description={t('settings.abacTab.description')}
        action={
          <>
            <Button variant="outline" size="sm" onClick={handleSeed} disabled={seeding}>
              {seeding ? t('settings.abacTab.applying') : t('settings.abacTab.applyDefaults')}
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setEditTarget(null)
                setModalOpen(true)
              }}
            >
              {t('settings.abacTab.newPolicy')}
            </Button>
          </>
        }
        contentClassName={loading || policies.length === 0 ? undefined : 'p-0'}
      >
      {loading ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : policies.length === 0 ? (
        <div className="space-y-3 py-6 text-center">
          <p className="text-muted-foreground">{t('settings.abacTab.noPolicies')}</p>
          <Button variant="outline" onClick={handleSeed} disabled={seeding}>
            {seeding ? t('settings.abacTab.applying') : t('settings.abacTab.applyDefaults')}
          </Button>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('settings.abacTab.nameCol')}</TableHead>
              <TableHead>{t('settings.abacTab.resourceTypeCol')}</TableHead>
              <TableHead>{t('settings.abacTab.actionCol')}</TableHead>
              <TableHead>{t('settings.abacTab.expressionCol')}</TableHead>
              <TableHead>{t('settings.abacTab.statusCol')}</TableHead>
              <TableHead className="text-right">{t('common.operation')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {policies.map((policy) => (
              <TableRow key={policy.id}>
                <TableCell>
                  <div>
                    <p className="font-medium text-sm">{policy.name}</p>
                    {policy.description && (
                      <p className="text-xs text-muted-foreground">{policy.description}</p>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{policy.resource_type}</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{policy.action}</Badge>
                </TableCell>
                <TableCell>
                  <code className="text-xs bg-muted rounded px-1 py-0.5 break-all">
                    {policy.expression}
                  </code>
                </TableCell>
                <TableCell>
                  <Switch
                    checked={policy.status === 'active'}
                    onCheckedChange={() => handleToggle(policy)}
                  />
                </TableCell>
                <TableCell className="text-right space-x-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setEditTarget(policy)
                      setModalOpen(true)
                    }}
                  >
                    {t('settings.abacTab.edit')}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleteTarget(policy)}
                  >
                    {t('settings.abacTab.delete')}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      </SettingsSection>

      {/* Policy form modal */}
      <AbacPolicyFormModal
        open={modalOpen}
        initial={editTarget}
        onClose={() => {
          setModalOpen(false)
          setEditTarget(null)
        }}
        onSave={handleSave}
      />

      {/* Delete confirm dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('settings.abacTab.confirmDeleteTitle')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm">
            {t('settings.abacTab.confirmDeleteDesc', { name: deleteTarget?.name })}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              {t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
