# LingQing Tenant App Service

Unified tenant app service combining chat orchestration and tenant management for the LingQing platform.

## Features

### Chat & Agent Orchestration

- Real-time chat with AI agents
- Streaming and non-streaming responses
- Conversation history management
- Multi-tenant agent orchestration
- Chart generation and visualization

### Tenant Management

- Tenant and user management
- Authentication and authorization
- Agent configuration management
- Knowledge base and document management
- Data source management
- File storage

## Development

```bash
# Start development server on port 8000
uv run uvicorn apps.tenant_app_service.server:app --reload --port 8000

# Or use nx
nx dev tenant_app_service
```

## API Endpoints

### Authentication

- `POST /auth/login` - User login
- `GET /auth/profile` - Get current user profile
- `POST /auth/profile/change-password` - Change password

### Tenant Management

- `GET /tenants` - List tenants (admin only)
- `GET /tenants/{tenant_id}/agents` - Get tenant agents
- `GET /tenants/stats` - Get tenant statistics

### Document Management

- `GET /documents` - List documents
- `POST /documents` - Upload document
- `GET /documents/{doc_id}` - Get document details
- `DELETE /documents/{doc_id}` - Delete document

### Data Sources

- `GET /data-sources` - List data sources
- `POST /data-sources` - Create data source
- `GET /data-sources/{id}` - Get data source details
- `POST /data-sources/{id}/test-connection` - Test connection
- `POST /data-sources/{id}/discover-assets` - Discover assets
- `GET /data-sources/{id}/assets` - List assets
- `POST /data-sources/{id}/assets/upload-csv` - Upload CSV

### Chat & Conversations

- `POST /chat/{agent_id}` - Send message to agent (non-streaming)
- `POST /chat/{agent_id}/stream` - Send message to agent (streaming)
- `GET /threads` - List conversation threads
- `POST /threads` - Create thread
- `GET /threads/{thread_id}` - Get thread details
- `GET /threads/{thread_id}/messages` - Get messages
- `DELETE /threads/{thread_id}` - Delete thread

### Health

- `GET /health` - Health check
- `GET /` - Root endpoint with version info

## Dependencies

### Core Framework

- FastAPI
- Uvicorn

### AI & Agent Orchestration

- LangGraph
- LangChain
- LangChain Core

### Database

- SQLAlchemy
- Alembic (database migrations)
- psycopg2 (PostgreSQL adapter)

### Vector & Knowledge

- ChromaDB (vector store)
- Embeddings support

### Data & Visualization

- Plotly (for charts)
- Pandas

### Utilities

- Pydantic
- python-dotenv

## Architecture

```
tenant_app_service/
├── routers/              # API route handlers
│   ├── auth.py          # Authentication endpoints
│   ├── tenants.py       # Tenant management endpoints
│   ├── documents.py     # Document management endpoints
│   ├── data_sources.py  # Data source endpoints
│   ├── chat.py          # Chat endpoints
│   ├── threads.py       # Conversation thread endpoints
│   └── health.py        # Health check endpoint
├── services/            # Business logic (if any)
├── auth/                # Authentication domain
├── tenant/              # Tenant management domain
├── chat/                # Chat domain
├── agents/              # Agent orchestration
├── thread/              # Conversation threading
├── agent_pool.py        # Agent pool management
├── constants.py         # Shared constants
└── server.py            # FastAPI application entry point
```

## Environment Variables

See `deploy/env/.env.template` for required configuration. Key variables:

- `TENANT_APP_DB_*` - Database connection settings
- `DATA_ROOT_PATH` - Root path for data storage
- `CORS_ORIGINS` - Allowed CORS origins
- `JWT_SECRET_KEY` - JWT secret for authentication

## Local Development Setup

1. Set up environment variables in `.env.local`
2. Ensure database is running and migrated
3. Start the tenant app service:
   ```bash
   uv run uvicorn apps.tenant_app_service.server:app --reload --port 8000
   ```
4. Service will be available at `http://localhost:8000`
5. API documentation at `http://localhost:8000/docs`

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/chat/

# Run with coverage
uv run pytest --cov=apps
```

## Production Deployment

See deployment guides in `deploy/` directory for Docker, Kubernetes, and cloud deployment options.
