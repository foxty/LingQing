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
import { formatDate } from '@/lib/dateTime'
import type { TokenUsageEventsResponse } from '@/lib/tenantApi'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    usageTab: {
      tokenDetails: 'Token Details',
      tokenDetailsDesc: 'Token usage details over the last {{days}} days',
      tokenDetailsDescForUser: 'Token usage details for {{username}} over the last {{days}} days',
      timeCol: 'Time',
      userCol: 'User',
      modelCol: 'Model',
      sessionCol: 'Session',
      noRecords: 'No records',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    usageTab: {
      tokenDetails: '令牌明细',
      tokenDetailsDesc: '最近 {{days}} 天的令牌用量明细',
      tokenDetailsDescForUser: '{{username}} 最近 {{days}} 天的令牌用量明细',
      timeCol: '时间',
      userCol: '用户',
      modelCol: '模型',
      sessionCol: '会话',
      noRecords: '暂无记录',
    }
  }
}, true, true)

function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

interface TokenTableProps {
  days: number
  username?: string
  isLoading: boolean
  events?: TokenUsageEventsResponse
  page: number
  onPageChange: (page: number) => void
}

export default function TokenTable({
  days,
  username,
  isLoading,
  events,
  page,
  onPageChange,
}: TokenTableProps) {
  const { t } = useTranslation()
  const description = username
    ? t('settings.usageTab.tokenDetailsDescForUser', { days, username })
    : t('settings.usageTab.tokenDetailsDesc', { days })

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
                  <TableHead className="text-right">Output</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events?.rows?.length ? (
                  events.rows.map((row) => (
                    <TableRow key={row.event_id}>
                      <TableCell>{formatDate(row.timestamp)}</TableCell>
                      <TableCell>{row.username || '-'}</TableCell>
                      <TableCell>{row.model_label || row.model_key || row.model_name || '-'}</TableCell>
                      <TableCell className="max-w-[220px] truncate" title={row.session_id}>
                        {row.session_id}
                      </TableCell>
                      <TableCell className="text-right">{formatNumber(row.input_tokens)}</TableCell>
                      <TableCell className="text-right">
                        {formatNumber(row.output_tokens)}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatNumber(row.total_tokens)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-muted-foreground">
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
