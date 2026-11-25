import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNotification } from '@/hooks/useNotification'
import { useApiConnectorPacks } from '@/hooks/useApiConnectorPacks'
import type { ApiConnector } from '@/lib/apiConnectorApi'
import { getDefaultIntegrationOAuthRedirectUri } from '@/lib/integrationOAuth'
import { getApiErrorMessage } from '@/lib/api'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    connectorPackDialog: {
      title: 'Install connector pack',
      description: 'Create a curated OAuth API connector from a platform template.',
      pack: 'Connector pack',
      clientId: 'OAuth client ID',
      clientSecret: 'OAuth client secret',
      redirectUri: 'OAuth redirect URI',
      redirectUriHelp:
        "Pre-filled with this deployment's API callback. Register the same URL in your OAuth app; change only if needed.",
      install: 'Install',
      installed: 'Connector pack installed',
      noPacks: 'No connector packs are available.',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    connectorPackDialog: {
      title: '安装连接器模板',
      description: '使用平台模板创建精选的 OAuth API 连接器。',
      pack: '连接器模板',
      clientId: 'OAuth 客户端 ID',
      clientSecret: 'OAuth 客户端密钥',
      redirectUri: 'OAuth 回调地址',
      redirectUriHelp: '已预填当前环境的 API 回调地址。请在 OAuth 应用中注册相同 URL；一般无需修改。',
      install: '安装',
      installed: '连接器模板已安装',
      noPacks: '当前没有可用的连接器模板。',
    },
  },
  true,
  true
)

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onInstalled: (connector: ApiConnector) => void
}

export default function InstallApiConnectorPackDialog({ open, onOpenChange, onInstalled }: Props) {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()
  const [packId, setPackId] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [redirectUri, setRedirectUri] = useState(() => getDefaultIntegrationOAuthRedirectUri())
  const { packs, packsLoading, installPack, installing } = useApiConnectorPacks(open)

  useEffect(() => {
    if (!open) return
    setRedirectUri(getDefaultIntegrationOAuthRedirectUri())
    setClientId('')
    setClientSecret('')
  }, [open])

  useEffect(() => {
    if (!packId && packs.length) {
      setPackId(packs[0].pack_id)
    }
  }, [packId, packs])

  const handleInstall = async () => {
    try {
      const connector = await installPack({
        pack_id: packId,
        client_id: clientId.trim(),
        client_secret: clientSecret,
        redirect_uri: redirectUri.trim() || getDefaultIntegrationOAuthRedirectUri(),
      })
      showSuccess(t('connectorPackDialog.installed'))
      onInstalled(connector)
      onOpenChange(false)
    } catch (error: unknown) {
      showError(getApiErrorMessage(error, t('common.error')))
    }
  }

  const canInstall = Boolean(packId && clientId.trim() && clientSecret)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('connectorPackDialog.title')}</DialogTitle>
          <DialogDescription>{t('connectorPackDialog.description')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>{t('connectorPackDialog.pack')}</Label>
            <Select value={packId} onValueChange={setPackId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {packs.map((pack) => (
                  <SelectItem key={pack.pack_id} value={pack.pack_id}>
                    {pack.name} · v{pack.version}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!packsLoading && packs.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('connectorPackDialog.noPacks')}</p>
            ) : null}
          </div>
          <div className="space-y-1">
            <Label htmlFor="pack-client-id">{t('connectorPackDialog.clientId')}</Label>
            <Input
              id="pack-client-id"
              value={clientId}
              onChange={(event) => setClientId(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="pack-client-secret">{t('connectorPackDialog.clientSecret')}</Label>
            <Input
              id="pack-client-secret"
              type="password"
              value={clientSecret}
              onChange={(event) => setClientSecret(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="pack-redirect-uri">{t('connectorPackDialog.redirectUri')}</Label>
            <Input
              id="pack-redirect-uri"
              value={redirectUri}
              onChange={(event) => setRedirectUri(event.target.value)}
              placeholder={getDefaultIntegrationOAuthRedirectUri()}
            />
            <p className="text-xs text-muted-foreground">
              {t('connectorPackDialog.redirectUriHelp')}
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button
            type="button"
            onClick={() => void handleInstall()}
            disabled={!canInstall || installing}
          >
            {t('connectorPackDialog.install')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
