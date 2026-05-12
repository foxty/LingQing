import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useAuth } from '@/hooks/useAuth'
import { ssoExchange } from '@/lib/ssoApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle, Loader2 } from 'lucide-react'
import { convertApiUserToUser } from '@/types'

i18n.addResourceBundle('en', 'translation', {
  login: {
    ssoExchanging: 'Signing you in...',
    ssoPending: 'Your login is pending admin approval.',
    ssoDenied: 'Sign-in was denied. Please contact your administrator.',
    ssoInvalidTicket: 'Invalid or expired sign-in ticket. Please try again.',
    ssoReasons: {
      invalid_or_expired_state: 'Sign-in session expired. Please try again.',
      provider_mismatch: 'Sign-in provider mismatch. Please try again.',
      provider_disabled: 'This sign-in provider has been disabled. Contact your administrator.',
      domain_not_allowed: 'Your email domain is not allowed for this provider.',
      missing_email: 'The identity provider did not return an email address.',
      reject_unknown: 'Unknown user. Contact your administrator to provision your account.',
      membership_inactive: 'Your account has been deactivated in this tenant. Contact your administrator.',
      account_disabled: 'Your account has been disabled. Contact your administrator.',
      user_not_found: 'User account not found. Contact your administrator.',
      'id_token issuer mismatch': 'Identity provider issuer mismatch. Check the Issuer URL in Settings → SSO.',
      'id_token audience mismatch': 'Identity provider audience mismatch. Check the Client ID in Settings → SSO.',
      'id_token nonce mismatch': 'Sign-in nonce mismatch. Please try again.',
      'id_token expired': 'Sign-in token expired. Please try again.',
      'id_token missing sub': 'Identity provider returned no subject. Contact your administrator.',
      'Malformed id_token': 'Malformed sign-in token. Contact your administrator.',
      'OIDC token response missing id_token': 'Identity provider did not return an ID token.',
      'OIDC token exchange failed': 'Sign-in token exchange failed. Check the Client Secret in Settings → SSO.',
      'OIDC discovery failed': 'Could not reach the identity provider. Check the Issuer URL in Settings → SSO.',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  login: {
    ssoExchanging: '正在登录...',
    ssoPending: '您的登录正在等待管理员审批。',
    ssoDenied: '登录被拒绝，请联系管理员。',
    ssoInvalidTicket: '登录票据无效或已过期，请重试。',
    ssoReasons: {
      invalid_or_expired_state: '登录会话已过期，请重试。',
      provider_mismatch: '登录提供商不匹配，请重试。',
      provider_disabled: '此登录提供商已被禁用，请联系管理员。',
      domain_not_allowed: '您的邮箱域名不被此提供商允许。',
      missing_email: '身份提供商未返回邮箱地址。',
      reject_unknown: '未知用户，请联系管理员开通账号。',
      membership_inactive: '您的账号已在当前租户停用，请联系管理员。',
      account_disabled: '您的账号已被禁用，请联系管理员。',
      user_not_found: '未找到用户账号，请联系管理员。',
      'id_token issuer mismatch': '身份提供商 issuer 不匹配，请在“设置 → SSO”中检查 Issuer URL。',
      'id_token audience mismatch': '身份提供商 audience 不匹配，请在“设置 → SSO”中检查 Client ID。',
      'id_token nonce mismatch': '登录 nonce 不匹配，请重试。',
      'id_token expired': '登录令牌已过期，请重试。',
      'id_token missing sub': '身份提供商未返回 subject，请联系管理员。',
      'Malformed id_token': '登录令牌格式错误，请联系管理员。',
      'OIDC token response missing id_token': '身份提供商未返回 ID Token。',
      'OIDC token exchange failed': '登录令牌交换失败，请在“设置 → SSO”中检查 Client Secret。',
      'OIDC discovery failed': '无法访问身份提供商，请在“设置 → SSO”中检查 Issuer URL。',
    },
  },
}, true, true)

export default function SsoCallbackPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { login, refreshPermissions } = useAuth()
  const [status, setStatus] = useState<'loading' | 'pending' | 'denied' | 'error'>('loading')
  const [message, setMessage] = useState<string>('')

  useEffect(() => {
    const ticket = params.get('ticket')
    const statusParam = params.get('status')

    if (statusParam === 'pending') {
      setStatus('pending')
      setMessage(t('login.ssoPending'))
      return
    }
    if (statusParam === 'denied') {
      setStatus('denied')
      const reason = params.get('reason') || ''
      const mapped = reason ? t(`login.ssoReasons.${reason}`, { defaultValue: '' }) : ''
      setMessage(mapped || t('login.ssoDenied'))
      return
    }
    if (!ticket) {
      setStatus('error')
      setMessage(t('login.ssoInvalidTicket'))
      return
    }

    const exchange = async () => {
      try {
        const res = await ssoExchange(ticket)
        const user = convertApiUserToUser({
          id: res.user_id,
          username: res.username,
          role: res.role as any,
          tenant_id: res.tenant_id,
          tenant_name: res.tenant_name,
        })
        login(user, res.access_token, [])
        await refreshPermissions()
        navigate('/', { replace: true })
      } catch (e: any) {
        setStatus('error')
        setMessage(e?.response?.data?.detail || t('login.ssoInvalidTicket'))
      }
    }
    void exchange()
  }, [params])

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-center">{t('login.title')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4 py-8">
          {status === 'loading' && (
            <>
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              <p className="text-sm text-muted-foreground">{t('login.ssoExchanging')}</p>
            </>
          )}
          {(status === 'pending' || status === 'denied' || status === 'error') && (
            <Alert variant={status === 'pending' ? 'default' : 'destructive'}>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{message}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
