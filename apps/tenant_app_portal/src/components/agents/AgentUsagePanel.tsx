import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  useAgentUsageDaily,
  useAgentUsageEvents,
  useAgentUsageSummary,
} from '@/hooks/useAgentUsage'
import TenantUserFilterCombobox from '@/components/TenantUserFilterCombobox'
import TimeRangePicker from '@/components/TimeRangePicker'
import { USAGE_TOKEN_TIME_RANGE_PRESET_VALUES } from '@/lib/timeRangeUtils'
import { useTokenUsageTimeRange } from '@/hooks/useTokenUsageTimeRange'
import TokenTrendChart from '@/pages/usage/TokenTrendChart'
import TokenTable from '@/pages/usage/TokenTable'
import UsageSummaryMetrics from '@/pages/usage/UsageSummaryMetrics'

type AgentUsagePanelProps = {
  agentId: number
  enabled?: boolean
}

export default function AgentUsagePanel({ agentId, enabled = true }: AgentUsagePanelProps) {
  const { t } = useTranslation()
  const { timeRange, setTimeRange, bounds, periodLabel } = useTokenUsageTimeRange()
  const [page, setPage] = useState(1)
  const [selectedUserId, setSelectedUserId] = useState<number | undefined>(undefined)
  const [selectedUsername, setSelectedUsername] = useState<string | undefined>(undefined)

  const tokenFilter = useMemo(
    () => ({ ...bounds, user_id: selectedUserId }),
    [bounds, selectedUserId]
  )

  const summaryQuery = useAgentUsageSummary(agentId, tokenFilter, enabled)
  const dailyQuery = useAgentUsageDaily(agentId, tokenFilter, enabled)

  const eventsQuery = useAgentUsageEvents(
    agentId,
    { ...bounds, page, page_size: 20, user_id: selectedUserId },
    enabled
  )

  const tokenSummary = summaryQuery.data
  const tokenDaily = dailyQuery.data ?? []
  const events = eventsQuery.data
  const tokenError = (summaryQuery.error || dailyQuery.error || eventsQuery.error) as Error | null
  const tokenLoading = summaryQuery.isLoading || dailyQuery.isLoading || eventsQuery.isLoading

  const handleRefresh = () => {
    summaryQuery.refetch()
    dailyQuery.refetch()
    eventsQuery.refetch()
  }

  const periodDescription = selectedUsername
    ? t('settings.usageTab.tokenUsageDescForUser', { period: periodLabel, username: selectedUsername })
    : t('settings.usageTab.tokenUsageDesc', { period: periodLabel })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{periodDescription}</p>
        <div className="flex flex-wrap items-center gap-2">
          <TimeRangePicker
            className="min-w-[220px]"
            value={timeRange}
            presets={USAGE_TOKEN_TIME_RANGE_PRESET_VALUES}
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
          <UsageSummaryMetrics summary={tokenSummary} periodLabel={periodLabel} showReachMetrics />
          <TokenTrendChart periodLabel={periodLabel} rows={tokenDaily} />
          <TokenTable
            periodLabel={periodLabel}
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