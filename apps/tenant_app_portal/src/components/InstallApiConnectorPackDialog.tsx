import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
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
import { isPackInstalledForTenant } from '@/lib/packConnectorUtils'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    connectorPackDialog: {
      title: 'Install connector pack',
      titleUpdate: 'Apply connector pack update',
      description: 'Create a curated OAuth API connector from a platform template.',
      descriptionUpdate:
        'Apply the latest pack template to your existing connector. OAuth client ID and secret are not changed.',
      pack: 'Connector pack',
      clientId: 'OAuth client ID',
      clientSecret: 'OAuth client secret',
      redirectUri: 'OAuth redirect URI',
      redirectUriHelp:
        "Pre-filled with this deployment's API callback. Register the same URL in your OAuth app; change only if needed.",
      install: 'Install',
      applyUpdate: 'Apply pack update',
      installing: 'Installing…',
      applying: 'Applying update…',
      installed: 'Connector pack installed',
      updated: 'Connector pack updated',
      updateReconnect: 'OAuth scopes changed — ask users to reconnect.',
      noPacks: 'No connector packs are available.',
      updateConfirmTitle: 'Apply pack update?',
      updateConfirmDesc:
        'Apply catalog version v{{version}} to the installed connector for this pack. Operations and agent instructions will be updated.',
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
      titleUpdate: '应用连接器模板更新',
      description: '使用平台模板创建精选的 OAuth API 连接器。',
      descriptionUpdate:
        '将最新模板应用到已安装的连接器。不会更改 OAuth 客户端 ID 与密钥。',
      pack: '连接器模板',
      clientId: 'OAuth 客户端 ID',
      clientSecret: 'OAuth 客户端密钥',
      redirectUri: 'OAuth 回调地址',
      redirectUriHelp: '已预填当前环境的 API 回调地址。请在 OAuth 应用中注册相同 URL；一般无需修改。',
      install: '安装',
      applyUpdate: '应用模板更新',
      installing: '正在安装…',
      applying: '正在应用更新…',
      installed: '连接器模板已安装',
      updated: '连接器模板已更新',
      updateReconnect: 'OAuth 权限范围已变更 — 请用户重新连接。',
      noPacks: '当前没有可用的连接器模板。',
      updateConfirmTitle: '确认应用模板更新？',
      updateConfirmDesc: '将目录版本 v{{version}} 应用到该模板已安装的连接器，并更新操作与 Agent 指引。',
    },
  },
  true,
  true
)

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onInstalled: (connector: ApiConnector) => void
  connectors: ApiConnector[]
}

export default function InstallApiConnectorPackDialog({
  open,
  onOpenChange,
  onInstalled,
  connectors,
}: Props) {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()
  const [packId, setPackId] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [redirectUri, setRedirectUri] = useState(() => getDefaultIntegrationOAuthRedirectUri())
  const [showUpdateConfirm, setShowUpdateConfirm] = useState(false)
  const { packs, packsLoading, installPack, installing } = useApiConnectorPacks(open)

  const selectedPack = useMemo(
    () => packs.find((pack) => pack.pack_id === packId),
    [packId, packs]
  )
  const packUpdateMode = Boolean(packId && isPackInstalledForTenant(connectors, packId))

  useEffect(() => {
    if (!open) return
    setRedirectUri(getDefaultIntegrationOAuthRedirectUri())
    setClientId('')
    setClientSecret('')
    setShowUpdateConfirm(false)
  }, [open])

  useEffect(() => {
    if (!packId && packs.length) {
      setPackId(packs[0].pack_id)
    }
  }, [packId, packs])

  const runInstallOrUpdate = async () => {
    try {
      const payload = packUpdateMode
        ? { pack_id: packId }
        : {
            pack_id: packId,
            client_id: clientId.trim(),
            client_secret: clientSecret,
            redirect_uri: redirectUri.trim() || getDefaultIntegrationOAuthRedirectUri(),
          }
      const result = await installPack(payload)
      showSuccess(t(packUpdateMode ? 'connectorPackDialog.updated' : 'connectorPackDialog.installed'))
      if (result.sync_summary?.scopes_expanded) {
        showSuccess(t('connectorPackDialog.updateReconnect'))
      }
      onInstalled(result.connector)
      onOpenChange(false)
    } catch (error: unknown) {
      showError(getApiErrorMessage(error, t('common.error')))
    } finally {
      setShowUpdateConfirm(false)
    }
  }

  const handlePrimaryClick = () => {
    if (packUpdateMode) {
      setShowUpdateConfirm(true)
      return
    }
    void runInstallOrUpdate()
  }

  const canSubmit = Boolean(
    packId && (packUpdateMode || (clientId.trim() && clientSecret))
  )

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {t(packUpdateMode ? 'connectorPackDialog.titleUpdate' : 'connectorPackDialog.title')}
            </DialogTitle>
            <DialogDescription>
              {t(
                packUpdateMode
                  ? 'connectorPackDialog.descriptionUpdate'
                  : 'connectorPackDialog.description'
              )}
            </DialogDescription>
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
            {packUpdateMode ? null : (
              <>
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
              </>
            )}
          </div>
          <DialogFooter>
            <Button
              type="button"
              onClick={handlePrimaryClick}
              disabled={!canSubmit || installing}
            >
              {installing
                ? t(packUpdateMode ? 'connectorPackDialog.applying' : 'connectorPackDialog.installing')
                : t(packUpdateMode ? 'connectorPackDialog.applyUpdate' : 'connectorPackDialog.install')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={showUpdateConfirm} onOpenChange={setShowUpdateConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('connectorPackDialog.updateConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('connectorPackDialog.updateConfirmDesc', {
                version: selectedPack?.version ?? '—',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={installing}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              disabled={installing}
              onClick={(event) => {
                event.preventDefault()
                void runInstallOrUpdate()
              }}
            >
              {installing
                ? t('connectorPackDialog.applying')
                : t('connectorPackDialog.applyUpdate')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}