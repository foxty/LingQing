import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Trash2, UserRound } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import TenantUserCombobox from '@/components/TenantUserCombobox'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useAgents } from '@/hooks/useAgents'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { getApiErrorMessage } from '@/lib/api'
import { MEMBER_ROLE_OWNER } from '@/lib/threadMemberRoles'
import {
  addThreadAgent,
  addThreadMember,
  listThreadAgentRoster,
  listThreadMembers,
  removeThreadAgent,
  removeThreadMember,
  setThreadPrimaryAgent,
  updateThreadMemberRole,
  type ThreadUserMemberRole,
} from '@/lib/threadsApi'

type RemoveTarget =
  | { kind: 'user'; id: number; label: string }
  | { kind: 'agent'; id: number; label: string }

type UserRow = {
  key: string
  kind: 'user'
  id: number
  label: string
  role: ThreadUserMemberRole
}

type AgentRow = {
  key: string
  kind: 'agent'
  id: number
  label: string
  isPrimary: boolean
}

type ParticipantRow = UserRow | AgentRow

interface SharedThreadParticipantsSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  threadId: string
  primaryAgentId?: number
  isOwner: boolean
}

const USER_ROLES: ThreadUserMemberRole[] = ['owner', 'member', 'viewer']
const LIST_MAX_HEIGHT = 'max-h-36'

export default function SharedThreadParticipantsSheet({
  open,
  onOpenChange,
  threadId,
  primaryAgentId,
  isOwner,
}: SharedThreadParticipantsSheetProps) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { showError } = useNotification()
  const queryClient = useQueryClient()
  const { data: catalogAgents = [] } = useAgents()

  const [userPickerOpen, setUserPickerOpen] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [selectedUsername, setSelectedUsername] = useState('')
  const [addingUser, setAddingUser] = useState(false)
  const [addAgentId, setAddAgentId] = useState('')
  const [addingAgent, setAddingAgent] = useState(false)
  const [roleUpdatingKey, setRoleUpdatingKey] = useState<string | null>(null)
  const [removeTarget, setRemoveTarget] = useState<RemoveTarget | null>(null)
  const [removing, setRemoving] = useState(false)

  const { data: members = [], isLoading: membersLoading } = useQuery({
    queryKey: ['threadMembers', threadId],
    queryFn: () => listThreadMembers(threadId),
    enabled: open && Boolean(threadId),
  })

  const { data: agentRoster = [], isLoading: rosterLoading } = useQuery({
    queryKey: ['threadRoster', threadId],
    queryFn: () => listThreadAgentRoster(threadId),
    enabled: open && Boolean(threadId),
  })

  const agentNameById = useMemo(
    () => new Map(catalogAgents.map((agent) => [agent.id, agent.name])),
    [catalogAgents]
  )

  const rosterAgentIds = useMemo(() => new Set(agentRoster.map((entry) => entry.agent_id)), [agentRoster])

  const addableAgents = useMemo(
    () => catalogAgents.filter((agent) => !rosterAgentIds.has(agent.id)),
    [catalogAgents, rosterAgentIds]
  )

  const excludeUserIds = useMemo(() => members.map((m) => m.user_id), [members])

  const userRows: UserRow[] = useMemo(
    () =>
      members.map((m) => ({
        key: `user-${m.user_id}`,
        kind: 'user' as const,
        id: m.user_id,
        label: m.username ?? `User ${m.user_id}`,
        role: (USER_ROLES.includes(m.role as ThreadUserMemberRole)
          ? m.role
          : 'member') as ThreadUserMemberRole,
      })),
    [members]
  )

  const agentRows: AgentRow[] = useMemo(
    () =>
      agentRoster.map((entry) => ({
        key: `agent-${entry.agent_id}`,
        kind: 'agent' as const,
        id: entry.agent_id,
        label:
          entry.display_alias ||
          agentNameById.get(entry.agent_id) ||
          `Agent ${entry.agent_id}`,
        isPrimary: primaryAgentId != null && entry.agent_id === primaryAgentId,
      })),
    [agentNameById, agentRoster, primaryAgentId]
  )

  const invalidateParticipants = async () => {
    await queryClient.invalidateQueries({ queryKey: ['threadMembers', threadId] })
    await queryClient.invalidateQueries({ queryKey: ['threadRoster', threadId] })
    await queryClient.invalidateQueries({ queryKey: ['threads'] })
    await queryClient.invalidateQueries({ queryKey: ['thread', threadId] })
  }

  const handleAddUser = async () => {
    if (selectedUserId == null) return
    setAddingUser(true)
    try {
      await addThreadMember(threadId, selectedUserId)
      await invalidateParticipants()
      setSelectedUserId(null)
      setSelectedUsername('')
    } catch (err) {
      showError(getApiErrorMessage(err, t('workbench.addMemberFailed')))
    } finally {
      setAddingUser(false)
    }
  }

  const handleAddAgent = async () => {
    const agentId = Number(addAgentId)
    if (!Number.isFinite(agentId)) return
    setAddingAgent(true)
    try {
      await addThreadAgent(threadId, agentId)
      await invalidateParticipants()
      setAddAgentId('')
    } catch (err) {
      showError(getApiErrorMessage(err, t('workbench.addAgentFailed')))
    } finally {
      setAddingAgent(false)
    }
  }

  const handleUserRoleChange = async (userId: number, role: ThreadUserMemberRole, rowKey: string) => {
    setRoleUpdatingKey(rowKey)
    try {
      await updateThreadMemberRole(threadId, userId, role)
      await invalidateParticipants()
    } catch (err) {
      showError(getApiErrorMessage(err, t('workbench.updateParticipantRoleFailed')))
    } finally {
      setRoleUpdatingKey(null)
    }
  }

  const handleAgentRoleChange = async (agentId: number, value: string, rowKey: string) => {
    if (value !== 'primary') return
    setRoleUpdatingKey(rowKey)
    try {
      await setThreadPrimaryAgent(threadId, agentId)
      await invalidateParticipants()
    } catch (err) {
      showError(getApiErrorMessage(err, t('workbench.updateParticipantRoleFailed')))
    } finally {
      setRoleUpdatingKey(null)
    }
  }

  const confirmRemove = async (target: RemoveTarget) => {
    setRemoving(true)
    try {
      if (target.kind === 'user') {
        await removeThreadMember(threadId, target.id)
      } else {
        await removeThreadAgent(threadId, target.id)
      }
      await invalidateParticipants()
      setRemoveTarget(null)
    } catch (err) {
      showError(getApiErrorMessage(err, t('workbench.removeParticipantFailed')))
    } finally {
      setRemoving(false)
    }
  }

  const loading = membersLoading || rosterLoading

  const canEditRow = (row: ParticipantRow) => {
    if (!isOwner) return false
    if (row.kind === 'user' && row.id === user?.id) return false
    return true
  }

  const canDeleteRow = (row: ParticipantRow) => {
    if (!canEditRow(row)) return false
    if (row.kind === 'user') {
      return row.role !== MEMBER_ROLE_OWNER
    }
    return agentRoster.length > 1
  }

  const renderRow = (row: ParticipantRow) => {
    const editable = canEditRow(row)
    const deletable = canDeleteRow(row)
    return (
      <li key={row.key} className="flex items-center gap-1.5 py-1.5 first:pt-0 last:pb-0">
        {row.kind === 'user' ? (
          <UserRound className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        )}
        <span className="min-w-0 flex-1 truncate text-sm">{row.label}</span>
        <Select
          value={row.kind === 'user' ? row.role : row.isPrimary ? 'primary' : 'participant'}
          onValueChange={(value) => {
            if (row.kind === 'user') {
              void handleUserRoleChange(row.id, value as ThreadUserMemberRole, row.key)
            } else {
              void handleAgentRoleChange(row.id, value, row.key)
            }
          }}
          disabled={!editable || roleUpdatingKey === row.key}
        >
          <SelectTrigger className="h-7 w-[6.75rem] shrink-0 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {row.kind === 'user'
              ? USER_ROLES.map((role) => (
                  <SelectItem key={role} value={role}>
                    {t(`workbench.participantRole.${role}`)}
                  </SelectItem>
                ))
              : (
                <>
                  <SelectItem value="primary">{t('workbench.participantRole.primary')}</SelectItem>
                  <SelectItem value="participant" disabled={row.isPrimary}>
                    {t('workbench.participantRole.participant')}
                  </SelectItem>
                </>
              )}
          </SelectContent>
        </Select>
        {deletable ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
            aria-label={t('workbench.removeParticipant')}
            onClick={() =>
              setRemoveTarget({
                kind: row.kind,
                id: row.id,
                label: row.label,
              })
            }
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        ) : (
          <span className="h-7 w-7 shrink-0" aria-hidden />
        )}
      </li>
    )
  }

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="flex w-full flex-col gap-0 sm:max-w-md">
          <SheetHeader className="shrink-0 space-y-1 pb-2">
            <SheetTitle className="text-base">{t('workbench.conversationParticipantsTitle')}</SheetTitle>
            <SheetDescription className="text-xs">{t('workbench.conversationParticipantsHint')}</SheetDescription>
          </SheetHeader>

          {loading ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden pb-2">
              <section className="flex shrink-0 flex-col gap-1">
                <h3 className="text-xs font-medium text-muted-foreground">
                  {t('workbench.participantsPeopleHeading')}
                </h3>
                <ul className={`${LIST_MAX_HEIGHT} divide-y divide-dashed divide-border overflow-y-auto`}>
                  {userRows.map((row) => renderRow(row))}
                </ul>
                {isOwner ? (
                  <div className="flex gap-1.5 pt-0.5">
                    <div className="min-w-0 flex-1">
                      <TenantUserCombobox
                        open={userPickerOpen}
                        onOpenChange={setUserPickerOpen}
                        placeholder={t('workbench.addMemberPlaceholder')}
                        searchPlaceholder={t('components.shareDialog.searchPlaceholder')}
                        searchingLabel={t('components.shareDialog.searching')}
                        emptyLabel={t('components.shareDialog.noUsersFound')}
                        excludeUserIds={excludeUserIds}
                        selectedUserId={selectedUserId}
                        selectedUsername={selectedUsername}
                        onSelect={(entry) => {
                          setSelectedUserId(entry.user_id)
                          setSelectedUsername(entry.username)
                        }}
                        onSearchError={(message) => showError(message)}
                      />
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      className="h-9 shrink-0 px-2.5"
                      disabled={selectedUserId == null || addingUser}
                      onClick={handleAddUser}
                    >
                      {t('workbench.addMember')}
                    </Button>
                  </div>
                ) : null}
              </section>

              <section className="flex min-h-0 shrink-0 flex-col gap-1 border-t border-border pt-3">
                <h3 className="text-xs font-medium text-muted-foreground">
                  {t('workbench.participantsAgentsHeading')}
                </h3>
                <ul className={`${LIST_MAX_HEIGHT} divide-y divide-dashed divide-border overflow-y-auto`}>
                  {agentRows.map((row) => renderRow(row))}
                </ul>
                {isOwner && addableAgents.length > 0 ? (
                  <div className="flex gap-1.5 pt-0.5">
                    <Select value={addAgentId} onValueChange={setAddAgentId}>
                      <SelectTrigger className="h-9 flex-1">
                        <SelectValue placeholder={t('workbench.addAgentPlaceholder')} />
                      </SelectTrigger>
                      <SelectContent>
                        {addableAgents.map((agent) => (
                          <SelectItem key={agent.id} value={String(agent.id)}>
                            {agent.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      size="sm"
                      className="h-9 shrink-0 px-2.5"
                      disabled={!addAgentId || addingAgent}
                      onClick={handleAddAgent}
                    >
                      {t('workbench.addAgent')}
                    </Button>
                  </div>
                ) : null}
              </section>
            </div>
          )}
        </SheetContent>
      </Sheet>

      <ConfirmationDialog
        open={removeTarget != null}
        item={removeTarget}
        isLoading={removing}
        title={t('workbench.confirmRemoveParticipantTitle')}
        description={(target) =>
          t('workbench.confirmRemoveParticipantBody', { name: target.label })
        }
        confirmText={t('workbench.removeParticipant')}
        isDangerous
        onConfirm={confirmRemove}
        onCancel={() => setRemoveTarget(null)}
      />
    </>
  )
}
