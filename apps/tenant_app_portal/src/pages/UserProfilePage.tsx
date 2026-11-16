import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { useUserProfile, usePreferredTimezone } from '@/hooks/useUserProfile'
import { formatInstant } from '@/lib/dateTime'
import { DATETIME_FORMAT_IDS, resolveDateTimeFormat, type DateTimeFormatId } from '@/lib/datetimeFormats'
import TimezonePicker from '@/components/TimezonePicker'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { AlertCircle, Loader2, User as UserIcon } from 'lucide-react'

i18n.addResourceBundle('en', 'translation', {
  userProfile: {
    title: 'User Profile',
    description: 'Manage your account settings and preferences',
    tabOverview: 'Overview',
    tabPreferences: 'Preferences',
    tabSecurity: 'Security',
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
    dateTimeTitle: 'Date & time',
    dateTimeDesc: 'Timezone and how timestamps appear across the app',
    timezone: 'Timezone',
    dateTimeFormat: 'Date & time format',
    dateTimeFormatLocale: 'Match UI language (default)',
    dateTimeFormatYmdHms24: '2026-03-16 14:32:45 (24-hour)',
    dateTimeFormatYmdHms12: '2026-03-16 2:32:45 PM',
    dateTimeFormatYmd: '2026-03-16 (date only)',
    dateTimeFormatMdyHm12: '03/16/2026 2:32 PM',
    dateTimePreview: 'Preview: {{sample}}',
    currentDateTimePrefs: 'Saved — timezone: {{tz}} · format: {{fmt}}',
    saveDateTime: 'Save date & time',
    dateTimeUpdateFailed: 'Failed to update date & time settings',
    dateTimeFormatInvalid: 'Invalid date & time format',
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
    loadFailed: 'Failed to load profile',
    passwordChangeFailed: 'Failed to change password',
    timezoneSelectPlaceholder: 'Select timezone',
    timezoneSearchPlaceholder: 'Search all IANA timezones…',
    timezoneSearchHint: 'Type to search the full list (400+ zones). Quick picks shown when empty.',
    timezoneNoResults: 'No matching timezones',
    timezoneInvalid: 'Invalid timezone identifier',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  userProfile: {
    title: '用户信息',
    description: '管理您的账户设置和偏好',
    tabOverview: '概览',
    tabPreferences: '偏好设置',
    tabSecurity: '安全',
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
    dateTimeTitle: '日期与时间',
    dateTimeDesc: '时区及时间戳在应用中的显示方式',
    timezone: '时区',
    dateTimeFormat: '日期时间格式',
    dateTimeFormatLocale: '跟随界面语言（默认）',
    dateTimeFormatYmdHms24: '2026-03-16 14:32:45（24 小时）',
    dateTimeFormatYmdHms12: '2026-03-16 下午2:32:45',
    dateTimeFormatYmd: '2026-03-16（仅日期）',
    dateTimeFormatMdyHm12: '03/16/2026 2:32 PM',
    dateTimePreview: '预览：{{sample}}',
    currentDateTimePrefs: '已保存 — 时区：{{tz}} · 格式：{{fmt}}',
    saveDateTime: '保存日期与时间',
    dateTimeUpdateFailed: '更新日期与时间设置失败',
    dateTimeFormatInvalid: '无效的日期时间格式',
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
    loadFailed: '加载用户信息失败',
    passwordChangeFailed: '修改密码失败',
    timezoneSelectPlaceholder: '选择时区',
    timezoneSearchPlaceholder: '搜索全部 IANA 时区…',
    timezoneSearchHint: '输入关键字搜索完整列表（400+）。未搜索时显示常用时区。',
    timezoneNoResults: '没有匹配的时区',
    timezoneInvalid: '无效的时区标识',
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

const DATE_TIME_FORMAT_I18N: Record<DateTimeFormatId, string> = {
  locale: 'userProfile.dateTimeFormatLocale',
  ymd_hms_24: 'userProfile.dateTimeFormatYmdHms24',
  ymd_hms_12: 'userProfile.dateTimeFormatYmdHms12',
  ymd: 'userProfile.dateTimeFormatYmd',
  mdy_hm_12: 'userProfile.dateTimeFormatMdyHm12',
}

export default function UserProfilePage() {
  const { t, i18n } = useTranslation()
  const { profile, loading, error, handleChangePassword, handleUpdateDateTimePreferences } =
    useUserProfile()
  const preferredTimeZone = usePreferredTimezone()
  const [tagKeys, setTagKeys] = useState<TagKeyDTO[]>([])
  const [userTags, setUserTags] = useState<TagValueDTO[]>([])
  const [timezoneIana, setTimezoneIana] = useState('')
  const [datetimeFormat, setDatetimeFormat] = useState<DateTimeFormatId>('locale')
  const displayFormatOpts = useMemo(
    () => ({
      locale: i18n.language,
      timeZone: preferredTimeZone,
      formatId: resolveDateTimeFormat(profile?.preferences?.datetime_format),
    }),
    [i18n.language, preferredTimeZone, profile?.preferences?.datetime_format]
  )

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
      setDatetimeFormat(resolveDateTimeFormat(profile.preferences?.datetime_format))
    }
  }, [profile])

  const dateTimePreview = useMemo(
    () =>
      formatInstant(new Date(), {
        locale: i18n.language,
        timeZone: timezoneIana || preferredTimeZone,
        formatId: datetimeFormat,
      }),
    [datetimeFormat, i18n.language, preferredTimeZone, timezoneIana]
  )

  const onSubmit = async (data: PasswordFormData) => {
    try {
      await handleChangePassword(data)
      reset()
    } catch {
      // Error already handled in hook
    }
  }

  const onDateTimeSubmit = async () => {
    const normalized = timezoneIana.trim()
    if (!normalized) return
    try {
      await handleUpdateDateTimePreferences({
        timezone_iana: normalized,
        datetime_format: datetimeFormat,
      })
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

      {error && !profile ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList className="h-auto w-full flex-wrap justify-start gap-1 p-1 md:w-auto">
          <TabsTrigger value="overview">{t('userProfile.tabOverview')}</TabsTrigger>
          <TabsTrigger value="preferences">{t('userProfile.tabPreferences')}</TabsTrigger>
          <TabsTrigger value="security">{t('userProfile.tabSecurity')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-0">
          <Card>
            <CardHeader>
              <CardTitle>{t('userProfile.userInfo')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {profile ? (
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
                    <p className="break-all md:col-span-2">
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
                      <span className="font-medium tabular-nums">
                        {formatInstant(profile.last_login_at, {
                          ...displayFormatOpts,
                          fallback: t('userProfile.neverLoggedIn'),
                        })}
                      </span>
                    </p>
                    <p>
                      <span className="text-muted-foreground">{t('userProfile.registrationTime')}: </span>
                      <span className="font-medium tabular-nums">
                        {formatInstant(profile.created_at, displayFormatOpts)}
                      </span>
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
              ) : null}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="preferences" className="mt-0">
          <Card>
            <CardHeader>
              <CardTitle>{t('userProfile.dateTimeTitle')}</CardTitle>
              <CardDescription>{t('userProfile.dateTimeDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {error ? (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}
              <div className="grid grid-cols-1 gap-6 md:grid-cols-2 md:items-start">
                <div className="min-w-0 space-y-2">
                  <Label htmlFor="user-timezone-picker">Timezone (IANA)</Label>
                  <TimezonePicker
                    id="user-timezone-picker"
                    value={timezoneIana}
                    onChange={setTimezoneIana}
                    disabled={loading}
                  />
                </div>
                <div className="min-w-0 space-y-2">
                  <Label htmlFor="user-datetime-format">{t('userProfile.dateTimeFormat')}</Label>
                  <Select
                    value={datetimeFormat}
                    onValueChange={(value) => setDatetimeFormat(value as DateTimeFormatId)}
                    disabled={loading}
                  >
                    <SelectTrigger id="user-datetime-format">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {DATETIME_FORMAT_IDS.map((id) => (
                        <SelectItem key={id} value={id}>
                          {t(DATE_TIME_FORMAT_I18N[id])}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="rounded-md border border-border/80 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                <p className="font-medium text-foreground">
                  {t('userProfile.dateTimePreview', { sample: dateTimePreview })}
                </p>
                <p className="mt-1">
                  {t('userProfile.currentDateTimePrefs', {
                    tz: profile?.preferences?.timezone_iana || t('userProfile.notSet'),
                    fmt: t(
                      DATE_TIME_FORMAT_I18N[
                        resolveDateTimeFormat(profile?.preferences?.datetime_format)
                      ]
                    ),
                  })}
                </p>
              </div>
              <div className="flex justify-end border-t border-border/70 pt-4">
                <Button onClick={onDateTimeSubmit} disabled={loading || !timezoneIana.trim()}>
                  {t('userProfile.saveDateTime')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security" className="mt-0">
          <Card>
            <CardHeader>
              <CardTitle>{t('userProfile.changePassword')}</CardTitle>
              <CardDescription>{t('userProfile.changePasswordDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit(onSubmit)} className="mx-auto max-w-md space-y-4">
                {error ? (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : null}

                <div className="space-y-2">
                  <Label htmlFor="oldPassword">{t('userProfile.currentPassword')}</Label>
                  <Input
                    id="oldPassword"
                    type="password"
                    placeholder={t('userProfile.currentPasswordPlaceholder')}
                    {...register('oldPassword')}
                    disabled={isSubmitting}
                  />
                  {errors.oldPassword ? (
                    <p className="text-sm text-destructive">{errors.oldPassword.message}</p>
                  ) : null}
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
                  {errors.newPassword ? (
                    <p className="text-sm text-destructive">{errors.newPassword.message}</p>
                  ) : null}
                  <p className="text-xs text-muted-foreground">{t('userProfile.passwordRequirements')}</p>
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
                  {errors.confirmPassword ? (
                    <p className="text-sm text-destructive">{errors.confirmPassword.message}</p>
                  ) : null}
                </div>

                <div className="flex justify-end gap-2 border-t border-border/70 pt-4">
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
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
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
        </TabsContent>
      </Tabs>
    </div>
  )
}
