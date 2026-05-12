import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

export interface SidebarNavItem {
  to: string
  label: string
  matchPrefixes: string[]
}

function isPathActive(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
}

interface SidebarNavGroupProps {
  collapsed: boolean
  icon: ReactNode
  label: string
  items: SidebarNavItem[]
}

export default function SidebarNavGroup({ collapsed, icon, label, items }: SidebarNavGroupProps) {
  const { pathname } = useLocation()
  const isItemActive = (item: SidebarNavItem) => isPathActive(pathname, item.matchPrefixes)
  const groupActive = items.some(isItemActive)
  const [open, setOpen] = useState(groupActive)

  useEffect(() => {
    if (groupActive) {
      setOpen(true)
    }
  }, [groupActive])

  if (collapsed) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant={groupActive ? 'secondary' : 'ghost'}
            className="w-full justify-center px-2"
            title={label}
          >
            {icon}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="start" className="min-w-[10rem]">
          {items.map((item) => (
            <DropdownMenuItem key={item.to} asChild>
              <Link
                to={item.to}
                className={cn(isItemActive(item) && 'bg-muted font-medium text-foreground')}
              >
                {item.label}
              </Link>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }

  return (
    <div className="space-y-0.5">
      <Button
        type="button"
        variant={groupActive ? 'secondary' : 'ghost'}
        className="w-full justify-start gap-1 px-2"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        {icon}
        <span className="ml-1 truncate">{label}</span>
      </Button>
      {open ? (
        <div className="ml-3 space-y-0.5 border-l pl-2">
          {items.map((item) => (
            <Link key={item.to} to={item.to}>
              <Button
                variant={isItemActive(item) ? 'secondary' : 'ghost'}
                className="h-8 w-full justify-start px-2 text-sm font-normal"
              >
                <span className="truncate">{item.label}</span>
              </Button>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function getArtifactNavItems(
  t: (key: string) => string
): SidebarNavItem[] {
  return [
    {
      to: '/artifacts/reports',
      label: t('sidebar.reports'),
      matchPrefixes: ['/artifacts/reports', '/reports'],
    },
    {
      to: '/artifacts/dashboards',
      label: t('sidebar.dashboards'),
      matchPrefixes: ['/artifacts/dashboards', '/dashboards'],
    },
    {
      to: '/artifacts/live-apps',
      label: t('sidebar.liveApps'),
      matchPrefixes: ['/artifacts/live-apps', '/live-apps'],
    },
    {
      to: '/artifacts/scheduled-tasks',
      label: t('sidebar.scheduledTasks'),
      matchPrefixes: ['/artifacts/scheduled-tasks', '/scheduled-tasks'],
    },
  ]
}

export function getSettingsNavItems(
  t: (key: string) => string
): SidebarNavItem[] {
  return [
    { to: '/settings/models', label: t('settings.models'), matchPrefixes: ['/settings/models'] },
    {
      to: '/settings/embedding',
      label: t('settings.embedding'),
      matchPrefixes: ['/settings/embedding'],
    },
    { to: '/settings/tags', label: t('settings.tags'), matchPrefixes: ['/settings/tags'] },
    { to: '/settings/abac', label: t('settings.abac'), matchPrefixes: ['/settings/abac'] },
    {
      to: '/settings/identity',
      label: t('settings.identity'),
      matchPrefixes: ['/settings/identity', '/settings/sso'],
    },
    { to: '/settings/users', label: t('settings.users'), matchPrefixes: ['/settings/users'] },
    { to: '/settings/usage', label: t('settings.usage'), matchPrefixes: ['/settings/usage'] },
  ]
}

export function getIntegrationNavItems(
  t: (key: string) => string,
  options: { includeDataSources: boolean; includeApiConnectors: boolean }
): SidebarNavItem[] {
  const items: SidebarNavItem[] = []
  if (options.includeDataSources) {
    items.push({
      to: '/data-sources',
      label: t('sidebar.dataSources'),
      matchPrefixes: ['/data-sources'],
    })
  }
  if (options.includeApiConnectors) {
    items.push({
      to: '/api-connectors',
      label: t('sidebar.apiConnector'),
      matchPrefixes: ['/api-connectors'],
    })
  }
  return items
}
