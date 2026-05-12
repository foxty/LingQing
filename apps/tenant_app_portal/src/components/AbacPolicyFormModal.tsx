import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    abacPolicyForm: {
      createTitle: 'Create Policy',
      editTitle: 'Edit Policy',
      name: 'Name',
      namePlaceholder: 'My Access Policy',
      description: 'Description',
      descPlaceholder: 'Optional description',
      resourceType: 'Resource Type',
      action: 'Action',
      dslExpression: 'DSL Expression',
      validating: 'Validating...',
      valid: 'Valid expression',
      humanReadable: '{{text}}',
      hideReference: 'Hide Reference',
      showReference: 'Show DSL Reference',
      testExpression: 'Test Expression',
      userId: 'User ID',
      resourceId: 'Resource ID',
      userRole: 'User Role',
      running: 'Running...',
      runTest: 'Run Test',
      allowed: 'Access Allowed',
      denied: 'Access Denied',
      reason: '{{reason}}',
      cancel: 'Cancel',
      saving: 'Saving...',
      save: 'Save',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    abacPolicyForm: {
      createTitle: '创建策略',
      editTitle: '编辑策略',
      name: '名称',
      namePlaceholder: '我的访问策略',
      description: '描述',
      descPlaceholder: '可选描述',
      resourceType: '资源类型',
      action: '操作',
      dslExpression: 'DSL 表达式',
      validating: '验证中...',
      valid: '有效的表达式',
      humanReadable: '{{text}}',
      hideReference: '隐藏参考',
      showReference: '显示 DSL 参考',
      testExpression: '测试表达式',
      userId: '用户 ID',
      resourceId: '资源 ID',
      userRole: '用户角色',
      running: '运行中...',
      runTest: '运行测试',
      allowed: '允许访问',
      denied: '拒绝访问',
      reason: '{{reason}}',
      cancel: '取消',
      saving: '保存中...',
      save: '保存',
    },
  },
}, true, true)

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
import { Textarea } from '@/components/ui/textarea'
import { useSimulatePolicy } from '@/hooks/useAbacPolicies'
import { useAbacPolicyValidation } from '@/hooks/useAbacPolicyValidation'
import type {
  AbacAction,
  AbacPolicy,
  AbacPolicyCreatePayload,
  ResourceType,
} from '@/lib/abacPolicyApi'

const RESOURCE_TYPES: ResourceType[] = ['document_collection', 'data_source', 'api_connector', 'user']
const ABAC_ACTIONS: AbacAction[] = ['read', 'write']

const DSL_REFERENCE = `Attribute reference:
  :user.id           – current user's numeric ID (scalar)
  :user.role         – current user's role string (scalar)
  :user.tags         – current user's tags set (e.g. "dept:sales")
  :resource.tags     – resource's tags set
  :resource.id       – resource's numeric ID
  :resource.owner_id – resource owner's user ID

Operators:
  :user.role equals "admin"
  :user.id in ("1", "2", "3")
  :user.tags has "dept:sales"
  :user.tags has "dept:*"
  :user.tags contains :resource.tags
  :user.tags contains :resource.tags on ("dept", "region")
  :user.id equals :resource.owner_id
  :user.tags rank_gte :resource.tags on "数据安全性"
  :user.tags rank_gt  :resource.tags on "数据安全性"
  :user.tags rank_lte :resource.tags on "数据安全性"
  :user.tags rank_lt  :resource.tags on "数据安全性"
  :user.tags rank_eq  :resource.tags on "数据安全性"

Notes:
  'on (...)' scope is supported only for ':user.tags contains :resource.tags'
  and for rank operators ('rank_gte/rank_gt/rank_lte/rank_lt/rank_eq').

Combine with: and / or / ( )`

interface AbacPolicyFormModalProps {
  open: boolean
  initial: AbacPolicy | null
  onClose: () => void
  onSave: (payload: AbacPolicyCreatePayload) => Promise<void>
}

export default function AbacPolicyFormModal({
  open,
  initial,
  onClose,
  onSave,
}: AbacPolicyFormModalProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [resourceType, setResourceType] = useState<ResourceType>('document_collection')
  const [action, setAction] = useState<AbacAction>('read')
  const [expression, setExpression] = useState('')
  const [saving, setSaving] = useState(false)
  const [showReference, setShowReference] = useState(false)

  const [showSimulate, setShowSimulate] = useState(false)
  const [simUserId, setSimUserId] = useState('')
  const [simResourceId, setSimResourceId] = useState('')
  const [simUserRole, setSimUserRole] = useState('')
  const {
    result: simResult,
    loading: simLoading,
    error: simError,
    run: runSim,
  } = useSimulatePolicy()

  const { result: validation, isValidating } = useAbacPolicyValidation(expression)

  useEffect(() => {
    if (initial) {
      setName(initial.name)
      setDescription(initial.description ?? '')
      setResourceType(initial.resource_type)
      setAction(initial.action)
      setExpression(initial.expression)
    } else {
      setName('')
      setDescription('')
      setResourceType('document_collection')
      setAction('read')
      setExpression('')
    }
    setSaving(false)
    setShowReference(false)
    setShowSimulate(false)
  }, [initial, open])

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave({
        name,
        description: description || null,
        resource_type: resourceType,
        action,
        expression,
      })
      onClose()
    } finally {
      setSaving(false)
    }
  }

  const handleSimulate = async () => {
    await runSim({
      expression,
      resource_type: resourceType,
      user_id: Number(simUserId),
      resource_id: Number(simResourceId),
      user_role: simUserRole || null,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initial ? t('components.abacPolicyForm.editTitle') : t('components.abacPolicyForm.createTitle')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>{t('components.abacPolicyForm.name')}</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('components.abacPolicyForm.namePlaceholder')} />
          </div>

          <div>
            <Label>{t('components.abacPolicyForm.description')}</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('components.abacPolicyForm.descPlaceholder')}
              rows={2}
            />
          </div>

          <div>
            <Label>{t('components.abacPolicyForm.resourceType')}</Label>
            <Select value={resourceType} onValueChange={(v) => setResourceType(v as ResourceType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RESOURCE_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>{t('components.abacPolicyForm.action')}</Label>
            <Select value={action} onValueChange={(v) => setAction(v as AbacAction)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ABAC_ACTIONS.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>{t('components.abacPolicyForm.dslExpression')}</Label>
            <Textarea
              value={expression}
              onChange={(e) => setExpression(e.target.value)}
              placeholder=':user.role equals "admin"'
              rows={3}
              className="font-mono text-sm"
            />

            {expression.trim() && (
              <div className="mt-2">
                {isValidating && <p className="text-xs text-muted-foreground">{t('components.abacPolicyForm.validating')}</p>}
                {!isValidating && validation && (
                  <div>
                    {validation.valid ? (
                      <Alert className="border-green-500 bg-green-50 dark:bg-green-950">
                        <AlertDescription className="text-green-700 dark:text-green-300 text-xs">
                          <span className="font-semibold">✓ {t('components.abacPolicyForm.valid')}</span>
                          {validation.human_readable && (
                            <> &mdash; {t('components.abacPolicyForm.humanReadable', { text: validation.human_readable })}</>
                          )}
                        </AlertDescription>
                      </Alert>
                    ) : (
                      <Alert variant="destructive">
                        <AlertDescription className="text-xs">
                          {validation.errors.join(' ')}
                        </AlertDescription>
                      </Alert>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="mt-2">
              <button
                type="button"
                className="text-xs text-muted-foreground underline"
                onClick={() => setShowReference((v) => !v)}
              >
                {showReference ? t('components.abacPolicyForm.hideReference') : t('components.abacPolicyForm.showReference')}
              </button>
              {showReference && (
                <pre className="mt-2 text-xs bg-muted rounded p-3 whitespace-pre-wrap font-mono">
                  {DSL_REFERENCE}
                </pre>
              )}
            </div>
          </div>

          <div className="border rounded-md">
            <button
              type="button"
              className="w-full text-left text-sm font-medium px-3 py-2 flex justify-between"
              onClick={() => setShowSimulate((v) => !v)}
            >
              <span>{t('components.abacPolicyForm.testExpression')}</span>
              <span className="text-muted-foreground">{showSimulate ? '▲' : '▼'}</span>
            </button>
            {showSimulate && (
              <div className="px-3 pb-3 space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <Label className="text-xs">{t('components.abacPolicyForm.userId')}</Label>
                    <Input
                      type="number"
                      value={simUserId}
                      onChange={(e) => setSimUserId(e.target.value)}
                      placeholder="42"
                    />
                  </div>
                  <div>
                    <Label className="text-xs">{t('components.abacPolicyForm.resourceId')}</Label>
                    <Input
                      type="number"
                      value={simResourceId}
                      onChange={(e) => setSimResourceId(e.target.value)}
                      placeholder="7"
                    />
                  </div>
                  <div>
                    <Label className="text-xs">{t('components.abacPolicyForm.userRole')}</Label>
                    <Input
                      value={simUserRole}
                      onChange={(e) => setSimUserRole(e.target.value)}
                      placeholder="admin"
                    />
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSimulate}
                  disabled={simLoading || !expression.trim() || !simUserId || !simResourceId}
                >
                  {simLoading ? t('components.abacPolicyForm.running') : t('components.abacPolicyForm.runTest')}
                </Button>
                {simError && <p className="text-xs text-destructive">{simError}</p>}
                {simResult && (
                  <Alert
                    className={
                      simResult.allowed
                        ? 'border-green-500 bg-green-50 dark:bg-green-950'
                        : 'border-red-500 bg-red-50 dark:bg-red-950'
                    }
                  >
                    <AlertDescription
                      className={`text-xs ${simResult.allowed ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}`}
                    >
                      {simResult.allowed ? `✓ ${t('components.abacPolicyForm.allowed')}` : `✗ ${t('components.abacPolicyForm.denied')}`} &mdash; {t('components.abacPolicyForm.reason', { reason: simResult.reason })}
                    </AlertDescription>
                  </Alert>
                )}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('components.abacPolicyForm.cancel')}
          </Button>
          <Button onClick={handleSave} disabled={saving || !name.trim() || !expression.trim()}>
            {saving ? t('components.abacPolicyForm.saving') : t('components.abacPolicyForm.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
