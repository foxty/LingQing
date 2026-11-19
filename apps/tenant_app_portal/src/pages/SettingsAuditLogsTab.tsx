import PaginationBar from '@/components/PaginationBar'
import SettingsPageShell from '@/components/SettingsPageShell'
import SettingsSection from '@/components/SettingsSection'
import SearchableCombobox from '@/components/SearchableCombobox'
import TenantUserFilterCombobox from '@/components/TenantUserFilterCombobox'
import TimeRangePicker, { type TimeRangeValue } from '@/components/TimeRangePicker'
import { Button } from '@/components/ui/button'
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
import {
  exportAuditEvents,
  formatAuditPayload,
  listAuditEventTypes,
  listAuditEvents,
  type AuditEventDTO,
} from '@/lib/auditApi'
import { resolveTimeRangeToIsoBounds } from '@/lib/timeRangeUtils'
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
      eventTypePlaceholder: 'All event types',
      eventTypeSearch: 'Search event types…',
      eventTypeEmpty: 'No matching event types',
      eventTypeUseCustom: 'Filter: {{value}}',
      clearEventType: 'Clear event type',
      actorUserId: 'Actor user ID',
      actorUserPlaceholder: 'All actors',
      actorUserSearch: 'Search users…',
      actorUserEmpty: 'No users found',
      clearActor: 'Clear actor',
      clearTimeRange: 'Clear time range',
      payloadCol: 'Payload',
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
      eventTypePlaceholder: '全部事件类型',
      eventTypeSearch: '搜索事件类型…',
      eventTypeEmpty: '没有匹配的事件类型',
      eventTypeUseCustom: '筛选：{{value}}',
      clearEventType: '清除事件类型',
      actorUserId: '操作人用户 ID',
      actorUserPlaceholder: '全部操作人',
      actorUserSearch: '搜索用户…',
      actorUserEmpty: '未找到用户',
      clearActor: '清除操作人',
      clearTimeRange: '清除时间范围',
      payloadCol: '详情',
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
  const [actorUserId, setActorUserId] = useState<number | undefined>(undefined)
  const [actorUsernames, setActorUsernames] = useState<Record<number, string>>({})
  const [timeRange, setTimeRange] = useState<TimeRangeValue | null>(null)
  const isoBounds = useMemo(() => resolveTimeRangeToIsoBounds(timeRange, 'datetime'), [timeRange])

  const eventTypesQuery = useQuery({
    queryKey: ['audit-event-types'],
    queryFn: listAuditEventTypes,
  })

  const eventTypeOptions = useMemo(
    () => (eventTypesQuery.data?.items ?? []).map((value) => ({ value, label: value })),
    [eventTypesQuery.data?.items]
  )

  const queryParams = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      event_type: eventType.trim() || undefined,
      actor_user_id: actorUserId,
      from: isoBounds.from,
      to: isoBounds.to,
    }),
    [actorUserId, eventType, isoBounds.from, isoBounds.to, page]
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
      showError(getApiErrorMessage(err, t('auditLogs.exportFailed')))
    }
  }

  return (
    <SettingsPageShell>
      <SettingsSection
        title={t('settings.auditLogs')}
        description={t('auditLogs.description')}
        action={
          canExport ? (
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="mr-2 h-4 w-4" />
              {t('auditLogs.export')}
            </Button>
          ) : undefined
        }
      >
        <div className="mb-4 grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 xl:grid-cols-3 xl:items-start">
          <SearchableCombobox
            className="w-full min-w-0"
            value={eventType}
            onChange={(next) => {
              setPage(1)
              setEventType(next)
            }}
            options={eventTypeOptions}
            placeholder={t('auditLogs.eventTypePlaceholder')}
            searchPlaceholder={t('auditLogs.eventTypeSearch')}
            emptyMessage={t('auditLogs.eventTypeEmpty')}
            clearLabel={t('auditLogs.clearEventType')}
            allowFreeform
            freeformActionLabel={(q) => t('auditLogs.eventTypeUseCustom', { value: q })}
            disabled={eventTypesQuery.isLoading}
          />
          <TenantUserFilterCombobox
            className="w-full min-w-0"
            value={actorUserId}
            onChange={(id, username) => {
              setPage(1)
              setActorUserId(id)
              if (id != null && username) {
                setActorUsernames((prev) => ({ ...prev, [id]: username }))
              }
            }}
          />
          <div className="flex min-w-0 flex-col gap-1 min-[480px]:col-span-2 xl:col-span-1">
            <TimeRangePicker
              className="w-full"
              value={timeRange}
              precision="datetime"
              onChange={(next) => {
                setPage(1)
                setTimeRange(next)
              }}
            />
            {timeRange ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 self-start px-2 text-xs"
                onClick={() => {
                  setPage(1)
                  setTimeRange(null)
                }}
              >
                {t('auditLogs.clearTimeRange')}
              </Button>
            ) : null}
          </div>
        </div>

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
                <TableHead className="min-w-[12rem]">{t('auditLogs.payloadCol')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    ...
                  </TableCell>
                </TableRow>
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    {t('auditLogs.noRows')}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => {
                  const payloadText = formatAuditPayload(row.payload)
                  const actorLabel =
                    row.actor_user_id != null
                      ? actorUsernames[row.actor_user_id] ?? row.actor_user_id
                      : '—'
                  return (
                    <TableRow key={row.id}>
                      <TableCell>{formatDt(row.created_at)}</TableCell>
                      <TableCell className="font-mono text-xs">{row.event_type}</TableCell>
                      <TableCell className="text-xs">{actorLabel}</TableCell>
                      <TableCell>{row.outcome ?? '—'}</TableCell>
                      <TableCell className="text-xs">
                        {row.resource_type ? `${row.resource_type}:${row.resource_id ?? ''}` : '—'}
                      </TableCell>
                      <TableCell
                        className="max-w-[20rem] truncate font-mono text-xs text-muted-foreground"
                        title={payloadText || undefined}
                      >
                        {payloadText || '—'}
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        )}

        {data && data.total_pages > 1 ? (
          <div className="mt-4">
            <PaginationBar
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              totalPages={data.total_pages}
              onPageChange={setPage}
            />
          </div>
        ) : null}
      </SettingsSection>
    </SettingsPageShell>
  )
}