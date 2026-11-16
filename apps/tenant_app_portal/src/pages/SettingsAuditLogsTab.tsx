import PaginationBar from '@/components/PaginationBar'
import SettingsListToolbar from '@/components/SettingsListToolbar'
import SettingsPageShell from '@/components/SettingsPageShell'
import SettingsSection from '@/components/SettingsSection'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/hooks/useAuth'
import { useFormatUserDateTime } from '@/hooks/useUserDateTimeFormat'
import { useNotification } from '@/hooks/useNotification'
import { exportAuditEvents, listAuditEvents, type AuditEventDTO } from '@/lib/auditApi'
import { getApiErrorMessage } from '@/lib/api'
import { PERMISSIONS } from '@/lib/permissionRules'
import i18n from '@/i18n/config'
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

const PAGE_SIZE = 20

i18n.addResourceBundle(
  'en',
  'translation',
  {
    settings: { auditLogs: 'Audit Logs' },
    auditLogs: {
      description: 'Review security-relevant user actions in this tenant.',
      eventType: 'Event type',
      actorUserId: 'Actor user ID',
      from: 'From (ISO)',
      to: 'To (ISO)',
      export: 'Export CSV',
      exportTruncated: 'Only the first 1000 matching rows were exported.',
      noRows: 'No audit events match your filters.',
      loadFailed: 'Failed to load audit logs.',
      exportFailed: 'Export failed.',
      timeCol: 'Time',
      eventCol: 'Event',
      actorCol: 'Actor',
      outcomeCol: 'Outcome',
      resourceCol: 'Resource',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    settings: { auditLogs: '审计日志' },
    auditLogs: {
      description: '查看本租户内与安全相关的用户操作记录。',
      eventType: '事件类型',
      actorUserId: '操作人用户 ID',
      from: '开始时间 (ISO)',
      to: '结束时间 (ISO)',
      export: '导出 CSV',
      exportTruncated: '仅导出了匹配的前 1000 条记录。',
      noRows: '没有符合筛选条件的审计事件。',
      loadFailed: '加载审计日志失败。',
      exportFailed: '导出失败。',
      timeCol: '时间',
      eventCol: '事件',
      actorCol: '操作人',
      outcomeCol: '结果',
      resourceCol: '资源',
    },
  },
  true,
  true
)

export default function SettingsAuditLogsTab() {
  const { t } = useTranslation()
  const formatDt = useFormatUserDateTime()
  const { hasAny } = useAuth()
  const { showError, showSuccess } = useNotification()
  const canExport = hasAny([PERMISSIONS.AUDIT_MANAGE])

  const [page, setPage] = useState(1)
  const [eventType, setEventType] = useState('')
  const [actorUserId, setActorUserId] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  const queryParams = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      event_type: eventType.trim() || undefined,
      actor_user_id: actorUserId.trim() ? Number(actorUserId) : undefined,
      from: from.trim() || undefined,
      to: to.trim() || undefined,
    }),
    [actorUserId, eventType, from, page, to]
  )

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['audit-events', queryParams],
    queryFn: () => listAuditEvents(queryParams),
  })

  const rows: AuditEventDTO[] = data?.items ?? []

  const handleExport = async () => {
    try {
      const { blob, truncated } = await exportAuditEvents({
        event_type: queryParams.event_type,
        actor_user_id: queryParams.actor_user_id,
        from: queryParams.from,
        to: queryParams.to,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'audit_events.csv'
      a.click()
      URL.revokeObjectURL(url)
      if (truncated) {
        showSuccess(t('auditLogs.exportTruncated'))
      }
    } catch (err) {
      showError(getApiErrorMessage(err) || t('auditLogs.exportFailed'))
    }
  }

  return (
    <SettingsPageShell title={t('settings.auditLogs')}>
      <SettingsSection title={t('settings.auditLogs')} description={t('auditLogs.description')}>
        <SettingsListToolbar
          actions={
            canExport ? (
              <Button variant="outline" size="sm" onClick={handleExport}>
                <Download className="mr-2 h-4 w-4" />
                {t('auditLogs.export')}
              </Button>
            ) : null
          }
        >
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            <Input
              placeholder={t('auditLogs.eventType')}
              value={eventType}
              onChange={(e) => {
                setPage(1)
                setEventType(e.target.value)
              }}
            />
            <Input
              placeholder={t('auditLogs.actorUserId')}
              value={actorUserId}
              onChange={(e) => {
                setPage(1)
                setActorUserId(e.target.value)
              }}
            />
            <Input
              placeholder={t('auditLogs.from')}
              value={from}
              onChange={(e) => {
                setPage(1)
                setFrom(e.target.value)
              }}
            />
            <Input
              placeholder={t('auditLogs.to')}
              value={to}
              onChange={(e) => {
                setPage(1)
                setTo(e.target.value)
              }}
            />
          </div>
        </SettingsListToolbar>

        {isError ? (
          <p className="py-6 text-sm text-destructive">
            {t('auditLogs.loadFailed')}{' '}
            <button type="button" className="underline" onClick={() => refetch()}>
              Retry
            </button>
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('auditLogs.timeCol')}</TableHead>
                <TableHead>{t('auditLogs.eventCol')}</TableHead>
                <TableHead>{t('auditLogs.actorCol')}</TableHead>
                <TableHead>{t('auditLogs.outcomeCol')}</TableHead>
                <TableHead>{t('auditLogs.resourceCol')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    ...
                  </TableCell>
                </TableRow>
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    {t('auditLogs.noRows')}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>{formatDt(row.created_at)}</TableCell>
                    <TableCell className="font-mono text-xs">{row.event_type}</TableCell>
                    <TableCell>{row.actor_user_id ?? '—'}</TableCell>
                    <TableCell>{row.outcome ?? '—'}</TableCell>
                    <TableCell className="text-xs">
                      {row.resource_type ? `${row.resource_type}:${row.resource_id ?? ''}` : '—'}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}

        {data && data.total_pages > 1 ? (
          <PaginationBar
            page={data.page}
            totalPages={data.total_pages}
            onPageChange={setPage}
            className="mt-4"
          />
        ) : null}
      </SettingsSection>
    </SettingsPageShell>
  )
}