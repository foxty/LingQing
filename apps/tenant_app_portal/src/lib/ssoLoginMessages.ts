import type { TFunction } from 'i18next'

/** Map OIDC callback `reason` query values to i18n keys under login.ssoReasons. */
export function messageForSsoDeniedReason(reason: string, t: TFunction): string {
  const trimmed = reason.trim()
  if (!trimmed) {
    return t('login.ssoDenied')
  }
  const mapped = t(`login.ssoReasons.${trimmed}`, { defaultValue: '' })
  return mapped || t('login.ssoDenied')
}

const EXCHANGE_CODE_TO_REASON: Record<string, string> = {
  AUTH_TENANT_DEACTIVATED: 'membership_inactive',
  AUTH_USER_DISABLED: 'account_disabled',
  AUTH_USER_NOT_FOUND: 'user_not_found',
  AUTH_TENANT_NOT_FOUND: 'reject_unknown',
  SSO_INVALID_TICKET: '',
}

/** Map SSO ticket exchange API errors to user-facing login messages. */
export function messageForSsoExchangeError(err: unknown, t: TFunction): string {
  const data = (err as { response?: { data?: { code?: string; message?: string; detail?: string } } })
    ?.response?.data
  const code = data?.code
  if (code === 'SSO_INVALID_TICKET') {
    return t('login.ssoInvalidTicket')
  }
  const reasonKey = code ? EXCHANGE_CODE_TO_REASON[code] : undefined
  if (reasonKey) {
    return messageForSsoDeniedReason(reasonKey, t)
  }
  const detail = data?.message || data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    const asReason = t(`login.ssoReasons.${detail.trim()}`, { defaultValue: '' })
    if (asReason) {
      return asReason
    }
  }
  return t('login.ssoInvalidTicket')
}
