import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import i18n from '@/i18n/config'
import { useAuth } from '@/hooks/useAuth'
import { login as loginApi } from '@/lib/authApi'
import { resolveTenantMethods, ssoStart, type LoginMethod } from '@/lib/ssoApi'
import { SsoProviderIcon } from '@/components/sso/SsoProviderIcon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle, Loader2 } from 'lucide-react'
import { getApiErrorMessage } from '@/lib/api'
import { convertApiUserToUser } from '@/types'

i18n.addResourceBundle('en', 'translation', {
  login: {
    resolve: 'Work email or account',
    resolvePlaceholder: 'you@company.com',
    resolveButton: 'Continue',
    signInTo: 'Sign in to {{name}}',
    continueWith: 'Continue with {{provider}}',
    usePasswordInstead: 'Sign in with password instead',
    adminSignIn: 'Administrator sign-in',
    orDivider: 'or',
    back: 'Back',
    ssoPending: 'Your login is pending admin approval.',
    ssoDenied: 'Sign-in was denied. Please contact your administrator.',
    tenantNotFound:
      'We could not find an organization for this sign-in. Try your work email or account@tenant-slug.',
    identifierInvalid: 'Enter your work email (e.g. you@company.com) or account@tenant-slug.',
    ssoRequired: 'Password sign-in is disabled for this organization. Use SSO instead.',
    ssoDiscoveryFailed: 'Could not reach the sign-in provider. Contact your administrator.',
    rateLimitExceeded: 'Too many sign-in attempts. Please wait a few minutes and try again.',
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  login: {
    resolve: '工作邮箱或账号',
    resolvePlaceholder: 'you@company.com',
    resolveButton: '继续',
    signInTo: '登录到 {{name}}',
    continueWith: '使用 {{provider}} 继续',
    usePasswordInstead: '改用密码登录',
    adminSignIn: '管理员应急登录',
    orDivider: '或',
    back: '返回',
    ssoPending: '您的登录正在等待管理员审批。',
    ssoDenied: '登录被拒绝，请联系管理员。',
    tenantNotFound: '未能识别该登录信息。请使用工作邮箱或 账号@租户标识。',
    identifierInvalid: '请输入工作邮箱（例如 you@company.com）或 账号@租户标识。',
    ssoRequired: '该组织已禁用密码登录，请使用 SSO。',
    ssoDiscoveryFailed: '无法连接登录提供商，请联系管理员。',
    rateLimitExceeded: '登录尝试过于频繁，请稍后再试。',
  },
}, true, true)

type LoginStep = 'credentials' | 'signin'

export default function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { login, refreshPermissions } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [step, setStep] = useState<LoginStep>('credentials')
  const [tenantId, setTenantId] = useState<number | null>(null)
  const [tenantName, setTenantName] = useState<string>('')
  const [methods, setMethods] = useState<LoginMethod[]>([])
  const [resolvedUsername, setResolvedUsername] = useState<string>('')
  const [showPassword, setShowPassword] = useState(false)
  const [emergencyPasswordAvailable, setEmergencyPasswordAvailable] = useState(false)

  const resolveSchema = useCallback(
    () =>
      z.object({
        username: z
          .string()
          .min(1, t('login.usernameError'))
          .refine((val) => val.includes('@'), {
            message: t('login.usernameFormatError'),
          }),
      }),
    [t]
  )

  const loginSchema = useCallback(
    () =>
      z.object({
        password: z.string().min(1, t('login.passwordError')),
      }),
    [t]
  )

  type ResolveFormData = z.infer<ReturnType<typeof resolveSchema>>
  type LoginFormData = z.infer<ReturnType<typeof loginSchema>>

  const {
    register: registerResolve,
    handleSubmit: handleResolveSubmit,
    formState: { errors: resolveErrors },
  } = useForm<ResolveFormData>({
    resolver: zodResolver(resolveSchema()),
  })

  const {
    register: registerLogin,
    handleSubmit: handleLoginSubmit,
    formState: { errors: loginErrors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema()),
  })

  const mapResolveError = (err: any): string => {
    const data = err?.response?.data
    const code = data?.code
    if (err?.response?.status === 429 || code === 'RATE_LIMITED') {
      return getApiErrorMessage(err, t('login.rateLimitExceeded'))
    }
    if (code === 'AUTH_TENANT_NOT_FOUND') return t('login.tenantNotFound')
    if (code === 'AUTH_IDENTIFIER_INVALID') return t('login.identifierInvalid')
    return getApiErrorMessage(err, t('login.loginFailed'))
  }

  const mapLoginError = (err: any): string => {
    const data = err?.response?.data
    if (err?.response?.status === 429 || data?.code === 'RATE_LIMITED') {
      return getApiErrorMessage(err, t('login.rateLimitExceeded'))
    }
    if (data?.code === 'AUTH_SSO_REQUIRED') return t('login.ssoRequired')
    return getApiErrorMessage(err, t('login.loginFailed'))
  }

  const mapSsoError = (err: any): string => {
    const data = err?.response?.data
    const code = data?.code
    if (code === 'SSO_DISCOVERY_FAILED') return t('login.ssoDiscoveryFailed')
    return data?.message || data?.detail || t('login.loginFailed')
  }

  const providerLabel = (method: LoginMethod) => method.display_name || method.type

  const startSso = async (method: LoginMethod) => {
    if (!tenantId || !method.provider_id) {
      setError(t('login.loginFailed'))
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      const res = await ssoStart(tenantId, method.provider_id)
      window.location.href = res.authorize_url
    } catch (err: any) {
      setError(mapSsoError(err))
    } finally {
      setIsLoading(false)
    }
  }

  const onResolve = async (data: ResolveFormData) => {
    setError(null)
    setShowPassword(false)
    setIsLoading(true)
    try {
      const result = await resolveTenantMethods(data.username)
      setResolvedUsername(data.username)
      setTenantId(result.tenant_id)
      setTenantName(result.tenant_name)
      setMethods(result.login_methods)
      setEmergencyPasswordAvailable(result.emergency_password_available)

      const hasSso = result.login_methods.some((m) => m.type !== 'native')
      setShowPassword(!hasSso)
      setStep('signin')
    } catch (err: any) {
      setError(mapResolveError(err))
    } finally {
      setIsLoading(false)
    }
  }

  const onSubmit = async (data: LoginFormData) => {
    setError(null)
    setIsLoading(true)
    try {
      const response = await loginApi({ username: resolvedUsername, password: data.password })
      const { access_token, user: apiUser } = response
      const user = convertApiUserToUser(apiUser)
      login(user, access_token, [])
      await refreshPermissions()
      navigate('/', { replace: true })
    } catch (err: any) {
      setError(mapLoginError(err))
    } finally {
      setIsLoading(false)
    }
  }

  const backToCredentials = () => {
    setTenantId(null)
    setStep('credentials')
    setShowPassword(false)
    setError(null)
  }

  const nativeMethod = methods.find((m) => m.type === 'native')
  const ssoMethods = methods.filter((m) => m.type !== 'native')
  const canUsePassword = Boolean(nativeMethod) || emergencyPasswordAvailable

  const renderSsoButton = (method: LoginMethod) => (
    <Button
      key={method.provider_id}
      variant="default"
      className="w-full"
      onClick={() => startSso(method)}
      disabled={isLoading}
    >
      <SsoProviderIcon issuer={method.issuer} className="h-5 w-5 mr-2 shrink-0" />
      {t('login.continueWith', { provider: providerLabel(method) })}
    </Button>
  )

  const renderPasswordChoice = () => {
    if (showPassword || !canUsePassword) return null
    return (
      <div className="space-y-3">
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-card px-2 text-muted-foreground">{t('login.orDivider')}</span>
          </div>
        </div>
        {nativeMethod && (
          <Button
            variant="outline"
            className="w-full"
            onClick={() => setShowPassword(true)}
            disabled={isLoading}
          >
            {t('login.usePasswordInstead')}
          </Button>
        )}
        {!nativeMethod && emergencyPasswordAvailable && (
          <Button
            variant="outline"
            className="w-full"
            onClick={() => setShowPassword(true)}
            disabled={isLoading}
          >
            {t('login.adminSignIn')}
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-3xl font-semibold text-center">{t('login.title')}</CardTitle>
          <CardDescription className="text-center">
            {step === 'credentials'
              ? t('login.subtitle')
              : t('login.signInTo', { name: tenantName })}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {step === 'credentials' && (
            <form onSubmit={handleResolveSubmit(onResolve)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">{t('login.resolve')}</Label>
                <Input
                  id="username"
                  type="text"
                  placeholder={t('login.resolvePlaceholder')}
                  {...registerResolve('username')}
                  disabled={isLoading}
                />
                {resolveErrors.username && (
                  <p className="text-sm text-destructive">{resolveErrors.username.message}</p>
                )}
                <p className="text-xs text-muted-foreground">{t('login.usernameHelper')}</p>
              </div>
              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                {t('login.resolveButton')}
              </Button>
            </form>
          )}

          {step === 'signin' && (
            <div className="space-y-4">
              {ssoMethods.length > 0 && (
                <div className="space-y-2">{ssoMethods.map((m) => renderSsoButton(m))}</div>
              )}

              {renderPasswordChoice()}

              {showPassword && (
                <form onSubmit={handleLoginSubmit(onSubmit)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="password">{t('login.password')}</Label>
                    <Input
                      id="password"
                      type="password"
                      placeholder={t('login.passwordPlaceholder')}
                      {...registerLogin('password')}
                      disabled={isLoading}
                      autoFocus
                    />
                    {loginErrors.password && (
                      <p className="text-sm text-destructive">{loginErrors.password.message}</p>
                    )}
                  </div>
                  <Button type="submit" className="w-full" disabled={isLoading}>
                    {isLoading ? t('login.loggingIn') : t('login.loginButton')}
                  </Button>
                </form>
              )}

              <Button variant="ghost" className="w-full" onClick={backToCredentials} disabled={isLoading}>
                {t('login.back')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
