import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

i18n.addResourceBundle('en', 'translation', {
  components: {
    hitlApproval: {
      loadDetailFailed: 'Failed to load details',
      loadingDetail: 'Loading...',
      agentWillUse: 'The agent wants to use "{{tool}}"',
      needsConfirmation: 'Needs your confirmation',
      pending: 'Pending',
      approved: 'Approved',
      rejected: 'Rejected',
      approve: 'Approve',
      reject: 'Reject',
      approveFailed: 'Failed to approve',
      approvedSuccess: 'Approved',
      rejectedSuccess: 'Rejected',
      rejectFailed: 'Failed to reject',
      copied: 'Copied',
      copyFailed: 'Failed to copy',
      tool: 'Tool',
      copyToolName: 'Copy',
      riskLevel: 'Risk Level',
      expiresAt: 'Expires At',
      approvedAt: 'Approved At',
      rejectedAt: 'Rejected At',
      copyProposalId: 'Proposal ID',
      callParams: 'Call Parameters',
      expandToView: 'Click to view',
      remark: '{{reason}}',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    hitlApproval: {
      loadDetailFailed: '加载详情失败',
      loadingDetail: '加载中...',
      agentWillUse: '助手想要使用 "{{tool}}"',
      needsConfirmation: '需要你的确认',
      pending: '待审批',
      approved: '已批准',
      rejected: '已拒绝',
      approve: '批准',
      reject: '拒绝',
      approveFailed: '批准失败',
      approvedSuccess: '已批准',
      rejectedSuccess: '已拒绝',
      rejectFailed: '拒绝失败',
      copied: '已复制',
      copyFailed: '复制失败',
      tool: '工具',
      copyToolName: '复制',
      riskLevel: '风险级别',
      expiresAt: '过期时间',
      approvedAt: '批准时间',
      rejectedAt: '拒绝时间',
      copyProposalId: '提案 ID',
      callParams: '调用参数',
      expandToView: '点击查看',
      remark: '{{reason}}',
    },
  },
}, true, true)
import { AlertTriangle, CheckCircle2, Copy, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useHitlApproval } from '@/hooks/useHitlApproval'
import { useNotification } from '@/hooks/useNotification'
import { formatDate } from '@/lib/dateTime'
import type { HitlPayload } from '@/types'
import type { HitlApprovalResponse } from '@/lib/hitlApi'

interface HitlApprovalCardProps {
  hitl: HitlPayload
  onApproved?: (proposalId: string) => void | Promise<void>
  onRejected?: (proposalId: string) => void | Promise<void>
  className?: string
}

export default function HitlApprovalCard({ hitl, onApproved, onRejected, className }: HitlApprovalCardProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { approve, reject, refresh, loading } = useHitlApproval()
  const { showNotification } = useNotification()
  const [approval, setApproval] = useState<HitlApprovalResponse | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const fetchApproval = async () => {
    setLoadingDetail(true)
    setDetailError(null)
    try {
      const latest = await refresh(hitl.proposal_id)
      setApproval(latest)
    } catch (error) {
      console.error('Refresh HITL approval failed:', error)
      setDetailError(t('components.hitlApproval.loadDetailFailed'))
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    let mounted = true

    const load = async () => {
      setLoadingDetail(true)
      setDetailError(null)
      try {
        const latest = await refresh(hitl.proposal_id)
        if (mounted) {
          setApproval(latest)
        }
      } catch (error) {
        console.error('Refresh HITL approval failed:', error)
        if (mounted) {
          setDetailError(t('components.hitlApproval.loadingDetail'))
        }
      } finally {
        if (mounted) {
          setLoadingDetail(false)
        }
      }
    }

    void load()
    return () => {
      mounted = false
    }
  }, [hitl.proposal_id, hitl.type, refresh])

  const status = approval?.status || hitl.status || 'pending'
  const version = approval?.version || hitl.version
  const toolName = approval?.tool_name || hitl.tool_name || 'unknown'
  const riskLevel = approval?.risk_level || hitl.risk_level || '-'
  const summary =
    hitl.summary ||
    t('components.hitlApproval.agentWillUse', { tool: toolName })
  const title = hitl.title || t('components.hitlApproval.needsConfirmation')
  const expiresAt = approval?.expires_at || hitl.expires_at
  const reason = approval?.reason
  const toolArgs = approval?.tool_args || hitl.args_preview

  const isPending = status === 'pending'
  const isApproved = status === 'approved'
  const isRejected = status === 'rejected'
  const statusText =
    status === 'pending'
      ? t('components.hitlApproval.pending')
      : status === 'approved'
        ? t('components.hitlApproval.approved')
        : status === 'rejected'
          ? t('components.hitlApproval.rejected')
          : status

  const cardToneClass = isApproved
    ? 'border-success/30 bg-success/10 text-foreground'
    : isRejected
      ? 'border-destructive/30 bg-destructive/10 text-foreground'
      : 'border-warn/30 bg-warn/10 text-foreground'

  const toneTextClass = isApproved
    ? 'text-success'
    : isRejected
      ? 'text-destructive'
      : 'text-foreground'

  const statusBadgeClass = isApproved
    ? 'bg-success/15 text-success'
    : isRejected
      ? 'bg-destructive/15 text-destructive'
      : 'bg-warn/15 text-foreground'

  const onApprove = async () => {
    if (!version) {
      showNotification('error', t('components.hitlApproval.approveFailed'))
      return
    }

    try {
      const result = await approve(hitl.proposal_id, version)
      setApproval((prev) =>
        prev
          ? {
              ...prev,
              status: result.status,
              version: result.version,
            }
          : prev
      )
      if (result.status === 'approved' && result.needs_agent_resume !== false) {
        await onApproved?.(hitl.proposal_id)
      }
      void queryClient.invalidateQueries({ queryKey: ['hitlStatusMap'] })
      showNotification('success', t('components.hitlApproval.approvedSuccess'))
    } catch (error) {
      console.error('Approve HITL failed:', error)
      showNotification('error', t('components.hitlApproval.approveFailed'))
    }
  }

  const onReject = async () => {
    if (!version) {
      showNotification('error', t('components.hitlApproval.approveFailed'))
      return
    }

    try {
      const result = await reject(hitl.proposal_id, version)
      setApproval((prev) =>
        prev
          ? {
              ...prev,
              status: result.status,
              version: result.version,
            }
          : prev
      )
      if (result.status === 'rejected' && result.needs_agent_resume === false) {
        await onRejected?.(hitl.proposal_id)
      }
      void queryClient.invalidateQueries({ queryKey: ['hitlStatusMap'] })
      showNotification(
        'success',
        result.ack_message?.trim() || t('components.hitlApproval.rejectedSuccess')
      )
    } catch (error) {
      console.error('Reject HITL failed:', error)
      showNotification('error', t('components.hitlApproval.rejectFailed'))
    }
  }

  const onCopyProposalId = async () => {
    try {
      await navigator.clipboard.writeText(hitl.proposal_id)
      showNotification('success', t('components.hitlApproval.copied'))
    } catch (error) {
      console.error('Copy proposal id failed:', error)
      showNotification('error', t('components.hitlApproval.copyFailed'))
    }
  }

  const onCopyToolName = async () => {
    try {
      await navigator.clipboard.writeText(toolName)
      showNotification('success', t('components.hitlApproval.copied'))
    } catch (error) {
      console.error('Copy tool name failed:', error)
      showNotification('error', t('components.hitlApproval.copyFailed'))
    }
  }

  return (
    <div className={`${className || 'mt-2'} rounded-md border p-3 text-xs ${cardToneClass}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          {isApproved ? (
            <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
          ) : isRejected ? (
            <XCircle className="mt-0.5 size-4 shrink-0" />
          ) : (
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          )}
          <div className="font-medium">{title}</div>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusBadgeClass}`}>
          {statusText}
        </span>
      </div>

      <div className={`mt-2 text-sm font-semibold ${toneTextClass}`}>{summary}</div>

      {loadingDetail && <div className={`mt-1 ${toneTextClass}`}>{t('components.hitlApproval.loadingDetail')}</div>}
      {detailError && (
        <div className={`mt-1 flex items-center gap-2 ${toneTextClass}`}>
          <span>{detailError}</span>
          <Button size="sm" variant="outline" onClick={fetchApproval} disabled={loadingDetail}>
            {t('common.retry')}
          </Button>
        </div>
      )}

      <div className="mt-3 rounded-md border border-current/15 bg-black/5 p-2.5 dark:bg-white/5">
        <div className="grid grid-cols-[72px,1fr] gap-x-2 gap-y-1.5 text-[11px] leading-relaxed">
          <div className="opacity-70">{t('components.hitlApproval.tool')}</div>
          <div className="flex items-center gap-1.5">
            <span className="break-all">{toolName}</span>
            <Button
              size="sm"
              variant="ghost"
              className="h-5 px-1 text-[10px]"
              onClick={onCopyToolName}
            >
              <Copy className="mr-1 size-3" />
              {t('components.hitlApproval.copyToolName')}
            </Button>
          </div>

          <div className="opacity-70">{t('components.hitlApproval.riskLevel')}</div>
          <div>{riskLevel}</div>

          {expiresAt && (
            <>
              <div className="opacity-70">{t('components.hitlApproval.expiresAt')}</div>
              <div>{formatDate(expiresAt)}</div>
            </>
          )}

          {approval?.approved_at && (
            <>
              <div className="opacity-70">{t('components.hitlApproval.approvedAt')}</div>
              <div>{formatDate(approval.approved_at)}</div>
            </>
          )}

          {approval?.rejected_at && (
            <>
              <div className="opacity-70">{t('components.hitlApproval.rejectedAt')}</div>
              <div>{formatDate(approval.rejected_at)}</div>
            </>
          )}

          <div className="opacity-70">{t('components.hitlApproval.copyProposalId')}</div>
          <div className="flex items-center gap-1.5">
            <span className="break-all font-mono text-[10px]">{hitl.proposal_id}</span>
            <Button
              size="sm"
              variant="ghost"
              className="h-5 px-1 text-[10px]"
              onClick={onCopyProposalId}
            >
              <Copy className="mr-1 size-3" />
              {t('components.hitlApproval.copyProposalId')}
            </Button>
          </div>

          {toolArgs && (
            <>
              <div className="opacity-70">{t('components.hitlApproval.callParams')}</div>
              <details>
                <summary className={`cursor-pointer ${toneTextClass}`}>{t('components.hitlApproval.expandToView')}</summary>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-black/5 p-2 text-[11px] text-current dark:bg-white/10">
                  {JSON.stringify(toolArgs, null, 2)}
                </pre>
              </details>
            </>
          )}
        </div>
      </div>

      {reason && <div className={`mt-1 ${toneTextClass}`}>{t('components.hitlApproval.remark', { reason })}</div>}

      {isPending && (
        <div className="mt-3 flex gap-2">
          <Button size="sm" onClick={onApprove} disabled={loading || !version}>
            {t('components.hitlApproval.approve')}
          </Button>
          <Button size="sm" variant="outline" onClick={onReject} disabled={loading || !version}>
            {t('components.hitlApproval.reject')}
          </Button>
        </div>
      )}
    </div>
  )
}
