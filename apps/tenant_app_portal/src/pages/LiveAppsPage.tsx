import { Badge } from '@/components/ui/badge'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useLiveApps } from '@/hooks/useLiveApps'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import { getBackendUrl } from '@/lib/api'
import { formatDate } from '@/lib/dateTime'
import type { LiveApp } from '@/lib/liveAppsApi'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { AppWindow, Share2 } from 'lucide-react'
import { useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  liveApps: {
    description: 'Manage and monitor your live applications',
    noApps: 'No live apps found',
    noAppsHint: 'Deploy an app to see it here',
    nameCol: 'Name',
    ownerCol: 'Owner',
    statusCol: 'Status',
    envCol: 'Environment',
    updatedCol: 'Last Updated',
    actionsCol: 'Actions',
    share: 'Share',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  liveApps: {
    description: '管理和监控您的实时应用',
    noApps: '暂无应用',
    noAppsHint: '部署应用后即可在此查看',
    nameCol: '名称',
    ownerCol: '所有者',
    statusCol: '状态',
    envCol: '环境',
    updatedCol: '最后更新',
    actionsCol: '操作',
    share: '分享',
  }
}, true, true)

const ENVIRONMENTS = ['dev', 'test', 'prod'] as const
type LiveAppEnvironment = (typeof ENVIRONMENTS)[number]

function shortSha(sha: string | null): string {
  if (!sha) return ''
  return sha.length > 7 ? `${sha.slice(0, 7)}…` : sha
}

function openEntry(appId: number, env: LiveAppEnvironment) {
  const url = getBackendUrl(`/apps/${appId}/${env}/entry`)
  window.open(url, '_blank', 'noopener,noreferrer')
}

function EnvironmentBadges({ app }: { app: LiveApp }) {
  const state = app.deployment_state
  return (
    <div className="flex flex-wrap gap-1.5">
      {ENVIRONMENTS.map((env) => {
        const sha = state[env]
        const isDev = env === 'dev'
        const hasPointer = Boolean(sha)
        const openable = isDev || hasPointer
        const showActive = isDev || hasPointer
        const label = (
          <Badge
            variant={showActive ? 'secondary' : 'outline'}
            className={showActive ? 'font-mono text-xs hover:bg-accent' : 'text-muted-foreground'}
          >
            {env}
            {hasPointer && sha ? (
              <span className="ml-1 text-[10px] opacity-80">{shortSha(sha)}</span>
            ) : null}
          </Badge>
        )
        if (openable) {
          return (
            <button
              key={env}
              type="button"
              title={sha ?? (isDev ? 'Open dev preview' : undefined)}
              onClick={() => openEntry(app.app_id, env)}
              className="cursor-pointer"
            >
              {label}
            </button>
          )
        }
        return (
          <span key={env} title={`${env}: not deployed`} className="opacity-50">
            {label}
          </span>
        )
      })}
    </div>
  )
}

export default function LiveAppsPage() {
  const { t } = useTranslation()
  const { data: apps = [], isLoading } = useLiveApps()
  const [sharingApp, setSharingApp] = useState<LiveApp | null>(null)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold inline-flex items-center gap-2">
          <AppWindow className="w-6 h-6" />
          {t('sidebar.liveApps')}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">{t('liveApps.description')}</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
          {t('common.loading')}
        </div>
      ) : apps.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
          <AppWindow className="w-10 h-10 opacity-30" />
          <p className="text-sm">{t('liveApps.noApps')}</p>
          <p className="text-xs">{t('liveApps.noAppsHint')}</p>
        </div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{t('liveApps.nameCol')}</TableHead>
                <TableHead className="w-32">{t('liveApps.ownerCol')}</TableHead>
                <TableHead className="w-28">{t('liveApps.statusCol')}</TableHead>
                <TableHead>{t('liveApps.envCol')}</TableHead>
                <TableHead className="w-24">SDK</TableHead>
                <TableHead className="w-40">{t('liveApps.updatedCol')}</TableHead>
                <TableHead className="w-20 text-right">{t('liveApps.actionsCol')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {apps.map((app: LiveApp) => (
                <TableRow key={app.app_id}>
                  <TableCell className="font-medium">
                    <div className="flex flex-col gap-0.5">
                      <span>{app.name}</span>
                      {app.description ? (
                        <span className="text-xs text-muted-foreground font-normal line-clamp-1">
                          {app.description}
                        </span>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm">{app.owner_name || t('dataSources.deletedUser')}</span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{app.status}</Badge>
                  </TableCell>
                  <TableCell>
                    <EnvironmentBadges app={app} />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {app.sdk_version}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(app.updated_at, { precision: 'datetime' })}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      title={t('liveApps.share')}
                      onClick={() => setSharingApp(app)}
                    >
                      <Share2 className="w-3.5 h-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {sharingApp && (
        <ResourceAclShareDialog
          open={Boolean(sharingApp)}
          onOpenChange={(open) => {
            if (!open) {
              setSharingApp(null)
            }
          }}
          resourceType={ACL_SHARE_RESOURCE_TYPES.APP}
          resourceId={sharingApp.app_id}
          resourceTitle={sharingApp.name}
        />
      )}
    </div>
  )
}
