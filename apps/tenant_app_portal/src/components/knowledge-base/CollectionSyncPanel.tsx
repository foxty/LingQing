import i18n from '@/i18n/config'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { openFileSourcePicker } from '@/components/knowledge-base/file-source-picker/FileSourcePickerFacade'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  useCollectionSyncConnector,
  useCreateSyncConnector,
  useDeleteSyncConnector,
  useDisconnectSourceConnection,
  useSourceConnections,
  useGoogleDriveAuthorize,
  useTriggerSyncConnector,
} from '@/hooks/useDocumentSync'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { getApiErrorMessage } from '@/lib/api'
import { formatDate } from '@/lib/dateTime'
import {
  AlertCircle,
  Cloud,
  FolderSync,
  Link2,
  Loader2,
  MoreHorizontal,
  RefreshCw,
  Unlink,
} from 'lucide-react'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    collectionSync: {
      syncedFromDrive: 'Synced from Google Drive',
      setupHint: 'Connect Google Drive to keep this collection in sync with a folder.',
      chooseFolderHint: 'Choose a Drive folder to sync into this collection.',
      notConnected: 'Google Drive not connected',
      connectedAs: 'Connected as {{user}} · {{account}}',
      connectionOwner: '{{user}} · {{account}}',
      connect: 'Connect',
      bindFolder: 'Choose folder',
      syncNow: 'Sync now',
      manageSync: 'Manage sync',
      disconnectConnector: 'Remove folder sync',
      disconnectAccount: 'Disconnect account',
      confirmDisconnect: 'Remove folder sync?',
      confirmDisconnectDesc:
        'Documents already imported stay in this collection. Future Drive changes will no longer sync.',
      confirmDisconnectAccount: 'Disconnect Google account?',
      confirmDisconnectAccountDesc:
        'Folder syncs using this account will stop. Already imported documents stay in their collections.',
      lastSynced: 'Last synced {{time}}',
      neverSynced: 'Not synced yet',
      syncError: 'Sync failed: {{error}}',
      connectFailed: 'Failed to start Google Drive authorization',
      bindFailed: 'Failed to bind folder',
      bindSuccess: 'Folder bound for sync',
      pickerFailed: 'Failed to open Google Drive picker',
      disconnectConnectorSuccess: 'Folder sync removed',
      disconnectConnectorFailed: 'Failed to remove folder sync',
      disconnectSuccess: 'Google Drive disconnected',
      disconnectFailed: 'Failed to disconnect Google Drive',
      syncSuccess: 'Sync complete — added {{added}}, updated {{updated}}, removed {{deleted}}',
      syncFailed: 'Sync failed',
      statusStopped: 'Sync paused',
      confirmBindFolder: 'Sync folder into this collection?',
      confirmBindFolderDesc:
        'This collection already has {{count}} document(s). Drive sync will add and update files alongside existing uploads.',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    collectionSync: {
      syncedFromDrive: '已从 Google Drive 同步',
      setupHint: '连接 Google Drive，将此集合与文件夹保持同步。',
      chooseFolderHint: '选择要同步到此集合的 Drive 文件夹。',
      notConnected: '未连接 Google Drive',
      connectedAs: '已连接：{{user}} · {{account}}',
      connectionOwner: '{{user}} · {{account}}',
      connect: '连接',
      bindFolder: '选择文件夹',
      syncNow: '立即同步',
      manageSync: '管理同步',
      disconnectConnector: '移除文件夹同步',
      disconnectAccount: '断开账号',
      confirmDisconnect: '移除文件夹同步？',
      confirmDisconnectDesc: '已导入的文档会保留在此集合中，之后 Drive 的变更将不再同步。',
      confirmDisconnectAccount: '断开 Google 账号？',
      confirmDisconnectAccountDesc: '使用此账号的文件夹同步将停止。已导入的文档会保留在各自集合中。',
      lastSynced: '上次同步 {{time}}',
      neverSynced: '尚未同步',
      syncError: '同步失败：{{error}}',
      connectFailed: '启动 Google Drive 授权失败',
      bindFailed: '绑定文件夹失败',
      bindSuccess: '文件夹已绑定同步',
      pickerFailed: '打开 Google Drive 选择器失败',
      disconnectConnectorSuccess: '已移除文件夹同步',
      disconnectConnectorFailed: '移除文件夹同步失败',
      disconnectSuccess: '已断开 Google Drive',
      disconnectFailed: '断开 Google Drive 失败',
      syncSuccess: '同步完成 — 新增 {{added}}，更新 {{updated}}，删除 {{deleted}}',
      syncFailed: '同步失败',
      statusStopped: '同步已暂停',
      confirmBindFolder: '将文件夹同步到此集合？',
      confirmBindFolderDesc:
        '此集合已有 {{count}} 个文档。Drive 同步会与现有上传内容并存，并继续新增或更新文件。',
    },
  },
  true,
  true
)

interface CollectionSyncPanelProps {
  collectionId: number
  documentCount?: number
  canManageCollection?: boolean
}

function SyncStatusBar({
  children,
  actions,
}: {
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex items-center gap-2 rounded-md border bg-muted/25 px-3 py-2 text-sm">
      <Cloud className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1 truncate">{children}</div>
      {actions ? <div className="flex shrink-0 items-center gap-1">{actions}</div> : null}
    </div>
  )
}

function formatConnectionOwnerLabel(
  t: (key: string, options?: Record<string, string | number>) => string,
  username: string | null | undefined,
  accountEmail: string | null | undefined,
  fallbackUserId?: number
): string | null {
  const user = username ?? (fallbackUserId != null ? `#${fallbackUserId}` : null)
  if (user && accountEmail) {
    return t('collectionSync.connectionOwner', { user, account: accountEmail })
  }
  if (user) return user
  if (accountEmail) return accountEmail
  return null
}

export default function CollectionSyncPanel({
  collectionId,
  documentCount = 0,
  canManageCollection = false,
}: CollectionSyncPanelProps) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { showError } = useNotification()
  const { data: connector, isLoading: connectorLoading } = useCollectionSyncConnector(collectionId)
  const setupEnabled = canManageCollection && !connector
  const { data: connections = [], isLoading: connectionsLoading } = useSourceConnections(setupEnabled)
  const authorizeMutation = useGoogleDriveAuthorize()
  const createConnectorMutation = useCreateSyncConnector(collectionId)
  const deleteConnectorMutation = useDeleteSyncConnector(collectionId)
  const disconnectAccountMutation = useDisconnectSourceConnection()
  const syncMutation = useTriggerSyncConnector(collectionId)
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [disconnectAccountOpen, setDisconnectAccountOpen] = useState(false)
  const [bindFolderOpen, setBindFolderOpen] = useState(false)
  const [pickingFolder, setPickingFolder] = useState(false)

  const activeConnection = connections.find((c) => c.status === 'active')
  const isConnectionOwner = connector != null && user?.id === connector.connection_owner_id
  const canManageConnector = isConnectionOwner
  const connectorOwnerLabel = connector
    ? formatConnectionOwnerLabel(
        t,
        connector.connection_owner_username,
        connector.account_email,
        connector.connection_owner_id
      )
    : null
  const setupOwnerLabel = activeConnection
    ? formatConnectionOwnerLabel(t, user?.username, activeConnection.account_email, user?.id)
    : null

  const isBusy =
    connectorLoading ||
    (setupEnabled && connectionsLoading) ||
    authorizeMutation.isPending ||
    createConnectorMutation.isPending ||
    deleteConnectorMutation.isPending ||
    disconnectAccountMutation.isPending ||
    syncMutation.isPending ||
    pickingFolder

  const handleConnect = async () => {
    try {
      const { authorize_url } = await authorizeMutation.mutateAsync()
      window.location.href = authorize_url
    } catch {
      // handled in mutation
    }
  }

  const handleBindFolderClick = () => {
    if (documentCount > 0) {
      setBindFolderOpen(true)
      return
    }
    void handleBindFolder()
  }

  const handleBindFolder = async () => {
    if (!activeConnection) return
    setBindFolderOpen(false)
    setPickingFolder(true)
    try {
      const picked = await openFileSourcePicker('google_drive', activeConnection.id)
      if (!picked) {
        return
      }
      await createConnectorMutation.mutateAsync({
        source_connection_id: activeConnection.id,
        source_folder_id: picked.folderId,
        source_folder_name: picked.folderName,
        include_subfolders: true,
      })
    } catch (error: unknown) {
      showError(getApiErrorMessage(error, t('collectionSync.pickerFailed')))
    } finally {
      setPickingFolder(false)
    }
  }

  const handleSync = () => {
    if (!connector) return
    syncMutation.mutate(connector.id)
  }

  const handleDisconnectConnector = async () => {
    await deleteConnectorMutation.mutateAsync()
    setDisconnectOpen(false)
  }

  const handleDisconnectAccount = async () => {
    if (!activeConnection) return
    await disconnectAccountMutation.mutateAsync(activeConnection.id)
    setDisconnectAccountOpen(false)
  }

  if (connectorLoading) {
    return (
      <SyncStatusBar>
        <span className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {t('common.loading')}
        </span>
      </SyncStatusBar>
    )
  }

  if (connector) {
    const syncMeta = connector.last_sync_error
      ? t('collectionSync.syncError', { error: connector.last_sync_error })
      : connector.last_synced_at
        ? t('collectionSync.lastSynced', { time: formatDate(connector.last_synced_at) })
        : t('collectionSync.neverSynced')

    const tooltipLines = [
      t('collectionSync.syncedFromDrive'),
      connector.source_folder_name,
      connectorOwnerLabel,
      syncMeta,
    ].filter(Boolean)

    const manageMenu = canManageConnector ? (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-8 w-8" disabled={isBusy}>
            <MoreHorizontal className="h-4 w-4" />
            <span className="sr-only">{t('collectionSync.manageSync')}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onClick={handleSync}
            disabled={isBusy || connector.status !== 'active'}
          >
            {syncMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {t('collectionSync.syncNow')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setDisconnectOpen(true)} disabled={isBusy}>
            <Unlink className="mr-2 h-4 w-4" />
            {t('collectionSync.disconnectConnector')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    ) : null

    return (
      <>
        <TooltipProvider delayDuration={300}>
          <SyncStatusBar
            actions={canManageConnector ? manageMenu : null}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex min-w-0 items-center gap-2">
                  <span className="shrink-0 font-medium">{t('collectionSync.syncedFromDrive')}</span>
                  {connector.status !== 'active' ? (
                    <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[11px] font-normal">
                      {t('collectionSync.statusStopped')}
                    </Badge>
                  ) : null}
                  {connector.last_sync_error ? (
                    <AlertCircle className="h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
                  ) : null}
                  <span className="truncate text-muted-foreground">
                    · {connector.source_folder_name}
                    {connectorOwnerLabel ? (
                      <>
                        {' · '}
                        {connectorOwnerLabel}
                      </>
                    ) : null}
                    {' · '}
                    {connector.last_sync_error ? (
                      <span className="text-destructive">{connector.last_sync_error}</span>
                    ) : connector.last_synced_at ? (
                      t('collectionSync.lastSynced', { time: formatDate(connector.last_synced_at) })
                    ) : (
                      t('collectionSync.neverSynced')
                    )}
                  </span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-sm text-left">
                {tooltipLines.map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </TooltipContent>
            </Tooltip>
          </SyncStatusBar>
        </TooltipProvider>

        <ConfirmationDialog<boolean>
          open={disconnectOpen}
          item={disconnectOpen}
          isLoading={deleteConnectorMutation.isPending}
          title={t('collectionSync.confirmDisconnect')}
          description={() => t('collectionSync.confirmDisconnectDesc')}
          confirmText={t('collectionSync.disconnectConnector')}
          isDangerous
          onConfirm={handleDisconnectConnector}
          onCancel={() => setDisconnectOpen(false)}
        />
      </>
    )
  }

  if (!canManageCollection) {
    return null
  }

  if (setupEnabled && connectionsLoading) {
    return (
      <SyncStatusBar>
        <span className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {t('common.loading')}
        </span>
      </SyncStatusBar>
    )
  }

  const manageMenu = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8" disabled={isBusy}>
          <MoreHorizontal className="h-4 w-4" />
          <span className="sr-only">{t('collectionSync.manageSync')}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {activeConnection ? (
          <DropdownMenuItem onClick={() => setDisconnectAccountOpen(true)} disabled={isBusy}>
            <Unlink className="mr-2 h-4 w-4" />
            {t('collectionSync.disconnectAccount')}
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )

  if (!activeConnection) {
    return (
      <>
        <SyncStatusBar
          actions={
            <Button size="sm" variant="secondary" className="h-8" onClick={handleConnect} disabled={isBusy}>
              {authorizeMutation.isPending ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Link2 className="mr-1.5 h-3.5 w-3.5" />
              )}
              {t('collectionSync.connect')}
            </Button>
          }
        >
          <span className="text-muted-foreground">{t('collectionSync.setupHint')}</span>
        </SyncStatusBar>

        <ConfirmationDialog<boolean>
          open={disconnectAccountOpen}
          item={disconnectAccountOpen}
          isLoading={disconnectAccountMutation.isPending}
          title={t('collectionSync.confirmDisconnectAccount')}
          description={() => t('collectionSync.confirmDisconnectAccountDesc')}
          confirmText={t('collectionSync.disconnectAccount')}
          isDangerous
          onConfirm={handleDisconnectAccount}
          onCancel={() => setDisconnectAccountOpen(false)}
        />
      </>
    )
  }

  return (
    <>
      <SyncStatusBar
        actions={
          <>
            <Button size="sm" variant="secondary" className="h-8" onClick={handleBindFolderClick} disabled={isBusy}>
              {pickingFolder ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <FolderSync className="mr-1.5 h-3.5 w-3.5" />
              )}
              {t('collectionSync.bindFolder')}
            </Button>
            {manageMenu}
          </>
        }
      >
        <span className="text-muted-foreground">
          {t('collectionSync.chooseFolderHint')}{' '}
          <span className="text-foreground/80">
            ·{' '}
            {setupOwnerLabel ??
              t('collectionSync.connectedAs', {
                user: user?.username ?? `#${user?.id ?? '?'}`,
                account: activeConnection.account_email ?? `#${activeConnection.id}`,
              })}
          </span>
        </span>
      </SyncStatusBar>

      <ConfirmationDialog<boolean>
        open={disconnectAccountOpen}
        item={disconnectAccountOpen}
        isLoading={disconnectAccountMutation.isPending}
        title={t('collectionSync.confirmDisconnectAccount')}
        description={() => t('collectionSync.confirmDisconnectAccountDesc')}
        confirmText={t('collectionSync.disconnectAccount')}
        isDangerous
        onConfirm={handleDisconnectAccount}
        onCancel={() => setDisconnectAccountOpen(false)}
      />

      <ConfirmationDialog<boolean>
        open={bindFolderOpen}
        item={bindFolderOpen}
        isLoading={pickingFolder || createConnectorMutation.isPending}
        title={t('collectionSync.confirmBindFolder')}
        description={() => t('collectionSync.confirmBindFolderDesc', { count: documentCount })}
        confirmText={t('collectionSync.bindFolder')}
        onConfirm={() => {
          void handleBindFolder()
        }}
        onCancel={() => setBindFolderOpen(false)}
      />
    </>
  )
}
