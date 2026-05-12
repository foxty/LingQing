import ArtifactsPanel from '@/components/artifacts/ArtifactsPanel'
import ChatArea from '@/components/chat/ChatArea'
import ThreadSelector from '@/components/workbench/ThreadSelector'
import { Button } from '@/components/ui/button'
import { useArtifacts } from '@/hooks/useArtifacts'
import { useAuth } from '@/hooks/useAuth'
import { useThread, useThreads } from '@/hooks/useThreads'
import { useUserPreferences } from '@/hooks/useUserPreferences'
import { useWorkbenchChat } from '@/hooks/useWorkbenchChat'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAgents } from '@/hooks/useAgents'
import { SYSTEM_AGENT_ONE_ID } from '@/lib/agentsApi'
import { PanelRight } from 'lucide-react'

i18n.addResourceBundle('en', 'translation', {
  workbench: {
    createThreadFailed: 'Failed to create chat thread. Please try again.',
    openArtifacts: 'Open artifacts',
    untitledThread: 'Conversation',
    selectAgent: 'Agent',
    agentAccessRevoked: 'You no longer have access to this agent',
    agentAccessRevokedDesc: 'This conversation is no longer listed. Start a new one with an agent you can use.',
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  workbench: {
    createThreadFailed: '创建对话失败，请重试。',
    openArtifacts: '打开产物',
    untitledThread: '对话',
    selectAgent: '智能体',
    agentAccessRevoked: '你已没有此智能体的访问权限',
    agentAccessRevokedDesc: '此对话已不再列出。请改用你仍可访问的智能体开始新对话。',
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
  const [artifactsPanelVisible, setArtifactsPanelVisible] = useState(true)
  const [departedThreadId, setDepartedThreadId] = useState<string | null>(null)
  const initialMessageSentRef = useRef(false)
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
  } = useArtifacts(currentThreadId)

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
    handleSendMessage,
    handleHitlApprovedContinue,
    handleHitlRejected,
  } = useWorkbenchChat({
    agentId,
    threadId: currentThreadId,
    createThread,
    navigate,
    updateThreadTitle,
    reloadArtifacts,
    selectArtifact,
    setArtifactsPanelVisible,
  })

  const queryAgentId = Number(searchParams.get('agent'))
  const hasQueryAgent = Boolean(searchParams.get('agent')) && Number.isFinite(queryAgentId)
  const accessibleThreads = useMemo(() => {
    const allowed = agentsLoaded && !agentsFailed ? accessibleAgentIds : null
    return [...threads]
      .filter((thread) => allowed == null || allowed.has(thread.agentId))
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
  }, [accessibleAgentIds, agentsFailed, agentsLoaded, threads])
  const sortedThreads = useMemo(
    () => accessibleThreads.filter((thread) => thread.agentId === selectedAgentId),
    [accessibleThreads, selectedAgentId]
  )
  const latestThread = accessibleThreads[0] || null
  const currentThread = sortedThreads.find((thread) => thread.id === currentThreadId) || null
  const selectedAgent = agentOptions.find((agent) => agent.id === selectedAgentId)
  const agentAccessRevoked =
    agentsLoaded && !agentsFailed && selectedAgentId > 0 && !agents.some((agent) => agent.id === selectedAgentId)
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
      if (accessibleAgentIds.has(routeThread.agent_id)) {
        if (routeThread.agent_id !== selectedAgentId) {
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
    if (hasQueryAgent) {
      const latestForAgent = sortedThreads[0]
      if (latestForAgent) {
        navigate(`/workbench/${latestForAgent.id}`, { replace: true })
      }
      return
    }
    if (latestThread) {
      navigate(`/workbench/${latestThread.id}`, { replace: true })
    }
  }, [
    agentsFailed,
    agentsLoaded,
    hasQueryAgent,
    latestThread,
    navigate,
    sortedThreads,
    threadIdParam,
    threadsFetched,
    threadsLoading,
  ])

  useEffect(() => {
    const state = location.state as { initialMessage?: string } | null
    if (state?.initialMessage && threadIdParam && !initialMessageSentRef.current && user) {
      initialMessageSentRef.current = true
      window.history.replaceState({}, document.title)
      handleSendMessage(state.initialMessage, [])
    }
  }, [location.state, threadIdParam, user, handleSendMessage])

  const handleNewThread = useCallback(async () => {
    try {
      const newThread = await createThread({ agentId: selectedAgentId })
      updatePreferences({ lastAgentId: selectedAgentId })
      navigate(`/workbench/${newThread.id}`)
    } catch (error) {
      console.error('Failed to create thread:', error)
    }
  }, [createThread, navigate, selectedAgentId, updatePreferences])

  const handleThreadSelect = useCallback(
    (threadId: string) => {
      navigate(`/workbench/${threadId}`)
    },
    [navigate]
  )

  const handleDeleteThread = useCallback(
    async (threadId: string) => {
      const remainingThreads = sortedThreads.filter((thread) => thread.id !== threadId)
      if (threadId === currentThreadId || threadId === threadIdParam) {
        setDepartedThreadId(threadId)
        setCurrentThreadId(null)
        if (remainingThreads.length > 0) {
          navigate(`/workbench/${remainingThreads[0].id}`, { replace: true })
        } else {
          navigate(`/workbench?agent=${selectedAgentId}`, { replace: true })
        }
      }
      await deleteThread(threadId)
    },
    [currentThreadId, deleteThread, navigate, selectedAgentId, sortedThreads, threadIdParam]
  )

  return (
    <div id="workbench" className="flex h-full overflow-hidden">
      <div className="flex-1 flex overflow-hidden">
        <div className={`flex flex-col overflow-hidden flex-1 ${isArtifactSplit ? 'min-w-[16rem]' : ''}`}>
          <div className="flex items-center gap-2 px-3 py-1.5 border-b min-h-11">
            <Select
              value={String(selectedAgentId)}
              onValueChange={(value) => {
                const nextId = Number(value)
                setSelectedAgentId(nextId)
                updatePreferences({ lastAgentId: nextId })
                navigate(`/workbench?agent=${nextId}`)
              }}
            >
              <SelectTrigger className="h-9 w-44 shrink-0" aria-label={t('workbench.selectAgent')}>
                <SelectValue placeholder={t('workbench.selectAgent')} />
              </SelectTrigger>
              <SelectContent>
                {agentOptions.map((agent) => (
                  <SelectItem key={agent.id} value={String(agent.id)}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ThreadSelector
              threads={sortedThreads}
              currentThreadId={currentThreadId}
              isLoading={threadsLoading}
              onSelectThread={handleThreadSelect}
              onCreateThread={handleNewThread}
              onDeleteThread={handleDeleteThread}
            />
            {artifacts.length > 0 && !artifactsPanelVisible ? (
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto h-9 shrink-0 px-2"
                onClick={() => setArtifactsPanelVisible(true)}
                title={t('workbench.openArtifacts')}
                aria-label={t('workbench.openArtifacts')}
              >
                <PanelRight className="h-4 w-4" />
                <span className="ml-1.5 tabular-nums text-xs text-muted-foreground">{artifacts.length}</span>
              </Button>
            ) : null}
          </div>

          <ChatArea
            messages={displayMessages}
            isStreaming={isStreaming}
            isBusy={showWorkingIndicator}
            streamingContent={isStreaming ? streamingContent : ''}
            streamingToolCalls={isStreaming ? streamingToolCalls : []}
            sendKeyPreference={preferences.sendKey}
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
            onHitlApprovedContinue={handleHitlApprovedContinue}
            onHitlRejected={handleHitlRejected}
          />
        </div>
      </div>

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
          onCollapse={() => setArtifactsPanelVisible(false)}
        />
      ) : null}
    </div>
  )
}
