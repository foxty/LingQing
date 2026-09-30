import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Can } from '@/components/Can'
import { Button } from '@/components/ui/button'
import SidebarNavGroup, {
  getArtifactNavItems,
  getIntegrationNavItems,
  getSettingsNavItems,
} from '@/components/SidebarNavGroup'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'
import { actionRules, navRules } from '@/lib/permissionRules'
import {
  Cable,
  ChevronLeft,
  ChevronRight,
  Bot,
  Code,
  HardDrive,
  Layers,
  MessageSquare,
  Search,
  Settings,
} from 'lucide-react'
import { Link } from 'react-router-dom'

interface SidebarProps {
  sidebarCollapsed: boolean
  onToggleSidebar: () => void
  isActive: (path: string) => boolean
}

function navItemClass(collapsed: boolean) {
  return cn('w-full', collapsed ? 'justify-center px-2' : 'justify-start')
}

export default function Sidebar({ sidebarCollapsed, onToggleSidebar, isActive }: SidebarProps) {
  const { t } = useTranslation()
  const { hasAny } = useAuth()
  const artifactItems = getArtifactNavItems(t)
  const settingsItems = useMemo(
    () =>
      getSettingsNavItems(t, {
        includeDocumentSources: hasAny(actionRules.canManageDocumentSources()),
      }),
    [hasAny, t]
  )
  const integrationItems = useMemo(
    () =>
      getIntegrationNavItems(t, {
        includeDataSources: hasAny(navRules.showDataSourcesMenu()),
        includeApiConnectors: hasAny(navRules.showApiConnectorsMenu()),
      }),
    [hasAny, t]
  )

  return (
    <aside
      className={cn(
        'border-r flex-shrink-0 transition-all duration-300 ease-in-out relative flex h-full flex-col',
        sidebarCollapsed ? 'w-16' : 'w-52'
      )}
    >
      <div className="flex-1 overflow-y-auto p-4">
        <nav className="space-y-2">
          <Can any={navRules.showConversationMenu()}>
            <Link to="/workbench">
              <Button
                variant={isActive('/workbench') ? 'secondary' : 'ghost'}
                className={navItemClass(sidebarCollapsed)}
                title={t('sidebar.conversation')}
              >
                <MessageSquare className="w-4 h-4" />
                {!sidebarCollapsed && <span className="ml-2">{t('sidebar.conversation')}</span>}
              </Button>
            </Link>
          </Can>

          <Can any={navRules.showAgentsMenu()}>
            <Link to="/agents">
              <Button
                variant={isActive('/agents') ? 'secondary' : 'ghost'}
                className={navItemClass(sidebarCollapsed)}
                title={t('sidebar.agents')}
              >
                <Bot className="w-4 h-4" />
                {!sidebarCollapsed && <span className="ml-2">{t('sidebar.agents')}</span>}
              </Button>
            </Link>
          </Can>

          <SidebarNavGroup
            collapsed={sidebarCollapsed}
            icon={<Layers className="h-4 w-4" />}
            label={t('sidebar.artifacts')}
            items={artifactItems}
          />

          <Can any={navRules.showDocumentsMenu()}>
            <Link to="/knowledge">
              <Button
                variant={isActive('/knowledge') ? 'secondary' : 'ghost'}
                className={navItemClass(sidebarCollapsed)}
                title={t('sidebar.knowledgeBase')}
              >
                <HardDrive className="w-4 h-4" />
                {!sidebarCollapsed && <span className="ml-2">{t('sidebar.knowledgeBase')}</span>}
              </Button>
            </Link>
          </Can>

          {integrationItems.length > 0 ? (
            <SidebarNavGroup
              collapsed={sidebarCollapsed}
              icon={<Cable className="h-4 w-4" />}
              label={t('sidebar.integrations')}
              items={integrationItems}
            />
          ) : null}

          <Can any={navRules.showSkillsMenu()}>
            <Link to="/skills">
              <Button
                variant={isActive('/skills') ? 'secondary' : 'ghost'}
                className={navItemClass(sidebarCollapsed)}
                title={t('sidebar.skills')}
              >
                <Code className="w-4 h-4" />
                {!sidebarCollapsed && <span className="ml-2">{t('sidebar.skills')}</span>}
              </Button>
            </Link>
          </Can>

          <Link to="/search">
            <Button
              variant={isActive('/search') ? 'secondary' : 'ghost'}
              className={navItemClass(sidebarCollapsed)}
              title={t('sidebar.search')}
            >
              <Search className="w-4 h-4" />
              {!sidebarCollapsed && <span className="ml-2">{t('sidebar.search')}</span>}
            </Button>
          </Link>

          <Can any={navRules.showSettingsMenu()}>
            <SidebarNavGroup
              collapsed={sidebarCollapsed}
              icon={<Settings className="h-4 w-4" />}
              label={t('sidebar.settings')}
              items={settingsItems}
            />
          </Can>
        </nav>
      </div>

      <button
        onClick={onToggleSidebar}
        className="absolute -right-3 top-8 z-10 flex h-6 w-6 items-center justify-center rounded-full border bg-background shadow-md hover:bg-accent transition-colors"
        title={sidebarCollapsed ? t('common.expandSidebar') : t('common.collapseSidebar')}
      >
        {sidebarCollapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </button>
    </aside>
  )
}
