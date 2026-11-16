/** Mirror of apps.shared.document.sync_types — connector / connection status values. */

export const CONNECTOR_STATUS = {
  ACTIVE: 'active',
  STOPPED: 'stopped',
} as const

export type ConnectorStatus = (typeof CONNECTOR_STATUS)[keyof typeof CONNECTOR_STATUS]

export const SOURCE_CONNECTION_STATUS = {
  ACTIVE: 'active',
  REVOKED: 'revoked',
} as const

export type SourceConnectionStatus =
  (typeof SOURCE_CONNECTION_STATUS)[keyof typeof SOURCE_CONNECTION_STATUS]