import { useState } from 'react'
import { Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Dashboard } from '@/lib/dashboardApi'

interface DashboardHeaderProps {
  dashboard: Dashboard
  periodLabel?: string | null
  onUpdate: (payload: { name: string; description: string }) => Promise<void>
}

export default function DashboardHeader({ dashboard, periodLabel, onUpdate }: DashboardHeaderProps) {
  const [dashboardName, setDashboardName] = useState(dashboard.name)
  const [dashboardDescription, setDashboardDescription] = useState(dashboard.description ?? '')
  const [isEditingName, setIsEditingName] = useState(false)
  const [isEditingDescription, setIsEditingDescription] = useState(false)

  const handleSaveDashboardName = async () => {
    if (dashboardName === dashboard.name) {
      setIsEditingName(false)
      return
    }
    try {
      await onUpdate({
        name: dashboardName,
        description: dashboardDescription,
      })
      setIsEditingName(false)
    } catch {
      // Revert on error
      setDashboardName(dashboard.name)
      setIsEditingName(false)
    }
  }

  const handleSaveDashboardDescription = async () => {
    if (dashboardDescription === (dashboard.description ?? '')) {
      setIsEditingDescription(false)
      return
    }
    try {
      await onUpdate({
        name: dashboardName,
        description: dashboardDescription,
      })
      setIsEditingDescription(false)
    } catch {
      // Revert on error
      setDashboardDescription(dashboard.description ?? '')
      setIsEditingDescription(false)
    }
  }

  return (
    <div className="flex-1 space-y-2">
      {isEditingName ? (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={dashboardName}
            onChange={(e) => setDashboardName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSaveDashboardName()
              } else if (e.key === 'Escape') {
                setDashboardName(dashboard.name)
                setIsEditingName(false)
              }
            }}
            autoFocus
            className="text-lg font-semibold bg-background border border-primary rounded px-2 py-1 text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <Button size="sm" variant="ghost" onClick={handleSaveDashboardName} className="text-xs">
            Save
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setDashboardName(dashboard.name)
              setIsEditingName(false)
            }}
            className="text-xs"
          >
            Cancel
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2 group">
          <h1 className="text-lg font-semibold text-foreground">{dashboardName}</h1>
          {periodLabel ? (
            <span className="rounded-full border bg-card px-2 py-0.5 text-xs text-muted-foreground">
              {periodLabel}
            </span>
          ) : null}
          <button
            onClick={() => setIsEditingName(true)}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-muted-foreground hover:text-foreground"
            title="Edit dashboard name"
          >
            <Pencil className="h-3 w-3" />
          </button>
        </div>
      )}
      {isEditingDescription ? (
        <div className="flex items-start gap-2">
          <textarea
            value={dashboardDescription}
            onChange={(e) => setDashboardDescription(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.ctrlKey) {
                handleSaveDashboardDescription()
              } else if (e.key === 'Escape') {
                setDashboardDescription(dashboard.description ?? '')
                setIsEditingDescription(false)
              }
            }}
            autoFocus
            className="text-sm bg-background border border-primary rounded px-2 py-1 text-foreground focus:outline-none focus:ring-2 focus:ring-primary flex-1 resize-none"
            rows={2}
          />
          <div className="flex flex-col gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={handleSaveDashboardDescription}
              className="text-xs"
            >
              Save
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setDashboardDescription(dashboard.description ?? '')
                setIsEditingDescription(false)
              }}
              className="text-xs"
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-2 group">
          {dashboardDescription ? (
            <>
              <p className="text-sm text-muted-foreground">{dashboardDescription}</p>
              <button
                onClick={() => setIsEditingDescription(true)}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-muted-foreground hover:text-foreground flex-shrink-0"
                title="Edit dashboard description"
              >
                <Pencil className="h-3 w-3" />
              </button>
            </>
          ) : (
            <button
              onClick={() => setIsEditingDescription(true)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              + Add description
            </button>
          )}
        </div>
      )}
    </div>
  )
}
