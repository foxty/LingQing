import MyIntegrationConnectionPanel from '@/components/MyIntegrationConnectionPanel'
import TenantUserFilterCombobox from '@/components/TenantUserFilterCombobox'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useFormatUserDateTime } from '@/hooks/useUserDateTimeFormat'
import type { ApiConnector } from '@/lib/apiConnectorApi'
import { listApiConnectorUserConnections } from '@/lib/apiConnectorApi'
import type { DataSource } from '@/lib/dataSourceApi'
import { listDataSourceUserConnections } from '@/lib/dataSourceApi'
import {
  apiConnectorAuthTypeHint,
  apiConnectorSecretFields,
  dataSourceSecretFields,
  dataSourceUserAuthTypeHint,
} from '@/lib/integrationConnectionFields'
import type { UserIntegrationConnectionSummary } from '@/lib/userIntegrationConnection'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Settings2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    adminUserConnections: {
      title: 'User connections',
      description: 'Provision or update per-user credentials on behalf of tenant members.',
      user: 'User',
      status: 'Status',
      accountLabel: 'Account label',
      configuredBy: 'Configured by',
      configuredBySelf: 'Self',
      updated: 'Updated',
      actions: 'Actions',
      configure: 'Configure',
      addUser: 'Add',
      pickUser: 'Member',
      filterUser: 'Filter',
      filterUserSearch: 'Search users…',
      filterUserEmpty: 'No users found',
      clearFilter: 'Clear filter',
      empty: 'No user connections yet.',
      emptyFiltered: 'No connections match this filter.',
      dialogTitle: 'User connection',
      statusConnected: 'Connected',
      statusNotConnected: 'Not connected',
      statusExpired: 'Expired',
      unsupportedAuth:
        'This resource does not support admin-managed per-user credentials for its auth type.',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    adminUserConnections: {
      title: '用户连接',
      description: '代租户成员配置按用户凭证。',
      user: '用户',
      status: '状态',
      accountLabel: '账号备注',
      configuredBy: '配置人',
      configuredBySelf: '本人',
      updated: '更新时间',
      actions: '操作',
      configure: '配置',
      addUser: '添加',
      pickUser: '成员',
      filterUser: '筛选',
      filterUserSearch: '搜索用户…',
      filterUserEmpty: '未找到用户',
      clearFilter: '清除筛选',
      empty: '尚无用户连接。',
      emptyFiltered: '没有符合筛选的连接。',
      dialogTitle: '用户连接',
      statusConnected: '已连接',
      statusNotConnected: '未连接',
      statusExpired: '已过期',
      unsupportedAuth: '此资源的认证类型不支持管理员代配按用户凭证。',
    },
  },
  true,
  true
)

type ResourceKind = 'data_source' | 'api_connector'

interface DataSourceProps {
  kind: 'data_source'
  dataSource: DataSource
  apiConnector?: never
}

interface ApiConnectorProps {
  kind: 'api_connector'
  apiConnector: ApiConnector
  dataSource?: never
}

type Props = (DataSourceProps | ApiConnectorProps) & {
  /** When true, omit section title (parent tab already labels the surface). */
  embeddedInTab?: boolean
}

function statusLabel(status: UserIntegrationConnectionSummary['status'], t: (k: string) => string) {
  if (status === 'connected') return t('adminUserConnections.statusConnected')
  if (status === 'expired') return t('adminUserConnections.statusExpired')
  return t('adminUserConnections.statusNotConnected')
}

function configuredByLabel(
  row: UserIntegrationConnectionSummary,
  t: (k: string) => string
): string {
  if (row.provisioned_by_username) {
    return row.provisioned_by_username
  }
  if (row.provisioned_by_user_id != null) {
    return String(row.provisioned_by_user_id)
  }
  if (row.status !== 'not_connected') {
    return t('adminUserConnections.configuredBySelf')
  }
  return '—'
}

export default function AdminUserConnectionsSection(props: Props) {
  const { t } = useTranslation()
  const formatDateTime = useFormatUserDateTime()
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [selectedUsername, setSelectedUsername] = useState<string | undefined>()
  const [addUserId, setAddUserId] = useState<number | undefined>()
  const [addUserUsername, setAddUserUsername] = useState<string | undefined>()
  const [filterUserId, setFilterUserId] = useState<number | undefined>()

  const resourceKind: ResourceKind = props.kind
  const resourceId = props.kind === 'data_source' ? props.dataSource.id : props.apiConnector.id
  const resourceName =
    props.kind === 'data_source' ? props.dataSource.name : props.apiConnector.name

  const listQueryKey = ['admin-user-connections', resourceKind, resourceId]

  const { data: connections = [], isLoading: listLoading } = useQuery({
    queryKey: listQueryKey,
    queryFn: () =>
      resourceKind === 'data_source'
        ? listDataSourceUserConnections(resourceId)
        : listApiConnectorUserConnections(resourceId),
  })

  const filteredConnections = useMemo(() => {
    if (filterUserId == null) {
      return connections
    }
    return connections.filter((row) => row.user_id === filterUserId)
  }, [connections, filterUserId])

  const authTypeHint =
    props.kind === 'data_source'
      ? dataSourceUserAuthTypeHint(props.dataSource.type)
      : apiConnectorAuthTypeHint(props.apiConnector.auth_type)

  const secretFields =
    props.kind === 'data_source'
      ? dataSourceSecretFields(props.dataSource.type)
      : apiConnectorSecretFields(props.apiConnector.auth_type)

  const openForUser = (userId: number, username?: string) => {
    setSelectedUserId(userId)
    setSelectedUsername(username)
    setDialogOpen(true)
  }

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: listQueryKey })
  }

  const dialogUsername =
    selectedUsername ??
    connections.find((c) => c.user_id === selectedUserId)?.username ??
    (selectedUserId != null ? String(selectedUserId) : undefined)

  const userComboboxLabels = {
    placeholder: t('adminUserConnections.pickUser'),
    searchPlaceholder: t('adminUserConnections.filterUserSearch'),
    emptyMessage: t('adminUserConnections.filterUserEmpty'),
    clearLabel: t('adminUserConnections.clearFilter'),
  }

  const filterComboboxLabels = {
    placeholder: t('adminUserConnections.filterUser'),
    searchPlaceholder: t('adminUserConnections.filterUserSearch'),
    emptyMessage: t('adminUserConnections.filterUserEmpty'),
    clearLabel: t('adminUserConnections.clearFilter'),
  }

  const embeddedInTab = props.embeddedInTab ?? false

  return (
    <section className="space-y-3">
      {!embeddedInTab ? (
        <div>
          <h2 className="text-sm font-semibold">{t('adminUserConnections.title')}</h2>
          <p className="text-xs text-muted-foreground mt-1">
            {t('adminUserConnections.description')}
          </p>
        </div>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 text-xs text-muted-foreground w-10 sm:w-auto">
            {t('adminUserConnections.filterUser')}
          </span>
          <TenantUserFilterCombobox
            className="min-w-0 flex-1 sm:w-52"
            value={filterUserId}
            onChange={(id) => setFilterUserId(id)}
            labels={filterComboboxLabels}
          />
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">
          <span className="shrink-0 text-xs text-muted-foreground">
            {t('adminUserConnections.pickUser')}
          </span>
          <TenantUserFilterCombobox
            className="min-w-0 flex-1 sm:w-52"
            value={addUserId}
            onChange={(id, username) => {
              setAddUserId(id)
              setAddUserUsername(username)
            }}
            labels={userComboboxLabels}
          />
          <Button
            type="button"
            size="sm"
            disabled={addUserId == null}
            onClick={() => {
              if (addUserId != null) {
                openForUser(addUserId, addUserUsername)
              }
            }}
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            {t('adminUserConnections.addUser')}
          </Button>
        </div>
      </div>

      {listLoading ? (
        <p className="text-xs text-muted-foreground">…</p>
      ) : filteredConnections.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {filterUserId != null
            ? t('adminUserConnections.emptyFiltered')
            : t('adminUserConnections.empty')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('adminUserConnections.user')}</TableHead>
                <TableHead>{t('adminUserConnections.status')}</TableHead>
                <TableHead>{t('adminUserConnections.accountLabel')}</TableHead>
                <TableHead>{t('adminUserConnections.configuredBy')}</TableHead>
                <TableHead>{t('adminUserConnections.updated')}</TableHead>
                <TableHead className="w-[100px]">{t('adminUserConnections.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredConnections.map((row) => (
                <TableRow key={row.user_id}>
                  <TableCell className="font-medium">{row.username ?? row.user_id}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        row.status === 'connected'
                          ? 'default'
                          : row.status === 'expired'
                            ? 'destructive'
                            : 'secondary'
                      }
                    >
                      {statusLabel(row.status, t)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {row.account_label ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {configuredByLabel(row, t)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {row.updated_at ? formatDateTime(row.updated_at) : '—'}
                  </TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => openForUser(row.user_id, row.username ?? undefined)}
                    >
                      <Settings2 className="h-3.5 w-3.5 mr-1" />
                      {t('adminUserConnections.configure')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('adminUserConnections.dialogTitle')}</DialogTitle>
            <DialogDescription>
              {resourceName}
              {dialogUsername ? ` · ${dialogUsername}` : ''}
            </DialogDescription>
          </DialogHeader>
          {selectedUserId != null &&
          authTypeHint &&
          (secretFields.length > 0 || authTypeHint === 'oauth2') ? (
            <MyIntegrationConnectionPanel
              key={`${resourceKind}-${resourceId}-${selectedUserId}`}
              resourceKind={resourceKind}
              resourceId={resourceId}
              credentialMode="user"
              authTypeHint={authTypeHint}
              secretFields={secretFields}
              targetUserId={selectedUserId}
              compact
              onConnectionChanged={invalidate}
              onSaved={() => {
                invalidate()
                setDialogOpen(false)
              }}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              {t('adminUserConnections.unsupportedAuth')}
            </p>
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
