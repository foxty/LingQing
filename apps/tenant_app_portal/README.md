# Tenant Portal

Web frontend for tenant users. Multi-tenant SaaS portal for AI agent interaction, document management, and data source configuration.

## Features

- **Agent Chat**: Interact with AI agents with real-time streaming support
- **Document Management**: Upload, manage, and organize documents (CSV, text, PDF)
- **Knowledge Bases**: Create and configure knowledge bases with RAG integration
- **Data Sources**: Connect and configure RDBMS and other data sources
- **Chat History**: Persistent thread-based conversation management
- **Tenant Administration**: Manage users, roles, and tenant settings
- **Multi-Tenant**: Full tenant isolation and role-based access control (RBAC)

## Tech Stack

- **React 18** + **TypeScript**: Type-safe component development
- **Vite**: Fast build tool and dev server
- **TailwindCSS**: Utility-first styling
- **shadcn/ui** + **Radix UI**: Accessible, composable components
- **React Router**: Client-side routing
- **TanStack Query**: Server state management and caching
- **React Hook Form** + **Zod**: Form state and validation
- **Lucide React**: Icon library
- **Axios**: HTTP client

## Project Structure

```
src/
├── components/          # UI components (pages, dialogs, layout)
├── components/ui/       # shadcn/ui base components
├── pages/              # Page components
├── hooks/              # Custom React hooks
├── lib/                # Utilities and API layer (Axios-based functions)
├── constants/          # App constants
├── types/              # TypeScript interfaces and types
├── App.tsx             # Main app router
└── main.tsx            # Entry point
```

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn

### Development Setup

```bash
# Install dependencies
npm install

# Set up environment variables
cp .env.example .env.local
# Edit .env.local with your backend URLs

# Start development server
npm run dev
```

Default dev server runs on `http://localhost:5173`.

### Build & Production

```bash
# Build for production
npm run build

# Preview production build locally
npm run preview

# Type checking and linting
npm run lint
```

## Environment Configuration

All environment variables must be prefixed with `VITE_` to be exposed to the client (Vite requirement). **Never store secrets in client-side vars.**

### Configuration File Precedence

Vite loads env files in this order (later files override earlier ones):

1. `.env` (committed, shared defaults)
2. `.env.local` (local dev, not committed)
3. `.env.[mode]` (e.g., `.env.production`)
4. `.env.[mode].local` (local overrides for a mode)

### Recommended Setup

**Local Development:**

```bash
# .env.local
VITE_BACKEND_URL=http://localhost:8000/api/
```

**Deployment (behind Nginx proxy with relative paths):**

```bash
VITE_BACKEND_URL=/api/
```

### Docker Build-Time Injection (CI/CD)

Pass environment variables at build time to support multi-environment deployments:

```bash
docker build -f deploy/docker/Dockerfile.frontend \
  --build-arg VITE_BACKEND_URL=/api/ \
  -t your-registry/tenant-portal:latest .
```

Backend URLs also have fallback logic in `src/lib/config.ts`.

## Backend Services

The portal communicates with two backend services:

| Service            | Port | Responsibility                                                  |
| ------------------ | ---- | --------------------------------------------------------------- |
| **Tenant Backend** | 8000 | Authentication, user/tenant management, documents, data sources |
| **Chat Backend**   | 8001 | Chat threads, agent orchestration, streaming responses          |

## Architecture Notes

- **3-Layer Pattern**: Components → Custom Hooks → API layer (`lib/\*Api.ts`)
- **API Layer**: Stateless functions using Axios; consumed by hooks and tests
- **State Management**: React Query for server state; React state for UI state
- **Type Safety**: Interfaces defined in API layer files, shared with hooks

Example pattern:

```typescript
// lib/dataSourceApi.ts
export interface DataSource {
  id: number
  name: string
}
export async function getDataSources(): Promise<DataSource[]> {
  const res = await api.get<DataSource[]>('/data-sources')
  return res.data
}

// hooks/useDataSources.ts
export function useDataSources() {
  return useQuery({
    queryKey: ['dataSources'],
    queryFn: getDataSources,
  })
}
```

## Development Workflow

### Adding Components

Use shadcn/ui CLI to add pre-built components:

```bash
npx shadcn-ui@latest add <component-name>
```

Components are installed to `src/components/ui/` and can be customized.

### Running Locally with Docker Services

```bash
# From project root, start backend services
./deploy/scripts/local-stack.sh infra-up

# In another terminal, start frontend
cd apps/tenant_app_portal && npm run dev
```

## Troubleshooting

- **Backend URL errors in console**: Check `VITE_BACKEND_URL` are set in `.env.local`
- **CORS issues**: In production, use relative paths (`/api/`) behind Nginx instead of absolute URLs
- **Types not found**: Run `npm run build` to ensure generated types are up-to-date
- **Port conflicts**: Vite will use a different port if 5173 is taken; check console output
