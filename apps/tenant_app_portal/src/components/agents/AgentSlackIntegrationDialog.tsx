import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { CatalogAgent } from '@/lib/agentsApi'
import AgentSlackIntegrationSection from '@/components/agents/AgentSlackIntegrationSection'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    agents: {
      slackIntegration: {
        dialogTitle: 'Slack — {{name}}',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    agents: {
      slackIntegration: {
        dialogTitle: 'Slack — {{name}}',
      },
    },
  },
  true,
  true
)

type Props = {
  agent: CatalogAgent | null
  canManage: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  onChanged?: () => void
}

export default function AgentSlackIntegrationDialog({
  agent,
  canManage,
  open,
  onOpenChange,
  onChanged,
}: Props) {
  const { t } = useTranslation()

  if (!agent) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('agents.slackIntegration.dialogTitle', { name: agent.name })}</DialogTitle>
        </DialogHeader>
        <AgentSlackIntegrationSection
          agentId={agent.id}
          canManage={canManage}
          embedded
          onChanged={onChanged}
        />
      </DialogContent>
    </Dialog>
  )
}
