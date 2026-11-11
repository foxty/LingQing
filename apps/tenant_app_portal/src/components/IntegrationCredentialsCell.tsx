import { Badge } from '@/components/ui/badge'
import i18n from '@/i18n/config'
import { cn } from '@/lib/utils'
import { AlertCircle, Building2, CheckCircle2, CircleDashed, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    integrationCredentials: {
      columnTitle: 'Credentials',
      modeShared: 'Shared',
      modePerUser: 'Per-user',
      modePlatform: 'Platform',
      stateDisconnected: 'Disconnected',
      stateConnected: 'Connected',
      stateExpired: 'Expired',
      actionConnect: 'Connect',
      actionManage: 'Manage',
      actionReconnect: 'Reconnect',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    integrationCredentials: {
      columnTitle: '凭证',
      modeShared: '共享',
      modePerUser: '按用户',
      modePlatform: '平台',
      stateDisconnected: '未连接',
      stateConnected: '已连接',
      stateExpired: '已过期',
      actionConnect: '连接',
      actionManage: '管理',
      actionReconnect: '重新连接',
    },
  },
  true,
  true
)

export type UserConnectionStatus = 'not_connected' | 'connected' | 'expired'

export function connectionActionLabelKey(
  status: UserConnectionStatus | null | undefined
): 'actionConnect' | 'actionManage' | 'actionReconnect' {
  if (status === 'connected') {
    return 'actionManage'
  }
  if (status === 'expired') {
    return 'actionReconnect'
  }
  return 'actionConnect'
}

export function showPerUserConnectionAction(
  credentialMode: 'shared' | 'user' | undefined,
  managed?: boolean,
  connectorAuthType?: string | null
): boolean {
  if (managed) {
    return false
  }
  if ((credentialMode ?? 'shared') !== 'user') {
    return false
  }
  if (connectorAuthType === undefined) {
    return true
  }
  return connectorAuthType === 'api_key' || connectorAuthType === 'bearer' || connectorAuthType === 'basic'
}

function perUserStatusStyles(status: UserConnectionStatus) {
  if (status === 'connected') {
    return {
      badge:
        'border-success/35 bg-success/15 text-success [&_svg]:text-success',
      Icon: CheckCircle2,
    }
  }
  if (status === 'expired') {
    return {
      badge: 'border-destructive/45 bg-destructive/10 text-destructive [&_svg]:text-destructive',
      Icon: AlertCircle,
    }
  }
  return {
    badge: 'text-muted-foreground [&_svg]:text-muted-foreground',
    Icon: CircleDashed,
  }
}

interface Props {
  credentialMode?: 'shared' | 'user'
  userConnectionStatus?: UserConnectionStatus | null
  managed?: boolean
  className?: string
}

export default function IntegrationCredentialsCell({
  credentialMode = 'shared',
  userConnectionStatus = 'not_connected',
  managed = false,
  className,
}: Props) {
  const { t } = useTranslation()

  const status = userConnectionStatus ?? 'not_connected'

  if (credentialMode === 'user' && !managed) {
    const { badge, Icon } = perUserStatusStyles(status)
    const stateLabel =
      status === 'connected'
        ? t('integrationCredentials.stateConnected')
        : status === 'expired'
          ? t('integrationCredentials.stateExpired')
          : t('integrationCredentials.stateDisconnected')

    return (
      <div className={cn('flex min-h-[2rem] items-center', className)}>
        <Badge
          variant="outline"
          className={cn(
            'inline-flex max-w-full items-center gap-1 text-[10px] font-normal px-1.5 py-0.5',
            badge
          )}
        >
          <Icon className="h-3 w-3 shrink-0" aria-hidden />
          <span className="truncate">{t('integrationCredentials.modePerUser')}</span>
          <span className="opacity-60" aria-hidden>
            ·
          </span>
          <span className="truncate font-medium">{stateLabel}</span>
        </Badge>
      </div>
    )
  }

  const modeLabel = managed
    ? t('integrationCredentials.modePlatform')
    : t('integrationCredentials.modeShared')
  const ModeIcon = managed ? Building2 : Users

  return (
    <div className={cn('flex min-h-[2rem] items-center', className)}>
      <Badge
        variant="outline"
        className="inline-flex max-w-full items-center gap-1 text-[10px] font-normal px-1.5 py-0.5 text-muted-foreground [&_svg]:text-muted-foreground"
      >
        <ModeIcon className="h-3 w-3 shrink-0" aria-hidden />
        <span className="truncate">{modeLabel}</span>
      </Badge>
    </div>
  )
}

export function integrationConnectionActionLabel(
  t: (key: string) => string,
  status: UserConnectionStatus | null | undefined
): string {
  return t(`integrationCredentials.${connectionActionLabelKey(status)}`)
}
