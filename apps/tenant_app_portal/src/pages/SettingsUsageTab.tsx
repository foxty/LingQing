import i18n from '@/i18n/config'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import SettingsPageShell from '@/components/SettingsPageShell'
import SettingsSection from '@/components/SettingsSection'
import { Card, CardContent } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import TimeRangePicker from '@/components/TimeRangePicker'
import { useTenantStats } from '@/hooks/useTenantStats'
import {
  useTenantTokenDaily,
  useTenantTokenSummary,
  useTenantUsageEvents,
} from '@/hooks/useTenantUsage'
import TenantUserFilterCombobox from '@/components/TenantUserFilterCombobox'
import { useTokenUsageTimeRange } from '@/hooks/useTokenUsageTimeRange'
import TokenTrendChart from '@/pages/usage/TokenTrendChart'
import StorageSnapshotCard from '@/pages/usage/StorageSnapshotCard'
import TokenTable from '@/pages/usage/TokenTable'
import UsageSummaryMetrics from '@/pages/usage/UsageSummaryMetrics'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    usageTab: {
      title: 'Usage',
      description: 'Monitor token consumption and storage',
      tokenUsageTitle: 'Token Usage',
      tokenUsageDesc: 'LLM token consumption · {{period}}',
      tokenUsageDescForUser: '{{username}} · {{period}}',
      storageTitle: 'Storage',
      storageDesc: 'Tenant-wide storage snapshot',
      selectUser: 'Select user',
      allUsers: 'All users',
      userSearch: 'Search users…',
      userSearchEmpty: 'No users found',
      loadFailed: 'Failed to load usage data',
      tokenLoadFailed: 'Failed to load token usage data',
      totalTokens: 'Total Tokens',
      inputTokens: 'Input Tokens',
      outputTokens: 'Output Tokens',
      llmCalls: 'LLM Calls',
      toolCalls: 'Tool Calls',
      activeUsers: 'Active Users',
      currentStorage: 'Current Storage',
      lastNDays: 'last {{days}} days',
      tokenBreakdown: '{{input}} input · {{output}} output',
      reachSection: 'Reach',
      performanceSection: 'Performance',
      llmErrorRate: 'LLM Error Rate',
      toolErrorRate: 'Tool Error Rate',
      avgLlmDuration: 'Avg LLM Duration',
      avgToolDuration: 'Avg Tool Duration',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    usageTab: {
      title: '用量',
      description: '监控令牌消耗和存储',
      tokenUsageTitle: '令牌用量',
      tokenUsageDesc: 'LLM 令牌消耗 · {{period}}',
      tokenUsageDescForUser: '{{username}} · {{period}}',
      storageTitle: '存储',
      storageDesc: '租户级存储快照',
      selectUser: '选择用户',
      allUsers: '全部用户',
      userSearch: '搜索用户…',
      userSearchEmpty: '未找到用户',
      loadFailed: '加载用量数据失败',
      tokenLoadFailed: '加载令牌用量数据失败',
      totalTokens: '总令牌数',
      inputTokens: '输入令牌',
      outputTokens: '输出令牌',
      llmCalls: 'LLM 调用',
      toolCalls: '工具调用',
      activeUsers: '活跃用户',
      currentStorage: '当前存储',
      lastNDays: '最近 {{days}} 天',
      tokenBreakdown: '{{input}} 输入 · {{output}} 输出',
      reachSection: '覆盖',
      performanceSection: '性能',
      llmErrorRate: 'LLM 错误率',
      toolErrorRate: '工具错误率',
      avgLlmDuration: 'LLM 平均耗时',
      avgToolDuration: '工具平均耗时',
    }
  }
}, true, true)

export default function SettingsUsageTab() {
  const { t } = useTranslation()
  const { timeRange, setTimeRange, bounds, periodLabel } = useTokenUsageTimeRange()
  const [page, setPage] = useState(1)
  const [selectedUserId, setSelectedUserId] = useState<number | undefined>(undefined)
  const [selectedUsername, setSelectedUsername] = useState<string | undefined>(undefined)

  const tokenFilter = useMemo(
    () => ({ ...bounds, user_id: selectedUserId }),
    [bounds, selectedUserId]
  )

  const statsQuery = useTenantStats()
  const tokenSummaryQuery = useTenantTokenSummary(tokenFilter)
  const tokenDailyQuery = useTenantTokenDaily(tokenFilter)

  const eventsQuery = useTenantUsageEvents({
    ...bounds,
    page,
    page_size: 20,
    user_id: selectedUserId,
  })

  const tokenSummary = tokenSummaryQuery.data
  const tokenDaily = tokenDailyQuery.data || []
  const events = eventsQuery.data
  const tokenError = (tokenSummaryQuery.error ||
    tokenDailyQuery.error ||
    eventsQuery.error) as Error | null
  const storageError = statsQuery.error as Error | null
  const tokenLoading =
    tokenSummaryQuery.isLoading || tokenDailyQuery.isLoading || eventsQuery.isLoading

  const handleRefreshToken = () => {
    tokenSummaryQuery.refetch()
    tokenDailyQuery.refetch()
    eventsQuery.refetch()
  }

  const tokenSectionDescription = selectedUsername
    ? t('settings.usageTab.tokenUsageDescForUser', { period: periodLabel, username: selectedUsername })
    : t('settings.usageTab.tokenUsageDesc', { period: periodLabel })

  const tokenFilters = (
    <div className="flex flex-wrap items-center gap-2">
      <TimeRangePicker
        className="min-w-[220px]"
        value={timeRange}
        onChange={(next) => {
          setPage(1)
          setTimeRange(next)
        }}
      />
      <div className="min-w-[12rem] flex-1 sm:max-w-xs">
        <TenantUserFilterCombobox
          className="w-full"
          value={selectedUserId}
          onChange={(id, username) => {
            setPage(1)
            setSelectedUserId(id)
            setSelectedUsername(username)
          }}
          labels={{
            placeholder: t('settings.usageTab.allUsers'),
            searchPlaceholder: t('settings.usageTab.userSearch'),
            emptyMessage: t('settings.usageTab.userSearchEmpty'),
            clearLabel: t('settings.usageTab.allUsers'),
            numericFallbackPlaceholder: t('settings.usageTab.selectUser'),
          }}
        />
      </div>
      <Button variant="outline" onClick={handleRefreshToken}>
        <RefreshCw className="mr-2 h-4 w-4" />
        {t('common.refresh')}
      </Button>
    </div>
  )

  return (
    <SettingsPageShell>
      <SettingsSection
        title={t('settings.usageTab.title')}
        description={t('settings.usageTab.description')}
      />

      <SettingsSection
        title={t('settings.usageTab.tokenUsageTitle')}
        description={tokenSectionDescription}
        action={tokenFilters}
      >
        {tokenError && (
          <Alert variant="destructive" className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {tokenError.message || t('settings.usageTab.tokenLoadFailed')}
            </AlertDescription>
          </Alert>
        )}

        {tokenLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <UsageSummaryMetrics
            summary={tokenSummary}
            periodLabel={periodLabel}
            showReachMetrics={false}
            embedded
          />
        )}
      </SettingsSection>

      {!tokenLoading && (
        <>
          <TokenTrendChart periodLabel={periodLabel} username={selectedUsername} rows={tokenDaily} />
          <TokenTable
            periodLabel={periodLabel}
            username={selectedUsername}
            isLoading={eventsQuery.isLoading}
            events={events}
            page={page}
            onPageChange={setPage}
          />
        </>
      )}

      {storageError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {storageError.message || t('settings.usageTab.loadFailed')}
          </AlertDescription>
        </Alert>
      )}
      {statsQuery.isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      ) : (
        <StorageSnapshotCard
          totalStorageBytes={statsQuery.data?.total_storage_bytes || 0}
          updatedAt={tokenSummary?.period_end}
        />
      )}
    </SettingsPageShell>
  )
}
