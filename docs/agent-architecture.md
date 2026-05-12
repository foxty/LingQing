# LingQing Agent Architecture

## Overview

This document describes the detailed architecture of the LingQing agent system, including main components, inter-connections, built-in AI capabilities, and data flows.

## Architecture Diagram

```mermaid
graph TD
    A["Frontend Portal\n(React + TypeScript)"] --> B["API Gateway\n(FastAPI Routers)"]

    B --> C["Chat Service\n(ChatService)"]
    B --> D["Agent Pool\n(AgentPool)"]
    B --> E["Thread Management\n(ThreadRepository)"]
    B --> F["Message Repository\n(MessageRepository)"]

    C --> G["Agent Execution\n(AgentBase)"]
    D --> G

    G --> H["LangGraph State Machine\n(StateGraph)"]

    H --> I["LLM Call Node\n(_llm_call)"]
    H --> J["Tool Node\n(_tool_node)"]
    H --> K["Load History Node\n(_load_history)"]
    H --> L["Save Messages Node\n(_save_messages)"]

    I --> M["Model Binding Manager\n(ModelBindingManager)"]
    I --> N["Conversation Memory Manager\n(ConversationMemoryManager)"]

    J --> O["Tool Executor\n(ToolExecutor)"]
    J --> P["Skill Control Tools\n(load_skill/unload_skill)"]

    O --> Q["Tool Registry\n(TOOL_REGISTRY)"]
    O --> R["Skill Resolution Service\n(SkillResolutionService)"]

    Q --> S["Built-in Tools\n(search_documents, etc.)"]
    Q --> T["Custom Tools\n(api_connector, etc.)"]

    R --> U["Skill Configurations\n(YAML files)"]
    R --> V["Tenant-scoped Skills"]

    N --> W["Database Storage\n(PostgreSQL)"]
    K --> W
    L --> W

    E --> W
    F --> W

    subgraph "AI Capabilities"
        X["LLM Integration\n(LangChain)"]
        Y["Prompt Engineering\n(System prompts, skills)"]
        Z["Tool Calling\n(Function calling)"]
        AA["Memory Management\n(Conversation history)"]
        BB["Skill System\n(Dynamic loading)"]
    end

    I --> X
    M --> X
    G --> Y
    J --> Z
    N --> AA
    R --> BB

    subgraph "Data Flow"
        CC["User Input"] --> DD["Chat Request"]
        DD --> EE["Thread Creation/Retrieval"]
        EE --> FF["History Loading"]
        FF --> GG["Context Preparation"]
        GG --> HH["LLM Processing"]
        HH --> II["Tool Execution (if needed)"]
        II --> JJ["Response Generation"]
        JJ --> KK["Message Saving"]
        KK --> LL["Streaming Response"]
    end

    A --> CC
    C --> DD
    E --> EE
    K --> FF
    N --> GG
    I --> HH
    O --> II
    I --> JJ
    L --> KK
    C --> LL

    style A fill:#e1f5fe
    style B fill:#f3e5f5
    style C fill:#e8f5e8
    style D fill:#fff3e0
    style G fill:#fce4ec
    style H fill:#f1f8e9
    style I fill:#e0f2f1
    style J fill:#e0f2f1
    style K fill:#e0f2f1
    style L fill:#e0f2f1
    style M fill:#fff8e1
    style N fill:#fff8e1
    style O fill:#fff8e1
    style P fill:#fff8e1
    style Q fill:#e1bee7
    style R fill:#e1bee7
    style S fill:#d1c4e9
    style T fill:#d1c4e9
    style U fill:#d1c4e9
    style V fill:#d1c4e9
    style W fill:#ffccbc
    style X fill:#b3e5fc
    style Y fill:#b3e5fc
    style Z fill:#b3e5fc
    style AA fill:#b3e5fc
    style BB fill:#b3e5fc
    style CC fill:#c8e6c9
    style DD fill:#c8e6c9
    style EE fill:#c8e6c9
    style FF fill:#c8e6c9
    style GG fill:#c8e6c9
    style HH fill:#c8e6c9
    style II fill:#c8e6c9
    style JJ fill:#c8e6c9
    style KK fill:#c8e6c9
    style LL fill:#c8e6c9
```

## Main Components

### 1. Frontend Portal

- **Technology**: React + TypeScript
- **Purpose**: User interface for interacting with agents
- **Features**: Chat interface, thread management, agent configuration

### 2. API Gateway

- **Technology**: FastAPI Routers
- **Purpose**: HTTP request handling and routing
- **Endpoints**: Chat, threads, agents, tools, skills

### 3. Core Services

- **Chat Service** (`ChatService`): Orchestrates chat operations
- **Agent Pool** (`AgentPool`): Manages agent instances
- **Thread Management** (`ThreadRepository`): Handles conversation threads
- **Message Repository** (`MessageRepository`): Persists conversation messages

### 4. Agent Execution Engine

- **Agent Base** (`AgentBase`): Core agent implementation
- **LangGraph State Machine** (`StateGraph`): Manages agent state transitions
- **Nodes**:
  - LLM Call Node: Processes language model requests
  - Tool Node: Executes tool calls
  - Load History Node: Retrieves conversation history
  - Save Messages Node: Persists messages

### 5. LLM Integration Layer

- **Model Binding Manager** (`ModelBindingManager`): Manages LLM model connections
- **Conversation Memory Manager** (`ConversationMemoryManager`): Handles conversation context

### 6. Tool System

- **Tool Executor** (`ToolExecutor`): Executes tool calls
- **Skill Control Tools**: Dynamic skill loading/unloading
- **Tool Registry** (`TOOL_REGISTRY`): Central registry of available tools
- **Skill Resolution Service** (`SkillResolutionService`): Resolves skill configurations

### 7. Storage Layer

- **Database**: PostgreSQL for persistent storage
- **Tables**: Threads, messages, tenants, users, agents

## AI Capabilities Built-in

### 1. LLM Integration

- **Framework**: LangChain
- **Features**: Model-agnostic LLM calls, streaming responses
- **Models**: Support for multiple LLM providers

### 2. Prompt Engineering

- **System Prompts**: Dynamic prompt generation
- **Skill Injection**: Runtime skill loading into prompts
- **Context Management**: Multi-layer context assembly

### 3. Tool Calling

- **Function Calling**: Native LLM function calling support
- **Tool Registry**: Centralized tool management
- **Execution Safety**: Rate limiting, error handling

### 4. Memory Management

- **Conversation History**: Full message persistence
- **Summarization**: Automatic conversation summarization
- **Context Window**: Intelligent context management

### 5. Skill System

- **Dynamic Loading**: Runtime skill activation
- **YAML Configuration**: Declarative skill definitions
- **Tenant Scoping**: Tenant-specific skill availability

## Data Flows

### 1. User Input Flow

```
User Input → Chat Request → Thread Creation/Retrieval → History Loading
```

### 2. Context Preparation Flow

```
History Loading → Context Preparation → LLM Processing
```

### 3. Processing Flow

```
LLM Processing → Tool Execution (if needed) → Response Generation
```

### 4. Persistence Flow

```
Response Generation → Message Saving → Streaming Response
```

### 5. Complete Cycle

```
User Input → Chat Request → Thread Management → History Loading →
Context Preparation → LLM Processing → Tool Execution →
Response Generation → Message Saving → Streaming Response → User Output
```

## Key Design Principles

### 1. Clean Architecture

- **Layer Separation**: API → Service → Domain → Infrastructure
- **Dependency Direction**: Inward dependency only
- **No Circular Imports**: Strict module boundaries

### 2. Tenant Isolation

- **Multi-tenancy**: All operations scoped by tenant ID
- **Data Separation**: Tenant-specific data isolation
- **Permission Controls**: Role-based access control

### 3. Scalability

- **Stateless Services**: Horizontal scaling capability
- **Async Operations**: Non-blocking I/O throughout
- **Connection Pooling**: Efficient database connections

### 4. Observability

- **Structured Logging**: Consistent log format
- **Metrics Collection**: Performance monitoring
- **Error Tracking**: Comprehensive error handling

## Technology Stack

### Backend

- **Framework**: FastAPI (Python)
- **Async Runtime**: asyncio
- **Database**: PostgreSQL with SQLAlchemy
- **LLM Framework**: LangChain
- **Agent Framework**: LangGraph
- **Package Manager**: uv

### Frontend

- **Framework**: React + TypeScript
- **UI Library**: shadcn/ui
- **State Management**: React Query
- **Routing**: React Router
- **Styling**: Tailwind CSS

### Infrastructure

- **Containerization**: Docker
- **Orchestration**: Kubernetes (Helm charts)
- **CI/CD**: GitHub Actions
- **Monitoring**: Structured logging

## Security Considerations

### 1. Authentication & Authorization

- **JWT Tokens**: Secure authentication
- **RBAC**: Role-based access control
- **Tenant Scoping**: Automatic tenant isolation

### 2. Data Protection

- **Encryption**: Sensitive data encryption at rest
- **Input Validation**: Comprehensive input sanitization
- **Rate Limiting**: API rate limiting per tenant

### 3. Tool Security

- **Sandboxing**: Code execution in isolated environments
- **Permission Checks**: Tool-level permission validation
- **Audit Logging**: Complete action auditing

_HALO_
