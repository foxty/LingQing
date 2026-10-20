import { useState, useEffect, useLayoutEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import AppBrandHeader from '@/components/AppBrandHeader'
import { useAuth } from '@/hooks/useAuth'
import { usePortalBranding } from '@/hooks/usePortalBranding'
import { resolvePortalBrandDisplay } from '@/lib/portalBrandingDisplay'
import { Button } from '@/components/ui/button'
import { ChevronDown, LogOut, Settings, UserRound } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { navRules } from '@/lib/permissionRules'
import Sidebar from './Sidebar'
import LanguageSwitcher from './LanguageSwitcher'

interface LayoutProps {
  children: React.ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { t, i18n } = useTranslation()
  const { user, logout, hasAny } = useAuth()
  const { data: portalBranding, isPending } = usePortalBranding()
  const brandingPending = isPending && portalBranding === undefined
  const location = useLocation()
  const navigate = useNavigate()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const showSettings = hasAny(navRules.showSettingsMenu())

  useEffect(() => {
    const saved = localStorage.getItem('sidebarCollapsed')
    if (saved !== null) {
      setSidebarCollapsed(saved === 'true')
    }
  }, [])

  useLayoutEffect(() => {
    if (brandingPending) {
      return
    }
    const { pageTitle } = resolvePortalBrandDisplay(portalBranding, t)
    if (pageTitle) {
      document.title = pageTitle
    }
  }, [portalBranding, brandingPending, t, i18n.language])

  const toggleSidebar = () => {
    const newState = !sidebarCollapsed
    setSidebarCollapsed(newState)
    localStorage.setItem('sidebarCollapsed', String(newState))
  }

  const isActive = (path: string) => {
    if (path === '/') {
      return location.pathname === '/'
    }
    return location.pathname === path || location.pathname.startsWith(`${path}/`)
  }

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const needsPadding = !location.pathname.startsWith('/workbench')

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="border-b flex-shrink-0">
        <div className="mx-auto px-4 py-2 flex items-center justify-between gap-4">
          <AppBrandHeader
            branding={portalBranding}
            tenantName={user?.tenantName}
            pending={brandingPending}
          />
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="h-11 gap-1.5 px-2.5">
                  <span className="text-sm font-medium max-w-[10rem] truncate">
                    {user?.username}
                  </span>
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[10rem]">
                <DropdownMenuItem onClick={() => navigate('/profile')}>
                  <UserRound className="mr-2 h-4 w-4" />
                  {t('header.profile')}
                </DropdownMenuItem>
                {showSettings ? (
                  <DropdownMenuItem onClick={() => navigate('/settings')}>
                    <Settings className="mr-2 h-4 w-4" />
                    {t('sidebar.settings')}
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  {t('common.logout')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
          isActive={isActive}
        />
        <main className={`flex-1 overflow-y-auto ${needsPadding ? 'p-4' : ''}`}>{children}</main>
      </div>
    </div>
  )
}
