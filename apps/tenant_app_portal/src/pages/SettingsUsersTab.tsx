import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import SettingsSection from '@/components/SettingsSection'
import TagBindingsDialog from '@/components/TagBindingsDialog'
import TagChips from '@/components/TagChips'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { useTenantUsers } from '@/hooks/useTenantUsers'
import { actionRules, PERMISSIONS } from '@/lib/permissionRules'
import type { TenantUserRole } from '@/lib/tenantUsersApi'
import {
  TAG_RESOURCE_TYPES,
  listTagKeys,
  listTagsForResource,
  type TagKeyDTO,
  type TagValueDTO,
} from '@/lib/tagsApi'
import { Info, RefreshCw, Tag } from 'lucide-react'
import { useEffect, useState } from 'react'

function apiErrorMessage(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: { message?: string; detail?: string } } })?.response
    ?.data
  return data?.message || data?.detail || fallback
}

function DeactivateUserButton({
  label,
  disabled,
  reason,
  onClick,
}: {
  label: string
  disabled: boolean
  reason: string | null
  onClick: () => void
}) {
  const button = (
    <Button size="sm" variant="outline" disabled={disabled} onClick={onClick}>
      {label}
    </Button>
  )
  if (!reason) {
    return button
  }
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex">{button}</span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-left">
          {reason}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

i18n.addResourceBundle('en', 'translation', {
  settings: {
    usersTab: {
      title: 'Users',
      description: 'Manage tenant users and roles',
      usernameCol: 'Username',
      roleCol: 'Role',
      statusCol: 'Status',
      noUsers: 'No users',
      currentUser: 'You',
      selectRole: 'Select role',
      admin: 'Admin',
      member: 'Member',
      viewer: 'Viewer',
      inactive: 'Inactive',
      active: 'Active',
      manageTags: 'Manage Tags',
      reactivate: 'Reactivate',
      resetPassword: 'Reset Password',
      deactivate: 'Deactivate',
      createSuccess: 'User created',
      createFailed: 'Create failed',
      passwordReset: 'Password reset',
      passwordResetFailed: 'Password reset failed',
      userDeactivated: 'User deactivated',
      deactivateFailed: 'Deactivate failed',
      cannotDeactivateSelf: 'You cannot deactivate your own account',
      cannotDeactivateLastAdmin: 'Tenant must keep at least one active admin',
      userReactivated: 'User reactivated',
      reactivateFailed: 'Reactivate failed',
      roleUpdated: 'Role updated',
      roleUpdateFailed: 'Role update failed',
      breakGlassCol: 'Break-glass',
      breakGlassHint: 'Allows password login even when Force SSO is on. Required to enable Force SSO.',
      breakGlassUpdated: 'Break-glass updated',
      breakGlassUpdateFailed: 'Break-glass update failed',
      newUser: {
        title: 'New User',
        description: 'Create a new user account',
        username: 'Username',
        usernamePlaceholder: 'Enter username',
        email: 'Email',
        role: 'Role',
        password: 'Password',
        passwordPlaceholder: 'Enter password',
        createButton: 'Create User',
      },
      resetPasswordDialog: {
        title: 'Reset Password',
        description: 'Enter a new password for the user',
        newPassword: 'New Password',
        confirm: 'Reset',
      },
      deactivateDialog: {
        title: 'Deactivate User',
        description: 'Are you sure you want to deactivate this user?',
      },
      reactivateDialog: {
        title: 'Reactivate User',
        description: 'Are you sure you want to reactivate this user?',
      },
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    usersTab: {
      title: '用户',
      description: '管理租户用户和角色',
      usernameCol: '用户名',
      roleCol: '角色',
      statusCol: '状态',
      noUsers: '暂无用户',
      currentUser: '你',
      selectRole: '选择角色',
      admin: '管理员',
      member: '成员',
      viewer: '只读',
      inactive: '已停用',
      active: '活跃',
      manageTags: '管理标签',
      reactivate: '重新激活',
      resetPassword: '重置密码',
      deactivate: '停用',
      createSuccess: '用户已创建',
      createFailed: '创建失败',
      passwordReset: '密码已重置',
      passwordResetFailed: '密码重置失败',
      userDeactivated: '用户已停用',
      deactivateFailed: '停用失败',
      cannotDeactivateSelf: '不能停用当前登录账号',
      cannotDeactivateLastAdmin: '租户至少需要保留一名活跃管理员',
      userReactivated: '用户已重新激活',
      reactivateFailed: '重新激活失败',
      roleUpdated: '角色已更新',
      roleUpdateFailed: '角色更新失败',
      breakGlassCol: 'Break-glass',
      breakGlassHint: '即使开启强制 SSO 也允许密码登录。启用强制 SSO 的前置条件。',
      breakGlassUpdated: 'Break-glass 已更新',
      breakGlassUpdateFailed: 'Break-glass 更新失败',
      newUser: {
        title: '新建用户',
        description: '创建新用户账号',
        username: '用户名',
        usernamePlaceholder: '请输入用户名',
        email: '邮箱',
        role: '角色',
        password: '密码',
        passwordPlaceholder: '请输入密码',
        createButton: '创建用户',
      },
      resetPasswordDialog: {
        title: '重置密码',
        description: '为用户输入新密码',
        newPassword: '新密码',
        confirm: '重置',
      },
      deactivateDialog: {
        title: '停用用户',
        description: '确定要停用此用户吗？',
      },
      reactivateDialog: {
        title: '重新激活用户',
        description: '确定要重新激活此用户吗？',
      },
    }
  }
}, true, true)

export default function SettingsUsersTab() {
  const { t } = useTranslation()
  const {
    users,
    loading,
    error,
    fetchUsers,
    addUser,
    deactivateUser,
    recoverUserMembership,
    resetPassword,
    updateUserRole,
    setBreakGlass,
  } = useTenantUsers()
  const { user: currentUser, hasAny } = useAuth()
  const { showError, showSuccess } = useNotification()

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<TenantUserRole>('member')
  const [password, setPassword] = useState('')

  const [resetDialogOpen, setResetDialogOpen] = useState(false)
  const [resetUserId, setResetUserId] = useState<number | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')

  const [deactivateDialogOpen, setDeactivateDialogOpen] = useState(false)
  const [deactivateUserId, setDeactivateUserId] = useState<number | null>(null)

  const [recoverDialogOpen, setRecoverDialogOpen] = useState(false)
  const [recoverUserId, setRecoverUserId] = useState<number | null>(null)

  const canReadTags = hasAny(actionRules.canReadTags())
  const canManageTags = hasAny(actionRules.canManageTags())
  const canManageUsers = hasAny([PERMISSIONS.USERS_MANAGE])
  const canManageSso = hasAny([PERMISSIONS.AUTH_PROVIDERS_MANAGE])

  const [tagKeys, setTagKeys] = useState<TagKeyDTO[]>([])
  const [userTags, setUserTags] = useState<Record<number, TagValueDTO[]>>({})

  useEffect(() => {
    fetchUsers().catch(() => undefined)
  }, [fetchUsers])

  useEffect(() => {
    if (!canReadTags) return
    listTagKeys()
      .then(setTagKeys)
      .catch(() => undefined)
  }, [canReadTags])

  useEffect(() => {
    if (!canReadTags || users.length === 0) {
      setUserTags({})
      return
    }

    Promise.all(
      users.map(async (user) => {
        const tags = await listTagsForResource(TAG_RESOURCE_TYPES.USER, user.id)
        return { userId: user.id, tags }
      })
    )
      .then((results) => {
        const next: Record<number, TagValueDTO[]> = {}
        results.forEach(({ userId, tags }) => {
          next[userId] = tags
        })
        setUserTags(next)
      })
      .catch(() => undefined)
  }, [canReadTags, users])

  const handleCreateUser = async () => {
    try {
      await addUser({
        username: username.trim(),
        password,
        role,
        email: email.trim() || undefined,
      })
      setUsername('')
      setEmail('')
      setPassword('')
      showSuccess(t('settings.usersTab.createSuccess'))
    } catch (err: any) {
      showError(apiErrorMessage(err, t('settings.usersTab.createFailed')))
    }
  }

  const handleResetPassword = async () => {
    if (!resetUserId) {
      return
    }
    try {
      await resetPassword(resetUserId, resetPasswordValue)
      setResetDialogOpen(false)
      setResetPasswordValue('')
      showSuccess(t('settings.usersTab.passwordReset'))
    } catch (err: any) {
      showError(apiErrorMessage(err, t('settings.usersTab.passwordResetFailed')))
    }
  }

  const handleDeactivateUser = async () => {
    if (!deactivateUserId) {
      return
    }
    try {
      await deactivateUser(deactivateUserId)
      setDeactivateDialogOpen(false)
      showSuccess(t('settings.usersTab.userDeactivated'))
    } catch (err: any) {
      showError(apiErrorMessage(err, t('settings.usersTab.deactivateFailed')))
    }
  }

  const handleRecoverUser = async () => {
    if (!recoverUserId) {
      return
    }
    try {
      await recoverUserMembership(recoverUserId)
      setRecoverDialogOpen(false)
      showSuccess(t('settings.usersTab.userReactivated'))
    } catch (err: any) {
      showError(apiErrorMessage(err, t('settings.usersTab.reactivateFailed')))
    }
  }

  const activeAdminCount = users.filter(
    (user) => user.role === 'admin' && user.membership_status !== 'inactive'
  ).length

  const deactivateBlockedReason = (userId: number, role: TenantUserRole, membershipStatus: string) => {
    if (userId === currentUser?.id) {
      return t('settings.usersTab.cannotDeactivateSelf')
    }
    if (role === 'admin' && membershipStatus !== 'inactive' && activeAdminCount <= 1) {
      return t('settings.usersTab.cannotDeactivateLastAdmin')
    }
    return null
  }

  const handleRoleChange = async (userId: number, nextRole: TenantUserRole) => {
    const targetUser = users.find((user) => user.id === userId)
    if (!targetUser || targetUser.role === nextRole) {
      return
    }
    try {
      await updateUserRole(userId, { role: nextRole })
      showSuccess(t('settings.usersTab.roleUpdated'))
    } catch (err: any) {
      showError(apiErrorMessage(err, t('settings.usersTab.roleUpdateFailed')))
    }
  }

  const handleBreakGlassChange = async (userId: number, next: boolean) => {
    const targetUser = users.find((user) => user.id === userId)
    if (!targetUser || targetUser.is_break_glass === next) {
      return
    }
    try {
      await setBreakGlass(userId, next)
      showSuccess(t('settings.usersTab.breakGlassUpdated'))
    } catch (err: any) {
      showError(apiErrorMessage(err, t('settings.usersTab.breakGlassUpdateFailed')))
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
        title={t('settings.usersTab.title')}
        description={t('settings.usersTab.description')}
        action={
          <Button variant="outline" size="sm" onClick={() => fetchUsers()} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            {t('common.refresh')}
          </Button>
        }
        contentClassName="p-0"
      >
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-10 w-[40px]">ID</TableHead>
                <TableHead className="h-10">{t('settings.usersTab.usernameCol')}</TableHead>
                <TableHead className="h-10">{t('settings.usersTab.roleCol')}</TableHead>
                <TableHead className="h-10">{t('settings.usersTab.statusCol')}</TableHead>
                <TableHead className="h-10">
                  <div className="flex items-center gap-1.5">
                    {t('settings.usersTab.breakGlassCol')}
                    <TooltipProvider delayDuration={200}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="text-muted-foreground">
                            <Info className="h-3.5 w-3.5" />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs text-left">
                          {t('settings.usersTab.breakGlassHint')}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                </TableHead>
                <TableHead className="h-10 text-right">{t('common.operation')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    {t('settings.usersTab.noUsers')}
                  </TableCell>
                </TableRow>
              ) : (
                users.map((user) => {
                  const blockedReason = deactivateBlockedReason(
                    user.id,
                    user.role,
                    user.membership_status
                  )
                  return (
                  <TableRow key={user.id}>
                    <TableCell className="py-3 text-sm text-muted-foreground">
                      {user.id}
                    </TableCell>
                    <TableCell className="py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{user.username}</span>
                        {user.id === currentUser?.id && (
                          <Badge variant="secondary">
                            {t('settings.usersTab.currentUser')}
                          </Badge>
                        )}
                      </div>
                      {canReadTags && (userTags[user.id]?.length || 0) > 0 && (
                        <TagChips tags={userTags[user.id]} tagKeys={tagKeys} className="mt-2" />
                      )}
                    </TableCell>
                    <TableCell className="py-3">
                      <Select
                        value={user.role}
                        onValueChange={(value) =>
                          handleRoleChange(user.id, value as TenantUserRole)
                        }
                        disabled={
                          !canManageUsers ||
                          loading ||
                          user.membership_status === 'inactive' ||
                          user.id === currentUser?.id ||
                          (user.role === 'admin' && activeAdminCount <= 1)
                        }
                      >
                        <SelectTrigger className="h-8 w-[120px]">
                          <SelectValue placeholder={t('settings.usersTab.selectRole')} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="admin">{t('settings.usersTab.admin')}</SelectItem>
                          <SelectItem value="member">{t('settings.usersTab.member')}</SelectItem>
                          <SelectItem value="viewer">{t('settings.usersTab.viewer')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="py-3">
                      <Badge
                        className={
                          user.membership_status === 'inactive'
                            ? 'border-transparent bg-muted text-muted-foreground'
                            : 'border-transparent bg-success/15 text-success'
                        }
                      >
                        {user.membership_status === 'inactive' ? t('settings.usersTab.inactive') : t('settings.usersTab.active')}
                      </Badge>
                    </TableCell>
                    <TableCell className="py-3">
                      <Switch
                        checked={!!user.is_break_glass}
                        onCheckedChange={(v) => handleBreakGlassChange(user.id, v)}
                        disabled={
                          !canManageSso ||
                          loading ||
                          user.membership_status === 'inactive'
                        }
                        aria-label={t('settings.usersTab.breakGlassCol')}
                      />
                    </TableCell>
                    <TableCell className="py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <TagBindingsDialog
                          resourceType={TAG_RESOURCE_TYPES.USER}
                          resourceId={user.id}
                          title={t('settings.usersTab.manageTags')}
                          canManage={canManageTags}
                          canRead={canReadTags}
                          onTagsUpdated={(resourceId, tags) =>
                            setUserTags((prev) => ({
                              ...prev,
                              [resourceId]: tags,
                            }))
                          }
                        >
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-8 w-8 p-0"
                            disabled={!canReadTags}
                            aria-label={t('settings.usersTab.manageTags')}
                            title={t('settings.usersTab.manageTags')}
                          >
                            <Tag className="w-4 h-4" />
                          </Button>
                        </TagBindingsDialog>
                        {user.membership_status === 'inactive' ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setRecoverUserId(user.id)
                              setRecoverDialogOpen(true)
                            }}
                            >
                              {t('settings.usersTab.reactivate')}
                            </Button>
                          ) : (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  setResetUserId(user.id)
                                  setResetDialogOpen(true)
                                }}
                              >
                                {t('settings.usersTab.resetPassword')}
                              </Button>
                              <DeactivateUserButton
                                label={t('settings.usersTab.deactivate')}
                                disabled={!canManageUsers || !!blockedReason}
                                reason={blockedReason}
                                onClick={() => {
                                  setDeactivateUserId(user.id)
                                  setDeactivateDialogOpen(true)
                                }}
                              />
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
      </SettingsSection>

      <SettingsSection
        title={t('settings.usersTab.newUser.title')}
        description={t('settings.usersTab.newUser.description')}
      >
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="username">{t('settings.usersTab.newUser.username')}</Label>
              <Input
                id="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder={t('settings.usersTab.newUser.usernamePlaceholder')}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">{t('settings.usersTab.newUser.email')}</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="user@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">{t('settings.usersTab.newUser.role')}</Label>
              <Select value={role} onValueChange={(value) => setRole(value as TenantUserRole)}>
                <SelectTrigger id="role">
                  <SelectValue placeholder={t('settings.usersTab.selectRole')} />
                </SelectTrigger>
                <SelectContent>
                <SelectItem value="admin">{t('settings.usersTab.admin')}</SelectItem>
                <SelectItem value="member">{t('settings.usersTab.member')}</SelectItem>
                <SelectItem value="viewer">{t('settings.usersTab.viewer')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">{t('settings.usersTab.newUser.password')}</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={t('settings.usersTab.newUser.passwordPlaceholder')}
              />
            </div>
          </div>
          <div className="flex justify-end mt-4">
            <Button onClick={handleCreateUser} disabled={loading || !username || !password}>
              {t('settings.usersTab.newUser.createButton')}
            </Button>
          </div>
      </SettingsSection>

      <AlertDialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.usersTab.resetPasswordDialog.title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('settings.usersTab.resetPasswordDialog.description')}</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2">
            <Label htmlFor="reset-password">{t('settings.usersTab.resetPasswordDialog.newPassword')}</Label>
            <Input
              id="reset-password"
              type="password"
              value={resetPasswordValue}
              onChange={(event) => setResetPasswordValue(event.target.value)}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleResetPassword}
              disabled={!resetPasswordValue || loading}
            >
              {t('settings.usersTab.resetPasswordDialog.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deactivateDialogOpen} onOpenChange={setDeactivateDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.usersTab.deactivateDialog.title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('settings.usersTab.deactivateDialog.description')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeactivateUser} disabled={loading}>
              {t('common.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={recoverDialogOpen} onOpenChange={setRecoverDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.usersTab.reactivateDialog.title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('settings.usersTab.reactivateDialog.description')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRecoverUser} disabled={loading}>
              {t('common.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}