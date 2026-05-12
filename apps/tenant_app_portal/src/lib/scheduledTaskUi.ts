export function getScheduledTaskStatusClass(status: string): string {
  const classMap: Record<string, string> = {
    pending: 'bg-warn/15 text-foreground border-warn/30',
    running: 'bg-secondary text-secondary-foreground border-border',
    paused: 'bg-muted text-muted-foreground border-border',
    completed: 'bg-success/15 text-success border-success/30',
    success: 'bg-success/15 text-success border-success/30',
    failed: 'bg-destructive/15 text-destructive border-destructive/30',
    cancelled: 'bg-muted text-muted-foreground border-border',
  }
  return classMap[status] || 'bg-muted text-muted-foreground border-border'
}
