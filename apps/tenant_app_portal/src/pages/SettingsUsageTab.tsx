import i18n from '@/i18n/config'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import SettingsSection from '@/components/SettingsSection'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useTenantStats } from '@/hooks/useTenantStats'
import {
  useTenantTokenDaily,
  useTenantTokenSummary,
  useTenantUsageEvents,
} from '@/hooks/useTenantUsage'
import { useTenantUsersList } from '@/hooks/useTenantUsers'
import TokenTrendChart from '@/pages/usage/TokenTrendChart'
import StorageSnapshotCard from '@/pages/usage/StorageSnapshotCard'
import TokenTable from '@/pages/usage/TokenTable'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    usageTab: {
      title: 'Usage',
      description: 'Monitor token consumption and storage',
      tokenUsageTitle: 'Token Usage',
      tokenUsageDesc: 'LLM token consumption over the last {{days}} days',
      tokenUsageDescForUser: 'LLM token consumption for {{username}} over the last {{days}} days',
      storageTitle: 'Storage',
      storageDesc: 'Tenant-wide storage snapshot',
      selectTimeRange: 'Select time range',
      last7Days: 'Last 7 days',
      last30Days: 'Last 30 days',
      last90Days: 'Last 90 days',
      selectUser: 'Select user',
      allUsers: 'All users',
      loadFailed: 'Failed to load usage data',
      tokenLoadFailed: 'Failed to load token usage data',
      totalTokens: 'Total Tokens',
      inputTokens: 'Input Tokens',
      outputTokens: 'Output Tokens',
      llmCalls: 'LLM Calls',
      activeUsers: 'Active Users',
      currentStorage: 'Current Storage',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    usageTab: {
      title: '用量',
      description: '监控令牌消耗和存储',
      tokenUsageTitle: '令牌用量',
      tokenUsageDesc: '最近 {{days}} 天的 LLM 令牌消耗',
      tokenUsageDescForUser: '{{username}} 最近 {{days}} 天的 LLM 令牌消耗',
      storageTitle: '存储',
      storageDesc: '租户级存储快照',
      selectTimeRange: '选择时间范围',
      last7Days: '最近 7 天',
      last30Days: '最近 30 天',
      last90Days: '最近 90 天',
      selectUser: '选择用户',
      allUsers: '全部用户',
      loadFailed: '加载用量数据失败',
      tokenLoadFailed: '加载令牌用量数据失败',
      totalTokens: '总令牌数',
      inputTokens: '输入令牌',
      outputTokens: '输出令牌',
      llmCalls: 'LLM 调用',
      activeUsers: '活跃用户',
      currentStorage: '当前存储',
    }
  }
}, true, true)

function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

function buildRange(days: number): { start_time: string; end_time: string } {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - days)
  return {
    start_time: start.toISOString(),
    end_time: end.toISOString(),
  }
}

export default function SettingsUsageTab() {
  const { t } = useTranslation()
  const [days, setDays] = useState(30)
  const [page, setPage] = useState(1)
  const [userFilter, setUserFilter] = useState('all')

  const tokenFilter = useMemo(() => {
    const userId = userFilter === 'all' ? undefined : Number(userFilter)
    return { days, user_id: userId }
  }, [days, userFilter])

  const statsQuery = useTenantStats()
  const tokenSummaryQuery = useTenantTokenSummary(tokenFilter)
  const tokenDailyQuery = useTenantTokenDaily(tokenFilter)
  const usersQuery = useTenantUsersList()

  const range = useMemo(() => buildRange(days), [days])
  const selectedUserId = userFilter === 'all' ? undefined : Number(userFilter)
  const selectedUsername = useMemo(() => {
    if (selectedUserId === undefined) {
      return undefined
    }
    return usersQuery.data?.find((user) => user.id === selectedUserId)?.username
  }, [selectedUserId, usersQuery.data])

  const eventsQuery = useTenantUsageEvents({
    ...range,
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

  const handleDaysChange = (value: string) => {
    setDays(Number(value))
    setPage(1)
  }

  const handleUserChange = (value: string) => {
    setUserFilter(value)
    setPage(1)
  }

  const handleRefreshToken = () => {
    tokenSummaryQuery.refetch()
    tokenDailyQuery.refetch()
    eventsQuery.refetch()
  }

  const sortedUsers = useMemo(
    () => [...(usersQuery.data || [])].sort((a, b) => a.username.localeCompare(b.username)),
    [usersQuery.data]
  )

  const tokenSectionDescription = selectedUsername
    ? t('settings.usageTab.tokenUsageDescForUser', { days, username: selectedUsername })
    : t('settings.usageTab.tokenUsageDesc', { days })

  const tokenFilters = (
    <div className="flex items-center gap-2">
      <div className="w-40">
        <Select value={String(days)} onValueChange={handleDaysChange}>
          <SelectTrigger>
            <SelectValue placeholder={t('settings.usageTab.selectTimeRange')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">{t('settings.usageTab.last7Days')}</SelectItem>
            <SelectItem value="30">{t('settings.usageTab.last30Days')}</SelectItem>
            <SelectItem value="90">{t('settings.usageTab.last90Days')}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="w-48">
        <Select value={userFilter} onValueChange={handleUserChange}>
          <SelectTrigger>
            <SelectValue placeholder={t('settings.usageTab.selectUser')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('settings.usageTab.allUsers')}</SelectItem>
            {sortedUsers.map((user) => (
              <SelectItem key={user.id} value={String(user.id)}>
                {user.username}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Button variant="outline" onClick={handleRefreshToken}>
        <RefreshCw className="mr-2 h-4 w-4" />
        {t('common.refresh')}
      </Button>
    </div>
  )

  return (
    <div className="space-y-4">
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
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card>
              <CardHeader className="p-4 pb-3">
                <CardDescription>{t('settings.usageTab.totalTokens')}</CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums">
                  {formatNumber(tokenSummary?.total_tokens || 0)}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="p-4 pb-3">
                <CardDescription>{t('settings.usageTab.inputTokens')}</CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums">
                  {formatNumber(tokenSummary?.total_input_tokens || 0)}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="p-4 pb-3">
                <CardDescription>{t('settings.usageTab.outputTokens')}</CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums">
                  {formatNumber(tokenSummary?.total_output_tokens || 0)}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="p-4 pb-3">
                <CardDescription>{t('settings.usageTab.llmCalls')}</CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums">
                  {formatNumber(tokenSummary?.total_llm_calls || 0)}
                </CardTitle>
              </CardHeader>
            </Card>
          </div>
        )}
      </SettingsSection>

      {!tokenLoading && (
        <>
          <TokenTrendChart days={days} username={selectedUsername} rows={tokenDaily} />
          <TokenTable
            days={days}
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
    </div>
  )
}
