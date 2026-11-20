import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import PaginationBar from '@/components/PaginationBar'
import SettingsSection from '@/components/SettingsSection'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useFormatUserDateTime } from '@/hooks/useUserDateTimeFormat'
import type { TokenUsageEventsResponse } from '@/lib/tenantApi'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    usageTab: {
      tokenDetails: 'Token Details',
      tokenDetailsDesc: 'Token usage details · {{period}}',
      tokenDetailsDescForUser: '{{username}} · {{period}}',
      timeCol: 'Time',
      userCol: 'User',
      modelCol: 'Model',
      sessionCol: 'Session',
      noRecords: 'No records',
      cacheReadCol: 'Cache read',
      cacheReadHint: 'Included in Input',
      thinkingCol: 'Thinking',
      thinkingHint: 'Included in Output',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    usageTab: {
      tokenDetails: '令牌明细',
      tokenDetailsDesc: '令牌用量明细 · {{period}}',
      tokenDetailsDescForUser: '{{username}} · {{period}}',
      timeCol: '时间',
      userCol: '用户',
      modelCol: '模型',
      sessionCol: '会话',
      noRecords: '暂无记录',
      cacheReadCol: '缓存读取',
      cacheReadHint: '已计入输入',
      thinkingCol: '思考',
      thinkingHint: '已计入输出',
    }
  }
}, true, true)

function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

function formatOptionalCount(value: number | null | undefined): string {
  if (value == null) {
    return '—'
  }
  return formatNumber(value)
}

interface TokenTableProps {
  periodLabel: string
  username?: string
  isLoading: boolean
  events?: TokenUsageEventsResponse
  page: number
  onPageChange: (page: number) => void
}

export default function TokenTable({
  periodLabel,
  username,
  isLoading,
  events,
  page,
  onPageChange,
}: TokenTableProps) {
  const { t } = useTranslation()
  const formatUserDateTime = useFormatUserDateTime()
  const description = username
    ? t('settings.usageTab.tokenDetailsDescForUser', { period: periodLabel, username })
    : t('settings.usageTab.tokenDetailsDesc', { period: periodLabel })

  return (
    <SettingsSection
      title={t('settings.usageTab.tokenDetails')}
      description={description}
    >
      <div className="space-y-4">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('settings.usageTab.timeCol')}</TableHead>
                  <TableHead>{t('settings.usageTab.userCol')}</TableHead>
                  <TableHead>{t('settings.usageTab.modelCol')}</TableHead>
                  <TableHead>{t('settings.usageTab.sessionCol')}</TableHead>
                  <TableHead className="text-right">Input</TableHead>
                  <TableHead className="text-right" title={t('settings.usageTab.cacheReadHint')}>
                    {t('settings.usageTab.cacheReadCol')}
                  </TableHead>
                  <TableHead className="text-right">Output</TableHead>
                  <TableHead className="text-right" title={t('settings.usageTab.thinkingHint')}>
                    {t('settings.usageTab.thinkingCol')}
                  </TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events?.rows?.length ? (
                  events.rows.map((row) => (
                    <TableRow key={row.event_id}>
                      <TableCell>{formatUserDateTime(row.timestamp)}</TableCell>
                      <TableCell>{row.username || '-'}</TableCell>
                      <TableCell>{row.model_label || row.model_key || row.model_name || '-'}</TableCell>
                      <TableCell className="max-w-[220px] truncate" title={row.session_id}>
                        {row.session_id}
                      </TableCell>
                      <TableCell className="text-right">{formatNumber(row.input_tokens)}</TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {formatOptionalCount(row.cache_read_input_tokens)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatNumber(row.output_tokens)}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {formatOptionalCount(row.reasoning_tokens)}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatNumber(row.total_tokens)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center text-muted-foreground">
                      {t('settings.usageTab.noRecords')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <PaginationBar
              page={page}
              pageSize={events?.page_size || 20}
              total={events?.total || 0}
              totalPages={events?.total_pages || 0}
              onPageChange={onPageChange}
            />
          </>
        )}
      </div>
    </SettingsSection>
  )
}
