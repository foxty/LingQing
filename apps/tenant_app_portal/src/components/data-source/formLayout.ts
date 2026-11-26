import type { FieldErrors } from 'react-hook-form'

/** Inline connection validation from AddDataSourceDialog submit (Zod + secret fields). */
export type DataSourceConnectionFieldErrors = Partial<{
  host: string
  port: string
  database: string
  username: string
  password: string
  warehouse_id: string
  http_path: string
  metadataSyncUsername: string
  metadataSyncPassword: string
}>

export function resolveConnectionFieldError(
  key: keyof DataSourceConnectionFieldErrors,
  connectionFieldErrors?: DataSourceConnectionFieldErrors,
  errors?: FieldErrors,
): string | undefined {
  return connectionFieldErrors?.[key] ?? (errors?.[key]?.message as string | undefined)
}

/** Shared grid layout for Add / Edit Data Source dialog fields. */

export const dsFieldLabelClass =
  'text-sm font-medium leading-tight text-foreground text-right shrink-0 pr-0.5'

export const dsFieldRowClass =
  'grid w-full min-w-0 grid-cols-[7.25rem_minmax(0,1fr)] gap-x-3 items-center'

export const dsFieldRowStartClass = 'grid grid-cols-[7.25rem_minmax(0,1fr)] gap-x-3 items-start'

/** Host/port and username/password rows: aligned label + control columns. */
export const dsFieldPairRowClass =
  'grid w-full min-w-0 grid-cols-[7.25rem_minmax(0,1fr)_5.5rem_minmax(0,1fr)] gap-x-3 items-center'

/**
 * Indent nested content to the value column of ``dsFieldRowClass`` (label width + gap).
 * Keep in sync with ``grid-cols-[7.25rem_minmax(0,1fr)] gap-x-3``.
 */
export const dsFormValueColumnInsetClass = 'ml-[calc(7.25rem+0.75rem)] min-w-0'