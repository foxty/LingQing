import { useEffect, useMemo, useState } from 'react'

import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    shareDialog: {
      title: 'Share',
      titleWithName: 'Share “{{name}}”',
      peopleWithAccess: 'People with access',
      addPeoplePlaceholder: 'Add people by username',
      shareAction: 'Share',
      owner: 'Owner',
      youMarker: '(you)',
      removeAccess: 'Remove access',
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
      shareListFilterPlaceholder: 'Filter shared users...',
      shareListNoMatches: 'No users match this filter',
      shareListCount: '{{count}} with access',
      shareListShowing: '{{shown}} of {{total}} shown',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    shareDialog: {
      title: '共享',
      titleWithName: '共享「{{name}}」',
      peopleWithAccess: '可访问的用户',
      addPeoplePlaceholder: '按用户名添加用户',
      shareAction: '共享',
      owner: '所有者',
      youMarker: '（你）',
      removeAccess: '移除访问',
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
      shareListFilterPlaceholder: '筛选已共享用户...',
      shareListNoMatches: '没有匹配的用户',
      shareListCount: '共 {{count}} 人',
      shareListShowing: '显示 {{shown}} / {{total}} 人',
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
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { cn } from '@/lib/utils'
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

function shareAvatarClass(name: string): string {
  const palette = [
    'bg-muted text-muted-foreground',
    'bg-primary/15 text-primary',
    'bg-accent text-accent-foreground',
    'bg-secondary text-secondary-foreground',
  ]
  let hash = 0
  for (let i = 0; i < name.length; i += 1) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return palette[Math.abs(hash) % palette.length]
}

function avatarInitial(username: string): string {
  const trimmed = username.trim()
  if (!trimmed) {
    return '?'
  }
  const first = trimmed[0]
  if (/[\u4e00-\u9fff]/.test(first)) {
    return first
  }
  return first.toUpperCase()
}

interface ResourceAclShareDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  resourceType: AclShareResourceType
  resourceId: number
  resourceTitle: string
  hint?: string
}

export default function ResourceAclShareDialog({
  open,
  onOpenChange,
  resourceType,
  resourceId,
  resourceTitle,
  hint,
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
  const { user: authUser } = useAuth()

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

  const sortedShares = useMemo(() => {
    const hideSelfBecauseOwnerRow =
      canManage && authUser?.id != null ? shares.some((s) => s.shared_with_user_id === authUser.id) : false
    const rows =
      hideSelfBecauseOwnerRow && authUser?.id != null
        ? shares.filter((share) => share.shared_with_user_id !== authUser.id)
        : shares
    return [...rows].sort((a, b) => {
      const nameA = (a.shared_with_username || `#${a.shared_with_user_id}`).toLowerCase()
      const nameB = (b.shared_with_username || `#${b.shared_with_user_id}`).toLowerCase()
      return nameA.localeCompare(nameB)
    })
  }, [shares, authUser?.id, canManage])

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

  const handleChangeSharePermission = async (userId: number, next: AclSharePermission) => {
    const row = shares.find((s) => s.shared_with_user_id === userId)
    if (!row || row.permission === next) {
      return
    }
    setSubmitting(true)
    try {
      await shareAclResource(resourceType, resourceId, {
        user_id: userId,
        permission: next,
      })
      showSuccess(t('components.shareDialog.shareSuccess'))
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

  const showOwnerRow = canManage && !!authUser?.username
  const ownerDisplayName = authUser?.username ?? ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[min(92vh,640px)] min-h-0 flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
        <DialogHeader className="shrink-0 space-y-1 px-6 pb-3 pt-6">
          <DialogTitle className="text-left text-base font-medium leading-snug pr-8">
            {t('components.shareDialog.titleWithName', { name: resourceTitle })}
          </DialogTitle>
          {hint ? (
            <DialogDescription className="text-left text-xs text-muted-foreground">{hint}</DialogDescription>
          ) : null}
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-hidden px-6 pb-2">
          <div className="flex min-h-0 flex-1 flex-col gap-0">
            {canManage ? (
              <div className="shrink-0 border-b border-border pb-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
                  <Popover open={candidatesOpen} onOpenChange={setCandidatesOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        id="share-user"
                        variant="outline"
                        role="combobox"
                        aria-expanded={candidatesOpen}
                        className="h-10 min-h-10 w-full flex-1 justify-between font-normal sm:min-w-0"
                      >
                        <span className="truncate text-left text-muted-foreground">
                          {selectedCandidateLabel || t('components.shareDialog.addPeoplePlaceholder')}
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
                          className="h-9"
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
                  <div className="flex gap-2 sm:shrink-0">
                    <Select
                      value={selectedPermission}
                      onValueChange={(value: string) => setSelectedPermission(value as AclSharePermission)}
                    >
                      <SelectTrigger className="h-10 w-full sm:w-[148px]" aria-label={t('components.shareDialog.permission')}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="read">{t('components.shareDialog.readOnly')}</SelectItem>
                        <SelectItem value="write">{t('components.shareDialog.readWrite')}</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button
                      className="h-10 shrink-0 px-4"
                      onClick={handleShare}
                      disabled={submitting || loading || !selectedUserId}
                    >
                      {t('components.shareDialog.shareAction')}
                    </Button>
                  </div>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{t('components.shareDialog.hint')}</p>
              </div>
            ) : null}

            <div className={cn('flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden pt-4', canManage ? '' : 'pt-0')}>
              <div className="shrink-0 pb-2 text-sm font-medium text-foreground">
                {canManage ? t('components.shareDialog.peopleWithAccess') : t('components.shareDialog.currentAccess')}
              </div>
              {loading ? (
                <div className="py-8 text-sm text-muted-foreground">{t('components.shareDialog.loading')}</div>
              ) : !showOwnerRow && sortedShares.length === 0 ? (
                <div className="py-8 text-sm text-muted-foreground">{t('components.shareDialog.noShares')}</div>
              ) : (
                <div
                  className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain [scrollbar-gutter:stable] max-h-[min(48vh,22rem)] sm:max-h-[min(52vh,24rem)]"
                  data-share-people-list
                >
                  <ul className="divide-y divide-border">
                    {showOwnerRow ? (
                      <li className="flex items-center gap-3 py-3 first:pt-0">
                        <div
                          className={cn(
                            'flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium',
                            shareAvatarClass(ownerDisplayName)
                          )}
                          aria-hidden
                        >
                          {avatarInitial(ownerDisplayName)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium">{ownerDisplayName}</div>
                          <div className="text-xs text-muted-foreground">{t('components.shareDialog.owner')}</div>
                        </div>
                        <span className="shrink-0 text-sm text-muted-foreground">{t('components.shareDialog.owner')}</span>
                      </li>
                    ) : null}
                    {sortedShares.map((share) => {
                      const display = share.shared_with_username || `#${share.shared_with_user_id}`
                      const isYou = authUser?.id === share.shared_with_user_id
                      return (
                        <li key={share.id} className="flex items-center gap-3 py-3">
                          <div
                            className={cn(
                              'flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium',
                              shareAvatarClass(display)
                            )}
                            aria-hidden
                          >
                            {avatarInitial(display)}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0">
                              <span className="truncate text-sm font-medium">{display}</span>
                              {isYou ? (
                                <span className="shrink-0 text-xs text-muted-foreground">{t('components.shareDialog.youMarker')}</span>
                              ) : null}
                            </div>
                          </div>
                          {canManage ? (
                            <div className="flex shrink-0 items-center gap-1">
                              <Select
                                value={share.permission}
                                onValueChange={(value: string) =>
                                  void handleChangeSharePermission(share.shared_with_user_id, value as AclSharePermission)
                                }
                                disabled={submitting || loading}
                              >
                                <SelectTrigger className="h-9 w-[132px] border-0 bg-transparent px-2 shadow-none hover:bg-accent/50 focus:ring-0">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent align="end">
                                  <SelectItem value="read">{t('components.shareDialog.readOnly')}</SelectItem>
                                  <SelectItem value="write">{t('components.shareDialog.readWrite')}</SelectItem>
                                </SelectContent>
                              </Select>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-9 text-muted-foreground hover:text-destructive"
                                disabled={submitting || loading}
                                onClick={() => void handleRevoke(share.shared_with_user_id)}
                              >
                                {t('components.shareDialog.removeAccess')}
                              </Button>
                            </div>
                          ) : (
                            <span className="shrink-0 text-sm text-muted-foreground">
                              {share.permission === 'write'
                                ? t('components.shareDialog.readWrite')
                                : t('components.shareDialog.readOnly')}
                            </span>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter className="shrink-0 border-t border-border px-6 py-3 sm:justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('components.shareDialog.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
