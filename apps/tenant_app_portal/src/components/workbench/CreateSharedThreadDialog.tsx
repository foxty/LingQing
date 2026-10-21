import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import TenantUserCombobox from '@/components/TenantUserCombobox'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { getApiErrorMessage } from '@/lib/api'
import { createConversation } from '@/lib/threadsApi'

interface AgentOption {
  id: number
  name: string
}

interface CreateSharedThreadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  agents: AgentOption[]
  defaultAgentId?: number
  onCreated: (threadId: string) => void
}

export default function CreateSharedThreadDialog({
  open,
  onOpenChange,
  agents,
  defaultAgentId,
  onCreated,
}: CreateSharedThreadDialogProps) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { showError } = useNotification()
  const [title, setTitle] = useState('')
  const [selected, setSelected] = useState<Set<number>>(() => {
    const initial = new Set<number>()
    if (defaultAgentId != null) initial.add(defaultAgentId)
    else if (agents[0]) initial.add(agents[0].id)
    return initial
  })
  const [memberLabels, setMemberLabels] = useState<Map<number, string>>(() => new Map())
  const [memberPickerOpen, setMemberPickerOpen] = useState(false)
  const [pickerUserId, setPickerUserId] = useState<number | null>(null)
  const [pickerUsername, setPickerUsername] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const memberUserIds = useMemo(() => [...memberLabels.keys()], [memberLabels])

  const excludeUserIds = useMemo(() => {
    const ids = [...memberUserIds]
    if (user?.id != null) {
      ids.push(user.id)
    }
    return ids
  }, [memberUserIds, user?.id])

  const toggleAgent = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const removeMember = (userId: number) => {
    setMemberLabels((prev) => {
      const next = new Map(prev)
      next.delete(userId)
      return next
    })
  }

  const handleCreate = async () => {
    const agentIds = [...selected]
    if (agentIds.length === 0) return
    setSubmitting(true)
    try {
      const thread = await createConversation({
        title: title.trim() || null,
        agent_ids: agentIds,
        member_user_ids: memberUserIds.length > 0 ? memberUserIds : undefined,
      })
      onCreated(thread.id)
      onOpenChange(false)
      setTitle('')
      setMemberLabels(new Map())
    } catch (err) {
      showError(getApiErrorMessage(err, t('workbench.createConversationFailed')))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('workbench.createConversationTitle')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="shared-thread-title">{t('workbench.sharedThreadTitleLabel')}</Label>
            <Input
              id="shared-thread-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('workbench.sharedThreadTitlePlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label>{t('workbench.sharedThreadAgentsLabel')}</Label>
            <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border border-border p-2">
              {agents.map((agent) => (
                <label key={agent.id} className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={selected.has(agent.id)}
                    onCheckedChange={() => toggleAgent(agent.id)}
                  />
                  <span>{agent.name}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <Label>{t('workbench.conversationMembersLabel')}</Label>
            {memberLabels.size > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {[...memberLabels.entries()].map(([userId, username]) => (
                  <Badge key={userId} variant="secondary" className="gap-1 pr-1">
                    {username}
                    <button
                      type="button"
                      className="rounded-sm p-0.5 hover:bg-muted"
                      aria-label={`Remove ${username}`}
                      onClick={() => removeMember(userId)}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">{t('workbench.conversationMembersHint')}</p>
            )}
            <TenantUserCombobox
              open={memberPickerOpen}
              onOpenChange={setMemberPickerOpen}
              placeholder={t('workbench.addMemberPlaceholder')}
              searchPlaceholder={t('components.shareDialog.searchPlaceholder')}
              searchingLabel={t('components.shareDialog.searching')}
              emptyLabel={t('components.shareDialog.noUsersFound')}
              excludeUserIds={excludeUserIds}
              selectedUserId={pickerUserId}
              selectedUsername={pickerUsername}
              onSelect={(row) => {
                setMemberLabels((prev) => {
                  const next = new Map(prev)
                  next.set(row.user_id, row.username)
                  return next
                })
                setPickerUserId(null)
                setPickerUsername('')
              }}
              onSearchError={(message) => showError(message)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleCreate} disabled={submitting || selected.size === 0}>
            {t('workbench.createConversationConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
