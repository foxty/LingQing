import { Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import AgentFeedbackPanel from '@/components/agents/AgentFeedbackPanel'
import { useAuth } from '@/hooks/useAuth'
import { PERMISSIONS } from '@/lib/permissionRules'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    agentFeedback: {
      pageTitle: 'Agent Feedback',
      description: 'Review thumbs up/down ratings from portal and Slack conversations.',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    agentFeedback: {
      pageTitle: '智能体反馈',
      description: '查看来自门户和 Slack 对话的点赞/点踩评价。',
    },
  },
  true,
  true
)

export default function AgentFeedbackPage() {
  const { t } = useTranslation()
  const { hasAny } = useAuth()
  const canAccess = hasAny([PERMISSIONS.TENANT_ADMIN, PERMISSIONS.AGENTS_MANAGE])

  if (!canAccess) {
    return <Navigate to="/agents" replace />
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t('agentFeedback.pageTitle')}</h1>
        <p className="text-sm text-muted-foreground">{t('agentFeedback.description')}</p>
      </div>
      <AgentFeedbackPanel />
    </div>
  )
}
