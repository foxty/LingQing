import MyIntegrationConnectionPanel from '@/components/MyIntegrationConnectionPanel'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { ApiConnector } from '@/lib/apiConnectorApi'
import type { DataSource } from '@/lib/dataSourceApi'
import {
  apiConnectorAuthTypeHint,
  apiConnectorSecretFields,
  dataSourceSecretFields,
  dataSourceUserAuthTypeHint,
} from '@/lib/integrationConnectionFields'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    myIntegrationConnectionDialog: {
      titleDataSource: 'Connect your login',
      titleApiConnector: 'Connect your API credentials',
      descriptionDataSource:
        'Enter the credentials you use to query this warehouse. We test the connection before saving.',
      descriptionApiConnector:
        'Enter the credentials you use to call this API. We test the connection before saving.',
      connectorAuthUnsupported:
        'This connector does not support per-user credentials. Ask an admin to use api_key, bearer, or basic auth.',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    myIntegrationConnectionDialog: {
      titleDataSource: '连接您的登录',
      titleApiConnector: '连接 API 凭证',
      descriptionDataSource: '填写用于查询此数据仓库的凭证。保存前会先测试连接。',
      descriptionApiConnector: '填写用于调用此 API 的凭证。保存前会先测试连接。',
      connectorAuthUnsupported: '此连接器不支持按用户凭证。请联系管理员改用 api_key、bearer 或 basic 认证。',
    },
  },
  true,
  true
)

interface DataSourceProps {
  kind: 'data_source'
  dataSource: DataSource | null
  apiConnector?: never
}

interface ApiConnectorProps {
  kind: 'api_connector'
  apiConnector: ApiConnector | null
  dataSource?: never
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConnectionChanged?: () => void
} & (DataSourceProps | ApiConnectorProps)

export default function MyIntegrationConnectionDialog({
  open,
  onOpenChange,
  onConnectionChanged,
  ...rest
}: Props) {
  const { t } = useTranslation()

  if (rest.kind === 'data_source') {
    const { dataSource } = rest
    if (!dataSource) return null
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('myIntegrationConnectionDialog.titleDataSource')}</DialogTitle>
            <DialogDescription>
              {dataSource.name} — {t('myIntegrationConnectionDialog.descriptionDataSource')}
            </DialogDescription>
          </DialogHeader>
          <MyIntegrationConnectionPanel
            key={dataSource.id}
            resourceKind="data_source"
            resourceId={dataSource.id}
            credentialMode="user"
            authTypeHint={dataSourceUserAuthTypeHint(dataSource.type)}
            secretFields={dataSourceSecretFields(dataSource.type)}
            compact
            onConnectionChanged={onConnectionChanged}
            onSaved={() => onOpenChange(false)}
          />
        </DialogContent>
      </Dialog>
    )
  }

  const { apiConnector } = rest
  if (!apiConnector) return null
  const authTypeHint = apiConnectorAuthTypeHint(apiConnector.auth_type)
  const secretFields = apiConnectorSecretFields(apiConnector.auth_type)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('myIntegrationConnectionDialog.titleApiConnector')}</DialogTitle>
          <DialogDescription>
            {apiConnector.name} — {t('myIntegrationConnectionDialog.descriptionApiConnector')}
          </DialogDescription>
        </DialogHeader>
        {authTypeHint && secretFields.length > 0 ? (
          <MyIntegrationConnectionPanel
            key={apiConnector.id}
            resourceKind="api_connector"
            resourceId={apiConnector.id}
            credentialMode="user"
            authTypeHint={authTypeHint}
            secretFields={secretFields}
            compact
            onConnectionChanged={onConnectionChanged}
            onSaved={() => onOpenChange(false)}
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            {t('myIntegrationConnectionDialog.connectorAuthUnsupported')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
