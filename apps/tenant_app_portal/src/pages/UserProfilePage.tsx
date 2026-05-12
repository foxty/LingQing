import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { useUserProfile } from '@/hooks/useUserProfile'
import { formatDate } from '@/lib/dateTime'
import {
  listTagKeys,
  listTagsForCurrentUser,
  type TagKeyDTO,
  type TagValueDTO,
} from '@/lib/tagsApi'
import TagChips from '@/components/TagChips'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { AlertCircle, Loader2, User as UserIcon } from 'lucide-react'

i18n.addResourceBundle('en', 'translation', {
  userProfile: {
    title: 'User Profile',
    description: 'Manage your account settings and preferences',
    userInfo: 'User Information',
    userId: 'User ID',
    username: 'Username',
    tenantId: 'Tenant ID',
    tenantName: 'Tenant Name',
    email: 'Email',
    notSet: 'Not set',
    role: 'Role',
    accountStatus: 'Account Status',
    active: 'Active',
    lastLogin: 'Last Login',
    neverLoggedIn: 'Never logged in',
    registrationTime: 'Registration Time',
    tags: 'Tags',
    noTags: 'No tags',
    timezone: 'Timezone',
    timezoneDesc: 'Set your preferred timezone for timestamps',
    currentTimezone: 'Current timezone: {{tz}}',
    saveTimezone: 'Save Timezone',
    changePassword: 'Change Password',
    changePasswordDesc: 'Update your account password',
    currentPassword: 'Current Password',
    currentPasswordPlaceholder: 'Enter current password',
    newPassword: 'New Password',
    newPasswordPlaceholder: 'Enter new password',
    passwordRequirements: 'Password must be at least 8 characters with uppercase, lowercase, and a number',
    confirmPassword: 'Confirm Password',
    confirmPasswordPlaceholder: 'Confirm new password',
    reset: 'Reset',
    saving: 'Saving...',
    save: 'Save Password',
    oldPasswordRequired: 'Current password is required',
    passwordMinLength: 'Password must be at least 8 characters',
    passwordRequireUppercase: 'Password must contain an uppercase letter',
    passwordRequireLowercase: 'Password must contain a lowercase letter',
    passwordRequireDigit: 'Password must contain a digit',
    confirmPasswordRequired: 'Please confirm your password',
    passwordMismatch: 'Passwords do not match',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  userProfile: {
    title: '用户信息',
    description: '管理您的账户设置和偏好',
    userInfo: '用户信息',
    userId: '用户ID',
    username: '用户名',
    tenantId: '租户ID',
    tenantName: '租户名称',
    email: '邮箱',
    notSet: '未设置',
    role: '角色',
    accountStatus: '账户状态',
    active: '活跃',
    lastLogin: '最后登录',
    neverLoggedIn: '从未登录',
    registrationTime: '注册时间',
    tags: '标签',
    noTags: '暂无标签',
    timezone: '时区',
    timezoneDesc: '设置您偏好的时区以显示时间戳',
    currentTimezone: '当前时区：{{tz}}',
    saveTimezone: '保存时区',
    changePassword: '修改密码',
    changePasswordDesc: '更新您的账户密码',
    currentPassword: '当前密码',
    currentPasswordPlaceholder: '请输入当前密码',
    newPassword: '新密码',
    newPasswordPlaceholder: '请输入新密码',
    passwordRequirements: '密码至少8位，需包含大写字母、小写字母和数字',
    confirmPassword: '确认密码',
    confirmPasswordPlaceholder: '请确认新密码',
    reset: '重置',
    saving: '保存中...',
    save: '保存密码',
    oldPasswordRequired: '请输入当前密码',
    passwordMinLength: '密码至少8位',
    passwordRequireUppercase: '密码必须包含大写字母',
    passwordRequireLowercase: '密码必须包含小写字母',
    passwordRequireDigit: '密码必须包含数字',
    confirmPasswordRequired: '请确认密码',
    passwordMismatch: '两次输入的密码不一致',
  }
}, true, true)

function createPasswordSchema(t: (key: string) => string) {
  return z
    .object({
      oldPassword: z.string().min(1, t('userProfile.oldPasswordRequired')),
      newPassword: z
        .string()
        .min(8, t('userProfile.passwordMinLength'))
        .regex(/[A-Z]/, t('userProfile.passwordRequireUppercase'))
        .regex(/[a-z]/, t('userProfile.passwordRequireLowercase'))
        .regex(/\d/, t('userProfile.passwordRequireDigit')),
      confirmPassword: z.string().min(1, t('userProfile.confirmPasswordRequired')),
    })
    .refine((data) => data.newPassword === data.confirmPassword, {
      message: t('userProfile.passwordMismatch'),
      path: ['confirmPassword'],
    })
}

type PasswordFormData = z.infer<ReturnType<typeof createPasswordSchema>>

const COMMON_TIMEZONES = [
  'UTC',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Los_Angeles',
  'Australia/Sydney',
] as const

export default function UserProfilePage() {
  const { t } = useTranslation()
  const { profile, loading, error, fetchProfile, handleChangePassword, handleUpdateTimezone } =
    useUserProfile()
  const [tagKeys, setTagKeys] = useState<TagKeyDTO[]>([])
  const [userTags, setUserTags] = useState<TagValueDTO[]>([])
  const [timezoneIana, setTimezoneIana] = useState('')
  const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  const timezoneOptions = Array.from(new Set([...COMMON_TIMEZONES, browserTimezone]))

  const passwordSchema = useMemo(() => createPasswordSchema(t), [t])

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PasswordFormData>({
    resolver: zodResolver(passwordSchema),
  })

  useEffect(() => {
    fetchProfile()
  }, [])

  useEffect(() => {
    listTagKeys()
      .then(setTagKeys)
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    listTagsForCurrentUser()
      .then(setUserTags)
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (profile) {
      setTimezoneIana(
        profile.preferences?.timezone_iana || Intl.DateTimeFormat().resolvedOptions().timeZone || ''
      )
    }
  }, [profile])

  const onSubmit = async (data: PasswordFormData) => {
    try {
      await handleChangePassword(data)
      reset()
    } catch {
      // Error already handled in hook
    }
  }

  const onTimezoneSubmit = async () => {
    const normalized = timezoneIana.trim()
    if (!normalized) return
    try {
      await handleUpdateTimezone(normalized)
    } catch {
      // Error already handled in hook
    }
  }

  if (loading && !profile) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center space-x-2">
          <UserIcon className="h-6 w-6" />
          <h1 className="text-2xl font-semibold">{t('userProfile.title')}</h1>
        </div>
        <p className="hidden text-sm text-muted-foreground md:block">{t('userProfile.description')}</p>
      </div>

      {/* User Information Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t('userProfile.userInfo')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {profile && (
            <div className="space-y-3">
              <div className="grid grid-cols-1 gap-x-10 gap-y-4 text-sm md:grid-cols-2">
                <p>
                  <span className="text-muted-foreground">{t('userProfile.userId')}: </span>
                  <span className="font-medium">{profile.id}</span>
                </p>
                <p>
                  <span className="text-muted-foreground">{t('userProfile.username')}: </span>
                  <span className="font-medium">{profile.username}</span>
                </p>
                <p>
                  <span className="text-muted-foreground">{t('userProfile.tenantId')}: </span>
                  <span className="font-medium">{profile.tenant_id}</span>
                </p>
                <p>
                  <span className="text-muted-foreground">{t('userProfile.tenantName')}: </span>
                  <span className="font-medium">{profile.tenant_name}</span>
                </p>
                <p className="break-all">
                  <span className="text-muted-foreground">{t('userProfile.email')}: </span>
                  <span className="font-medium">{profile.email || t('userProfile.notSet')}</span>
                </p>
                <p>
                  <span className="text-muted-foreground">{t('userProfile.role')}: </span>
                  <span className="font-medium">{profile.role}</span>
                </p>
                <p>
                  <span className="text-muted-foreground">{t('userProfile.accountStatus')}: </span>
                  <span className="font-medium">
                    {profile.status === 'active' ? t('userProfile.active') : profile.status}
                  </span>
                </p>
                <p>
                  <span className="text-muted-foreground">{t('userProfile.lastLogin')}: </span>
                  <span className="font-medium">
                    {formatDate(profile.last_login_at, { fallback: t('userProfile.neverLoggedIn') })}
                  </span>
                </p>
                <p>
                  <span className="text-muted-foreground">{t('userProfile.registrationTime')}: </span>
                  <span className="font-medium">{formatDate(profile.created_at)}</span>
                </p>
              </div>

              <div className="border-t border-border/70 pt-3 text-sm">
                <span className="text-muted-foreground">{t('userProfile.tags')}: </span>
                {userTags.length > 0 ? (
                  <div className="mt-2">
                    <TagChips tags={userTags} tagKeys={tagKeys} />
                  </div>
                ) : (
                  <span className="text-muted-foreground">{t('userProfile.noTags')}</span>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Timezone Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t('userProfile.timezone')}</CardTitle>
          <CardDescription>
            {t('userProfile.timezoneDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div className="space-y-2">
            <Label>Timezone (IANA)</Label>
            <Select value={timezoneIana} onValueChange={setTimezoneIana} disabled={loading}>
              <SelectTrigger>
                <SelectValue placeholder="Select timezone" />
              </SelectTrigger>
              <SelectContent>
                {timezoneOptions.map((tz) => (
                  <SelectItem key={tz} value={tz}>
                    {tz}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {t('userProfile.currentTimezone', { tz: profile?.preferences?.timezone_iana || t('userProfile.notSet') })}
            </p>
          </div>
          <div className="flex justify-end">
            <Button onClick={onTimezoneSubmit} disabled={loading || !timezoneIana.trim()}>
              {t('userProfile.saveTimezone')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Change Password Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t('userProfile.changePassword')}</CardTitle>
          <CardDescription>{t('userProfile.changePasswordDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="oldPassword">{t('userProfile.currentPassword')}</Label>
              <Input
                id="oldPassword"
                type="password"
                placeholder={t('userProfile.currentPasswordPlaceholder')}
                {...register('oldPassword')}
                disabled={isSubmitting}
              />
              {errors.oldPassword && (
                <p className="text-sm text-destructive">{errors.oldPassword.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="newPassword">{t('userProfile.newPassword')}</Label>
              <Input
                id="newPassword"
                type="password"
                placeholder={t('userProfile.newPasswordPlaceholder')}
                {...register('newPassword')}
                disabled={isSubmitting}
              />
              {errors.newPassword && (
                <p className="text-sm text-destructive">{errors.newPassword.message}</p>
              )}
              <p className="text-xs text-muted-foreground">
                {t('userProfile.passwordRequirements')}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword">{t('userProfile.confirmPassword')}</Label>
              <Input
                id="confirmPassword"
                type="password"
                placeholder={t('userProfile.confirmPasswordPlaceholder')}
                {...register('confirmPassword')}
                disabled={isSubmitting}
              />
              {errors.confirmPassword && (
                <p className="text-sm text-destructive">{errors.confirmPassword.message}</p>
              )}
            </div>

            <div className="flex justify-end space-x-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => reset()}
                disabled={isSubmitting}
              >
                {t('userProfile.reset')}
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {t('userProfile.saving')}
                  </>
                ) : (
                  t('userProfile.save')
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
