/**
 * API Configuration Constants
 */

export const API_ENDPOINTS = {
  // Auth
  login: '/auth/login',

  // Data Sources
  dataSources: '/data-sources',
  dataSourceById: (id: number) => `/data-sources/${id}`,
  testConnection: '/data-sources/test-connection',
  discoverAssets: (id: number) => `/data-sources/${id}/discover-assets`,
  updateAssetSelection: (id: number) => `/data-sources/${id}/assets/selection`,
  dataSourceAssets: (id: number) => `/data-sources/${id}/assets`,
  uploadCsv: (id: number) => `/data-sources/${id}/assets/upload-csv`,
  assetByName: (id: number, name: string) => `/data-sources/${id}/assets/${name}`,
  queryAsset: (id: number, name: string) => `/data-sources/${id}/assets/${name}/query`,

  // API Connectors
  apiConnectors: '/api-connectors',
  apiConnectorById: (id: number) => `/api-connectors/${id}`,
  apiConnectorSyncSchema: (id: number) => `/api-connectors/${id}/sync-schema`,
  apiConnectorOperations: (id: number) => `/api-connectors/${id}/operations`,
  apiConnectorOperationStats: (id: number) => `/api-connectors/${id}/operations/stats`,
  apiConnectorOperationById: (id: number) => `/api-connectors/operations/${id}`,
  apiConnectorOperationStatusById: (id: number) => `/api-connectors/operations/${id}/status`,
  apiConnectorCallOperation: (operationUid: string) =>
    `/api-connectors/operations/${operationUid}/call`,

  // Documents
  documents: '/documents',
  documentById: (id: number) => `/documents/${id}`,
  uploadDocument: '/documents/upload',

  // Agents
  agents: '/agents',

  // Chat
  chat: (agentId: number) => `/chat/${agentId}`,

  // History
  history: '/history',
} as const
