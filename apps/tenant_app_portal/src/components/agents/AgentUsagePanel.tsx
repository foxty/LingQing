import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useAgentUsageDaily,
  useAgentUsageEvents,
  useAgentUsageSummary,
} from '@/hooks/useAgentUsage'
import { useTenantUsersList } from '@/hooks/useTenantUsers'
import { buildRelativeIsoRange } from '@shared/frontend/format'
import TokenTrendChart from '@/pages/usage/TokenTrendChart'
import TokenTable from '@/pages/usage/TokenTable'
import UsageSummaryMetrics from '@/pages/usage/UsageSummaryMetrics'

type AgentUsagePanelProps = {
  agentId: number
  enabled?: boolean
}

export default function AgentUsagePanel({ agentId, enabled = true }: AgentUsagePanelProps) {
  const { t } = useTranslation()
  const [days, setDays] = useState(30)
  const [page, setPage] = useState(1)
  const [userFilter, setUserFilter] = useState('all')

  const tokenFilter = useMemo(() => {
    const userId = userFilter === 'all' ? undefined : Number(userFilter)
    return { days, user_id: userId }
  }, [days, userFilter])

  const summaryQuery = useAgentUsageSummary(agentId, tokenFilter, enabled)
  const dailyQuery = useAgentUsageDaily(agentId, tokenFilter, enabled)
  const usersQuery = useTenantUsersList()

  const range = useMemo(() => buildRelativeIsoRange(days), [days])
  const selectedUserId = userFilter === 'all' ? undefined : Number(userFilter)
  const selectedUsername = useMemo(() => {
    if (selectedUserId === undefined) {
      return undefined
    }
    return usersQuery.data?.find((user) => user.id === selectedUserId)?.username
  }, [selectedUserId, usersQuery.data])

  const eventsQuery = useAgentUsageEvents(
    agentId,
    { ...range, page, page_size: 20, user_id: selectedUserId },
    enabled
  )

  const tokenSummary = summaryQuery.data
  const tokenDaily = dailyQuery.data ?? []
  const events = eventsQuery.data
  const tokenError = (summaryQuery.error || dailyQuery.error || eventsQuery.error) as Error | null
  const tokenLoading = summaryQuery.isLoading || dailyQuery.isLoading || eventsQuery.isLoading

  const handleDaysChange = (value: string) => {
    setDays(Number(value))
    setPage(1)
  }

  const handleUserChange = (value: string) => {
    setUserFilter(value)
    setPage(1)
  }

  const handleRefresh = () => {
    summaryQuery.refetch()
    dailyQuery.refetch()
    eventsQuery.refetch()
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {selectedUsername
            ? t('settings.usageTab.tokenUsageDescForUser', { days, username: selectedUsername })
            : t('settings.usageTab.tokenUsageDesc', { days })}
        </p>
        <div className="flex flex-wrap items-center gap-2">
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
          <div className="w-44">
            <Select value={userFilter} onValueChange={handleUserChange}>
              <SelectTrigger>
                <SelectValue placeholder={t('settings.usageTab.selectUser')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('settings.usageTab.allUsers')}</SelectItem>
                {(usersQuery.data ?? []).map((user) => (
                  <SelectItem key={user.id} value={String(user.id)}>
                    {user.username}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button variant="outline" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t('common.refresh')}
          </Button>
        </div>
      </div>

      {tokenError ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {tokenError.message || t('settings.usageTab.tokenLoadFailed')}
          </AlertDescription>
        </Alert>
      ) : null}

      {tokenLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          <UsageSummaryMetrics summary={tokenSummary} days={days} showReachMetrics />
          <TokenTrendChart days={days} rows={tokenDaily} />
          <TokenTable
            days={days}
            isLoading={eventsQuery.isLoading}
            events={events}
            page={page}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  )
}
