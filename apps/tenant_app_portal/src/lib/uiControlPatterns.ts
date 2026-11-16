/**
 * Locked Tailwind recipes for buttons, icon buttons, and compact action rows.
 * Normative rules: apps/tenant_app_portal/DESIGN.md §6.1
 */

/** Irreversible action before ConfirmationDialog — never `destructive` fill on the control. */
export const buttonDestructiveOutlineClass =
  'border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive'

/** Three-up actions in popovers (sync / pause / disconnect). */
export const buttonCompactActionClass = 'h-8 min-w-0 gap-1 px-2 text-xs'

/** Icon-only control beside a chip or table cell (Info, overflow). */
export const iconButtonDenseClass = 'h-6 w-6 shrink-0 p-0 text-muted-foreground hover:text-foreground'

/** Table / list row overflow trigger (⋮). */
export const iconButtonRowClass = 'h-8 w-8 p-0'

/** Popover header status trigger wrapping a chip — not a filled CTA. */
export const popoverChipTriggerClass = 'h-8 shrink-0 px-1 font-normal hover:bg-muted/60'

export const statusChipTableClass =
  'h-5 gap-1 px-1.5 text-[11px] font-normal shadow-none border-transparent max-w-full shrink'

export const statusChipHeaderClass =
  'h-6 gap-1 px-2 text-[11px] font-normal shadow-none border-transparent'