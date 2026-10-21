import ArtifactsPanel from '@/components/artifacts/ArtifactsPanel'
import ChatArea from '@/components/chat/ChatArea'
import '@/components/chat/workbenchChatI18n'
import CreateSharedThreadDialog from '@/components/workbench/CreateSharedThreadDialog'
import SharedThreadParticipantsSheet from '@/components/workbench/SharedThreadParticipantsSheet'
import WorkbenchThreadChrome from '@/components/workbench/WorkbenchThreadChrome'
import { useArtifacts } from '@/hooks/useArtifacts'
import { useAuth } from '@/hooks/useAuth'
import { useThread, useThreads } from '@/hooks/useThreads'
import { useUserPreferences } from '@/hooks/useUserPreferences'
import { useAgentThinkingEffortControl } from '@/hooks/useAgentThinkingEffortControl'
import { useWorkbenchChat } from '@/hooks/useWorkbenchChat'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useNotification } from '@/hooks/useNotification'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listThreadAgentRoster, listThreadMembers } from '@/lib/threadsApi'
import { isSharedThreadsUiEnabled } from '@/lib/sharedThreadsFeature'
import { workbenchThreadPath } from '@/lib/workbenchThreadPaths'
import type { ChatThread } from '@/types'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useAgents } from '@/hooks/useAgents'
import { SYSTEM_AGENT_ONE_ID } from '@/lib/agentsApi'

i18n.addResourceBundle('en', 'translation', {
  workbench: {
    createThreadFailed: 'Failed to create chat thread. Please try again.',
    streamDisconnected:
      'Connection lost while the agent was working. Waiting for the response…',
    streamFailed: 'The agent could not finish this turn. Please try again.',
    authRequired: 'Your session expired. Sign in again and retry.',
    openArtifacts: 'Open artifacts',
    artifactReady: 'New artifact ready',
    viewArtifact: 'View',
    untitledThread: 'Conversation',
    selectAgent: 'Agent',
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  workbench: {
    createThreadFailed: '创建对话失败，请重试。',
    streamDisconnected: '连接中断，智能体仍在后台处理，正在等待回复…',
    streamFailed: '智能体未能完成本轮对话，请重试。',
    authRequired: '登录已过期，请重新登录后再试。',
    openArtifacts: '打开产物',
    artifactReady: '新产物已就绪',
    viewArtifact: '查看',
    untitledThread: '对话',
    selectAgent: '智能体',
  },
}, true, true)

export default function WorkbenchPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { threadId: threadIdParam } = useParams<{ threadId?: string }>()
  const { data: agents = [], isSuccess: agentsLoaded, isError: agentsFailed } = useAgents()
  const { preferences, updatePreferences } = useUserPreferences()
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState<number>(
    Number(searchParams.get('agent')) || preferences.lastAgentId || SYSTEM_AGENT_ONE_ID
  )
  const [artifactsPanelVisible, setArtifactsPanelVisible] = useState(false)
  const [conversationCreateOpen, setConversationCreateOpen] = useState(false)
  const [membersPanelOpen, setMembersPanelOpen] = useState(false)
  const sharedUiEnabled = isSharedThreadsUiEnabled()
  const [departedThreadId, setDepartedThreadId] = useState<string | null>(null)
  const initialMessageSentRef = useRef(false)
  const artifactsPanelVisibleRef = useRef(false)
  const artifactsPanelDismissedForThreadRef = useRef(false)
  const { showInfoWithAction } = useNotification()
  const { data: routeThread, isFetched: routeThreadFetched } = useThread(
    threadIdParam,
    threadIdParam !== departedThreadId
  )

  const accessibleAgentIds = useMemo(() => new Set(agents.map((agent) => agent.id)), [agents])
  const fallbackAgentId = useMemo(() => {
    if (accessibleAgentIds.has(preferences.lastAgentId)) {
      return preferences.lastAgentId
    }
    return agents[0]?.id ?? SYSTEM_AGENT_ONE_ID
  }, [accessibleAgentIds, agents, preferences.lastAgentId])
  const {
    threads,
    isLoading: threadsLoading,
    isFetched: threadsFetched,
    createThread,
    deleteThread,
    updateThreadTitle,
  } = useThreads()

  const agentId = selectedAgentId
  const agentOptions = useMemo(
    () =>
      agents.length > 0
        ? agents
        : [{ id: SYSTEM_AGENT_ONE_ID, name: 'Agent One', example_questions: [] as string[] }],
    [agents]
  )
  const {
    artifacts,
    selectedArtifact,
    artifactsPanelWidth,
    loading: artifactsLoading,
    reloadArtifacts,
    selectArtifact,
    clearSelection,
    updatePanelWidth,
    restoreSelectionFromStorage,
  } = useArtifacts(currentThreadId)

  useEffect(() => {
    artifactsPanelVisibleRef.current = artifactsPanelVisible
  }, [artifactsPanelVisible])

  useEffect(() => {
    artifactsPanelDismissedForThreadRef.current = false
    setArtifactsPanelVisible(false)
    setMembersPanelOpen(false)
  }, [currentThreadId])

  const setArtifactsPanelVisibleFromChat = useCallback((visible: boolean) => {
    if (visible) {
      artifactsPanelDismissedForThreadRef.current = false
    }
    setArtifactsPanelVisible(visible)
  }, [])

  const handleOpenArtifactsPanel = useCallback(() => {
    artifactsPanelDismissedForThreadRef.current = false
    setArtifactsPanelVisible(true)
    restoreSelectionFromStorage()
  }, [restoreSelectionFromStorage])

  const handleCollapseArtifactsPanel = useCallback(() => {
    artifactsPanelDismissedForThreadRef.current = true
    setArtifactsPanelVisible(false)
  }, [])

  const queryAgentId = Number(searchParams.get('agent'))
  const hasQueryAgent = Boolean(searchParams.get('agent')) && Number.isFinite(queryAgentId)
  const wantsNewConversation = searchParams.get('new') === '1'

  const accessibleThreads = useMemo(() => {
    const allowed = agentsLoaded && !agentsFailed ? accessibleAgentIds : null
    return [...threads]
      .filter(
        (thread) =>
          allowed == null || thread.threadKind === 'shared' || allowed.has(thread.agentId)
      )
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
  }, [accessibleAgentIds, agentsFailed, agentsLoaded, threads])

  const isSharedThread = useMemo(() => {
    if (!isSharedThreadsUiEnabled()) return false
    if (routeThread?.thread_kind === 'shared') return true
    const fromList = accessibleThreads.find((t) => t.id === currentThreadId)
    return fromList?.threadKind === 'shared'
  }, [accessibleThreads, currentThreadId, routeThread?.thread_kind])

  const { data: threadMembers = [] } = useQuery({
    queryKey: ['threadMembers', currentThreadId],
    queryFn: () => listThreadMembers(currentThreadId!),
    enabled: Boolean(currentThreadId) && Boolean(user?.id),
  })

  const userNameById = useMemo(() => {
    const map = new Map<number, string>()
    if (user?.id && user.username) {
      map.set(user.id, user.username)
    }
    for (const m of threadMembers) {
      if (m.username) {
        map.set(m.user_id, m.username)
      }
    }
    return map
  }, [threadMembers, user?.id, user?.username])

  const { data: threadRoster = [] } = useQuery({
    queryKey: ['threadRoster', currentThreadId],
    queryFn: () => listThreadAgentRoster(currentThreadId!),
    enabled: Boolean(currentThreadId),
  })

  const agentNameById = useMemo(() => {
    const map = new Map(agents.map((a) => [a.id, a.name]))
    for (const entry of threadRoster) {
      const label =
        entry.display_alias || map.get(entry.agent_id) || `#${entry.agent_id}`
      map.set(entry.agent_id, label)
    }
    return map
  }, [agents, threadRoster])

  const rosterAgentOptions = useMemo(
    () =>
      threadRoster.map((entry) => ({
        id: entry.agent_id,
        label:
          entry.display_alias ||
          agents.find((a) => a.id === entry.agent_id)?.name ||
          `#${entry.agent_id}`,
      })),
    [agents, threadRoster]
  )

  const defaultSharedAgentId = rosterAgentOptions[0]?.id ?? selectedAgentId

  const threadMemberUserIds = useMemo(
    () => threadMembers.map((m) => m.user_id),
    [threadMembers]
  )

  const threadMemberUserLabels = useMemo(
    () =>
      threadMembers
        .filter((m) => m.username)
        .map((m) => ({ id: m.user_id, label: m.username! })),
    [threadMembers]
  )

  const {
    displayMessages,
    historyLoading,
    threadLoadError,
    hasMore,
    isLoadingMore,
    handleLoadMore,
    showWorkingIndicator,
    isStreaming,
    streamingContent,
    streamingToolCalls,
    streamingAgentId,
    handleSendMessage,
    handleHitlApprovedContinue,
    handleHitlRejected,
  } = useWorkbenchChat({
    agentId,
    chatAgentId: isSharedThread ? defaultSharedAgentId : selectedAgentId,
    threadId: currentThreadId,
    createThread,
    navigate,
    updateThreadTitle,
    reloadArtifacts,
    selectArtifact,
    setArtifactsPanelVisible: setArtifactsPanelVisibleFromChat,
    artifactsAutoOpen: preferences.artifactsAutoOpen,
    thinkingEffort: preferences.thinkingEffort,
    isArtifactsPanelDismissedForThread: () => artifactsPanelDismissedForThreadRef.current,
    isArtifactsPanelVisible: () => artifactsPanelVisibleRef.current,
    onNewArtifactsWhilePanelClosed: (newArtifacts) => {
      const primary = newArtifacts[0]
      if (!primary) return
      showInfoWithAction(t('workbench.artifactReady'), t('workbench.viewArtifact'), () => {
        artifactsPanelDismissedForThreadRef.current = false
        setArtifactsPanelVisible(true)
        selectArtifact(primary)
      })
    },
  })

  const sortedThreads = useMemo(() => {
    if (!sharedUiEnabled) {
      return accessibleThreads.filter((thread) => thread.agentId === selectedAgentId)
    }
    return accessibleThreads.filter(
      (thread) => thread.threadKind === 'shared' || thread.agentId === selectedAgentId
    )
  }, [accessibleThreads, selectedAgentId, sharedUiEnabled])

  const resolveThreadPath = useCallback(
    (thread: Pick<ChatThread, 'id' | 'threadKind'>) => workbenchThreadPath(thread),
    []
  )

  const latestThread = accessibleThreads[0] || null
  const currentThread = sortedThreads.find((thread) => thread.id === currentThreadId) || null
  const canManageMembers = Boolean(currentThread && user && currentThread.userId === user.id)
  const showMembersControl = Boolean(sharedUiEnabled && currentThreadId)
  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId)
  const {
    thinkingEffortControlEnabled,
    thinkingEffortOptions,
    defaultThinkingEffortValue,
    agentModelId,
    agentProfileName,
  } = useAgentThinkingEffortControl(selectedAgentId)

  useEffect(() => {
    if (!defaultThinkingEffortValue) {
      return
    }
    const allowed = new Set(thinkingEffortOptions.map((option) => option.value))
    const current = preferences.thinkingEffort
    if (!current || !allowed.has(current)) {
      updatePreferences({ thinkingEffort: defaultThinkingEffortValue })
    }
  }, [
    defaultThinkingEffortValue,
    preferences.thinkingEffort,
    thinkingEffortOptions,
    updatePreferences,
  ])
  const agentAccessRevoked = useMemo(() => {
    if (!agentsLoaded || agentsFailed) return false
    const gateAgentId = isSharedThread ? defaultSharedAgentId : selectedAgentId
    return gateAgentId > 0 && !agents.some((agent) => agent.id === gateAgentId)
  }, [agents, agentsFailed, agentsLoaded, defaultSharedAgentId, isSharedThread, selectedAgentId])
  const sessionTitle = currentThread?.title || t('workbench.untitledThread')
  const isArtifactSplit = artifacts.length > 0 && artifactsPanelVisible

  useEffect(() => {
    if (threadIdParam && threadIdParam !== departedThreadId) {
      setCurrentThreadId(threadIdParam)
      return
    }
    setCurrentThreadId(null)
  }, [departedThreadId, threadIdParam])

  useEffect(() => {
    if (departedThreadId && threadIdParam !== departedThreadId) {
      setDepartedThreadId(null)
    }
  }, [departedThreadId, threadIdParam])

  useEffect(() => {
    if (!agentsLoaded || agentsFailed) {
      return
    }
    if (hasQueryAgent) {
      if (!accessibleAgentIds.has(queryAgentId)) {
        setSelectedAgentId(fallbackAgentId)
        updatePreferences({ lastAgentId: fallbackAgentId })
        navigate('/workbench', { replace: true })
        return
      }
      if (queryAgentId !== selectedAgentId) {
        setSelectedAgentId(queryAgentId)
        updatePreferences({ lastAgentId: queryAgentId })
      }
      return
    }
    if (threadIdParam) {
      if (threadIdParam === departedThreadId) {
        return
      }
      if (!routeThreadFetched) {
        return
      }
      if (!routeThread) {
        navigate(`/workbench?agent=${selectedAgentId}`, { replace: true })
        return
      }
      const routeIsShared = routeThread.thread_kind === 'shared'
      if (routeIsShared || accessibleAgentIds.has(routeThread.agent_id)) {
        if (!routeIsShared && routeThread.agent_id !== selectedAgentId) {
          setSelectedAgentId(routeThread.agent_id)
          updatePreferences({ lastAgentId: routeThread.agent_id })
        }
        return
      }
      setSelectedAgentId(fallbackAgentId)
      updatePreferences({ lastAgentId: fallbackAgentId })
      navigate(`/workbench?agent=${fallbackAgentId}`, { replace: true })
      return
    }
    if (!accessibleAgentIds.has(selectedAgentId)) {
      setSelectedAgentId(fallbackAgentId)
      updatePreferences({ lastAgentId: fallbackAgentId })
    }
  }, [
    accessibleAgentIds,
    agentsFailed,
    agentsLoaded,
    departedThreadId,
    fallbackAgentId,
    hasQueryAgent,
    navigate,
    queryAgentId,
    routeThread,
    routeThreadFetched,
    selectedAgentId,
    threadIdParam,
    updatePreferences,
  ])

  useEffect(() => {
    if (threadIdParam || threadsLoading || !threadsFetched) {
      return
    }
    if (!agentsLoaded && !agentsFailed) {
      return
    }
    if (hasQueryAgent && !wantsNewConversation) {
      const latestForAgent = sortedThreads[0]
      if (latestForAgent) {
        navigate(resolveThreadPath(latestForAgent), { replace: true })
      }
      return
    }
    if (latestThread) {
      navigate(resolveThreadPath(latestThread), { replace: true })
    }
  }, [
    agentsFailed,
    agentsLoaded,
    hasQueryAgent,
    latestThread,
    navigate,
    resolveThreadPath,
    sortedThreads,
    threadIdParam,
    threadsFetched,
    threadsLoading,
    wantsNewConversation,
  ])

  useEffect(() => {
    const state = location.state as { initialMessage?: string } | null
    if (state?.initialMessage && threadIdParam && !initialMessageSentRef.current && user) {
      initialMessageSentRef.current = true
      window.history.replaceState({}, document.title)
      handleSendMessage(state.initialMessage, [])
    }
  }, [location.state, threadIdParam, user, handleSendMessage])

  const handleNewConversation = useCallback(() => {
    if (sharedUiEnabled) {
      setConversationCreateOpen(true)
      return
    }
    void (async () => {
      try {
        const newThread = await createThread({ agentId: selectedAgentId })
        updatePreferences({ lastAgentId: selectedAgentId })
        navigate(workbenchThreadPath({ id: newThread.id, threadKind: 'personal' }))
      } catch (error) {
        console.error('Failed to create thread:', error)
      }
    })()
  }, [createThread, navigate, selectedAgentId, sharedUiEnabled, updatePreferences])

  const handleThreadSelect = useCallback(
    (threadId: string) => {
      const thread = accessibleThreads.find((t) => t.id === threadId)
      if (thread) {
        navigate(resolveThreadPath(thread))
        return
      }
      navigate(`/workbench/${threadId}`)
    },
    [accessibleThreads, navigate, resolveThreadPath]
  )

  const handleDeleteThread = useCallback(
    async (threadId: string) => {
      const remainingThreads = sortedThreads.filter((thread) => thread.id !== threadId)
      if (threadId === currentThreadId || threadId === threadIdParam) {
        setDepartedThreadId(threadId)
        setCurrentThreadId(null)
        if (remainingThreads.length > 0) {
          navigate(resolveThreadPath(remainingThreads[0]), { replace: true })
        } else {
          navigate(`/workbench?agent=${selectedAgentId}`, { replace: true })
        }
      }
      await deleteThread(threadId)
    },
    [currentThreadId, deleteThread, navigate, resolveThreadPath, selectedAgentId, sortedThreads, threadIdParam]
  )

  return (
    <div id="workbench" className="flex h-full overflow-hidden">
      <div className="flex-1 flex overflow-hidden">
        <div className={`flex flex-col overflow-hidden flex-1 ${isArtifactSplit ? 'min-w-[16rem]' : ''}`}>
          <WorkbenchThreadChrome
            sharedUiEnabled={sharedUiEnabled}
            selectedAgentId={selectedAgentId}
            agentOptions={agentOptions.map((a) => ({ id: a.id, name: a.name }))}
            onAgentChange={(nextId) => {
              setSelectedAgentId(nextId)
              updatePreferences({ lastAgentId: nextId })
              if (threadIdParam) {
                navigate(`/workbench/${threadIdParam}?agent=${nextId}`)
              } else {
                navigate(`/workbench?agent=${nextId}`)
              }
            }}
            threads={sortedThreads}
            currentThreadId={currentThreadId}
            threadsLoading={threadsLoading}
            isSharedThread={isSharedThread}
            showMembersButton={showMembersControl}
            participantCount={threadMembers.length + threadRoster.length}
            onSelectThread={handleThreadSelect}
            onCreateConversation={handleNewConversation}
            onDeleteThread={handleDeleteThread}
            onOpenMembers={() => setMembersPanelOpen((open) => !open)}
            membersPanelOpen={membersPanelOpen}
            artifactsCount={artifacts.length}
            artifactsPanelVisible={artifactsPanelVisible}
            onOpenArtifactsPanel={handleOpenArtifactsPanel}
            onCloseArtifactsPanel={handleCollapseArtifactsPanel}
          />

          <ChatArea
            messages={displayMessages}
            isStreaming={isStreaming}
            isBusy={showWorkingIndicator}
            streamingContent={isStreaming ? streamingContent : ''}
            streamingToolCalls={isStreaming ? streamingToolCalls : []}
            streamingAgentId={isStreaming ? streamingAgentId : null}
            sendKeyPreference={preferences.sendKey}
            artifactsAutoOpen={preferences.artifactsAutoOpen}
            thinkingEffort={
              preferences.thinkingEffort || defaultThinkingEffortValue || ''
            }
            thinkingEffortOptions={thinkingEffortOptions}
            thinkingEffortControlEnabled={thinkingEffortControlEnabled}
            agentModelId={agentModelId}
            agentProfileName={agentProfileName}
            threadId={currentThreadId || undefined}
            isLoadingHistory={historyLoading}
            threadLoadError={threadLoadError}
            agentAccessRevoked={agentAccessRevoked}
            exampleQuestions={selectedAgent?.example_questions ?? []}
            hasMore={hasMore}
            isLoadingMore={isLoadingMore}
            onLoadMore={handleLoadMore}
            onSendMessage={handleSendMessage}
            onSendKeyPreferenceChange={(value) => {
              updatePreferences({ sendKey: value })
            }}
            onArtifactsAutoOpenChange={(value) => {
              updatePreferences({ artifactsAutoOpen: value })
            }}
            onThinkingEffortChange={(value) => {
              updatePreferences({ thinkingEffort: value })
            }}
            onHitlApprovedContinue={handleHitlApprovedContinue}
            onHitlRejected={handleHitlRejected}
            isSharedThread={isSharedThread}
            rosterAgentOptions={rosterAgentOptions}
            memberUserIds={threadMemberUserIds}
            memberUserLabels={threadMemberUserLabels}
            currentUserId={user?.id}
            userNameById={userNameById}
            agentNameById={agentNameById}
            fallbackAgentId={isSharedThread ? undefined : defaultSharedAgentId ?? selectedAgentId}
          />
        </div>
      </div>

      {sharedUiEnabled ? (
        <>
          <CreateSharedThreadDialog
            open={conversationCreateOpen}
            onOpenChange={setConversationCreateOpen}
            agents={agentOptions.map((a) => ({ id: a.id, name: a.name }))}
            defaultAgentId={selectedAgentId}
            onCreated={(id) => {
              navigate(workbenchThreadPath({ id, threadKind: 'shared' }))
            }}
          />
          {currentThreadId ? (
            <SharedThreadParticipantsSheet
              open={membersPanelOpen}
              onOpenChange={setMembersPanelOpen}
              threadId={currentThreadId}
              primaryAgentId={currentThread?.agentId}
              isOwner={canManageMembers}
            />
          ) : null}
        </>
      ) : null}

      {isArtifactSplit ? (
        <ArtifactsPanel
          artifacts={artifacts}
          selectedArtifact={selectedArtifact}
          sessionTitle={sessionTitle}
          loading={artifactsLoading}
          width={artifactsPanelWidth}
          onWidthChange={updatePanelWidth}
          onArtifactSelect={selectArtifact}
          onClearSelection={clearSelection}
          onCollapse={handleCollapseArtifactsPanel}
        />
      ) : null}
    </div>
  )
}
