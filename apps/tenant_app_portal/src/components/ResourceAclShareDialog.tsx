import { useEffect, useMemo, useState } from 'react'

import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    shareDialog: {
      title: 'Share',
      newShare: 'New Share',
      user: 'User',
      searchUser: 'Search user...',
      searchPlaceholder: 'Type to search...',
      searching: 'Searching...',
      noUsersFound: 'No users found',
      hint: 'Search for a user to share with',
      permission: 'Permission',
      readOnly: 'Read Only',
      readWrite: 'Read & Write',
      addShare: 'Add Share',
      sharedUsers: 'Shared Users',
      currentAccess: 'Current Access',
      loading: 'Loading...',
      noShares: 'No shares yet',
      permissionLabel: '{{perm}}',
      close: 'Close',
      cancel: 'Revoke',
      shareSuccess: 'Shared successfully',
      shareFailed: 'Failed to share',
      unshareSuccess: 'Access revoked',
      unshareFailed: 'Failed to revoke access',
      loadFailed: 'Failed to load shares',
      loadCandidatesFailed: 'Failed to load users',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    shareDialog: {
      title: '共享',
      newShare: '新建共享',
      user: '用户',
      searchUser: '搜索用户...',
      searchPlaceholder: '输入搜索...',
      searching: '搜索中...',
      noUsersFound: '未找到用户',
      hint: '搜索要共享的用户',
      permission: '权限',
      readOnly: '只读',
      readWrite: '读写',
      addShare: '添加共享',
      sharedUsers: '已共享用户',
      currentAccess: '当前访问',
      loading: '加载中...',
      noShares: '暂无共享',
      permissionLabel: '{{perm}}',
      close: '关闭',
      cancel: '撤销',
      shareSuccess: '共享成功',
      shareFailed: '共享失败',
      unshareSuccess: '访问已撤销',
      unshareFailed: '撤销访问失败',
      loadFailed: '加载共享列表失败',
      loadCandidatesFailed: '加载用户列表失败',
    },
  },
}, true, true)
import { Button } from '@/components/ui/button'
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
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { useNotification } from '@/hooks/useNotification'
import {
  listAclShareCandidates,
  listAclResourceShares,
  revokeAclResourceShare,
  shareAclResource,
  type AclShareCandidate,
  type AclShareEntry,
  type AclSharePermission,
  type AclShareResourceType,
} from '@/lib/aclSharesApi'
import { Check, ChevronsUpDown } from 'lucide-react'

interface ResourceAclShareDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  resourceType: AclShareResourceType
  resourceId: number
  resourceTitle: string
}

export default function ResourceAclShareDialog({
  open,
  onOpenChange,
  resourceType,
  resourceId,
  resourceTitle,
}: ResourceAclShareDialogProps) {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()

  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [shares, setShares] = useState<AclShareEntry[]>([])
  const [canManage, setCanManage] = useState(false)
  const [candidatesOpen, setCandidatesOpen] = useState(false)
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [candidates, setCandidates] = useState<AclShareCandidate[]>([])
  const [candidateQuery, setCandidateQuery] = useState('')
  const [selectedUserId, setSelectedUserId] = useState<string>('')
  const [selectedUsername, setSelectedUsername] = useState('')
  const [selectedPermission, setSelectedPermission] = useState<AclSharePermission>('read')

  const loadData = async () => {
    setLoading(true)
    try {
      const result = await listAclResourceShares(resourceType, resourceId)
      setShares(result.shares)
      setCanManage(result.can_manage)
    } catch (error: any) {
      showError(error?.response?.data?.detail || t('components.shareDialog.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const loadCandidates = async (query: string) => {
    if (!canManage) {
      setCandidates([])
      return
    }
    setLoadingCandidates(true)
    try {
      const rows = await listAclShareCandidates(resourceType, resourceId, {
        q: query,
        limit: 20,
      })
      setCandidates(rows)
    } catch (error: any) {
      showError(error?.response?.data?.detail || t('components.shareDialog.loadCandidatesFailed'))
    } finally {
      setLoadingCandidates(false)
    }
  }

  useEffect(() => {
    if (!open) {
      return
    }
    setSelectedUserId('')
    setSelectedUsername('')
    setCandidateQuery('')
    setCandidates([])
    setCandidatesOpen(false)
    setSelectedPermission('read')
    setCanManage(false)
    void loadData()
  }, [open, resourceType, resourceId])

  useEffect(() => {
    if (!open || !canManage || !candidatesOpen) {
      return
    }
    const timer = window.setTimeout(() => {
      void loadCandidates(candidateQuery)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [open, canManage, candidatesOpen, candidateQuery, resourceType, resourceId])

  const selectedCandidateLabel = useMemo(() => {
    if (selectedUsername) {
      return selectedUsername
    }
    const matchedCandidate = candidates.find((candidate) => String(candidate.id) === selectedUserId)
    return matchedCandidate?.username ?? ''
  }, [candidates, selectedUserId, selectedUsername])

  const handleShare = async () => {
    if (!selectedUserId) {
      showError(t('common.noData'))
      return
    }
    setSubmitting(true)
    try {
      await shareAclResource(resourceType, resourceId, {
        user_id: Number(selectedUserId),
        permission: selectedPermission,
      })
      showSuccess(t('components.shareDialog.shareSuccess'))
      setSelectedUserId('')
      setSelectedUsername('')
      setCandidateQuery('')
      setCandidates([])
      setCandidatesOpen(false)
      await loadData()
    } catch (error: any) {
      showError(error?.response?.data?.detail || t('components.shareDialog.shareFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleRevoke = async (userId: number) => {
    setSubmitting(true)
    try {
      await revokeAclResourceShare(resourceType, resourceId, userId)
      showSuccess(t('components.shareDialog.unshareSuccess'))
      await loadData()
    } catch (error: any) {
      showError(error?.response?.data?.detail || t('components.shareDialog.unshareFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t('components.shareDialog.title')}</DialogTitle>
          <DialogDescription className="truncate">{resourceTitle}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {canManage && (
            <div className="rounded-md border p-4">
              <div className="text-sm font-medium">{t('components.shareDialog.newShare')}</div>
              <div className="mt-3 grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="share-user">{t('components.shareDialog.user')}</Label>
                  <Popover open={candidatesOpen} onOpenChange={setCandidatesOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        id="share-user"
                        variant="outline"
                        role="combobox"
                        aria-expanded={candidatesOpen}
                        className="w-full justify-between font-normal"
                      >
                        <span className="truncate">
                          {selectedCandidateLabel || t('components.shareDialog.searchUser')}
                        </span>
                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
                      <div className="border-b p-2">
                        <Input
                          value={candidateQuery}
                          onChange={(event) => setCandidateQuery(event.target.value)}
                          placeholder={t('components.shareDialog.searchPlaceholder')}
                          autoFocus
                        />
                      </div>
                      <div className="max-h-64 overflow-y-auto p-1">
                        {loadingCandidates ? (
                          <div className="px-2 py-6 text-sm text-muted-foreground">{t('components.shareDialog.searching')}</div>
                        ) : candidates.length === 0 ? (
                          <div className="px-2 py-6 text-sm text-muted-foreground">{t('components.shareDialog.noUsersFound')}</div>
                        ) : (
                          candidates.map((candidate) => {
                            const isSelected = selectedUserId === String(candidate.id)
                            return (
                              <button
                                key={candidate.id}
                                type="button"
                                className="flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                                onClick={() => {
                                  setSelectedUserId(String(candidate.id))
                                  setSelectedUsername(candidate.username)
                                  setCandidatesOpen(false)
                                }}
                              >
                                <span className="truncate">{candidate.username}</span>
                                {isSelected && <Check className="ml-2 h-4 w-4 shrink-0" />}
                              </button>
                            )
                          })
                        )}
                      </div>
                    </PopoverContent>
                  </Popover>
                  <div className="text-xs text-muted-foreground">{t('components.shareDialog.hint')}</div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="share-permission">{t('components.shareDialog.permission')}</Label>
                  <RadioGroup
                    id="share-permission"
                    value={selectedPermission}
                    onValueChange={(value: string) => setSelectedPermission(value as AclSharePermission)}
                    className="grid grid-cols-2 gap-2"
                  >
                    <label className="flex items-center gap-2 rounded-md border px-3 py-2 cursor-pointer hover:bg-accent/40">
                      <RadioGroupItem value="read" />
                      <span className="text-sm font-medium">{t('components.shareDialog.readOnly')}</span>
                    </label>
                    <label className="flex items-center gap-2 rounded-md border px-3 py-2 cursor-pointer hover:bg-accent/40">
                      <RadioGroupItem value="write" />
                      <span className="text-sm font-medium">{t('components.shareDialog.readWrite')}</span>
                    </label>
                  </RadioGroup>
                </div>
                <div className="md:col-span-2 flex justify-end">
                  <Button
                    onClick={handleShare}
                    disabled={submitting || loading || !selectedUserId}
                  >
                    {t('components.shareDialog.addShare')}
                  </Button>
                </div>
              </div>
            </div>
          )}

          <div className="rounded-md border">
            <div className="px-3 py-2 border-b text-sm font-medium">
              {canManage ? t('components.shareDialog.sharedUsers') : t('components.shareDialog.currentAccess')}
            </div>
            {loading ? (
              <div className="px-3 py-6 text-sm text-muted-foreground">{t('components.shareDialog.loading')}</div>
            ) : shares.length === 0 ? (
              <div className="px-3 py-6 text-sm text-muted-foreground">{t('components.shareDialog.noShares')}</div>
            ) : (
              <div className="divide-y">
                {shares.map((share) => (
                  <div key={share.id} className="px-3 py-2 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">
                        {share.shared_with_username || `${t('common.owner')} ${share.shared_with_user_id}`}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {t('components.shareDialog.permissionLabel', { perm: share.permission === 'write' ? t('components.shareDialog.readWrite') : t('components.shareDialog.readOnly') })}
                      </div>
                    </div>
                    {canManage && (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={submitting}
                        onClick={() => void handleRevoke(share.shared_with_user_id)}
                      >
                        {t('components.shareDialog.cancel')}
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('components.shareDialog.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
