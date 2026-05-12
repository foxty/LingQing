import { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
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
  const { t } = useTranslation()
  const { user, logout, hasAny } = useAuth()
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
          <div className="flex items-center gap-3 min-w-0">
            <div className="min-w-0">
              <p className="text-xl font-semibold truncate">{t('brand.title')}</p>
              <p className="text-xs text-muted-foreground truncate">{t('brand.subtitle')}</p>
            </div>
            {user?.tenantName ? (
              <div className="hidden sm:flex flex-col justify-center rounded-md border px-2.5 py-1 min-h-11">
                <span className="text-[11px] text-muted-foreground tracking-wide">
                  {t('header.tenant')}
                </span>
                <span className="text-sm font-medium leading-tight truncate max-w-[12rem]">
                  {user.tenantName}
                </span>
              </div>
            ) : null}
          </div>
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
