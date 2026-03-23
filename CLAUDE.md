# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Velpos is a web interface for controlling Claude Code via the Agent SDK. Python FastAPI backend + Vue 3 frontend, communicating over REST and WebSocket.

## Development Commands

### Quick Start (Dev)
```bash
# 1. Copy and configure environment
cp build/dev/.env.example build/dev/.env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 2. Start everything (MySQL docker + backend + frontend)
build/dev/start.sh start
```

### Dev Service Management
```bash
build/dev/start.sh start     # Start MySQL + backend + frontend, tail logs
build/dev/start.sh stop      # Stop all (including MySQL)
build/dev/start.sh restart   # Restart all
build/dev/start.sh status    # Check running state
build/dev/start.sh logs      # Tail backend logs
```

### Production (Full Docker)
```bash
# 1. Configure
cp build/prod/.env.example build/prod/.env

# 2. Build and start
cd build/prod && docker compose up --build -d
```

### Run Services Individually
```bash
# Backend (from backend/)
uv run uvicorn main:app --host 0.0.0.0 --port 8083 --reload

# Frontend (from frontend/)
npm run dev
npm run build
```

### Build Directory Structure
```
build/
├── dev/                  # Dev: Docker MySQL + host backend/frontend
│   ├── docker-compose.yml
│   ├── .env.example
│   └── start.sh
└── prod/                 # Prod: Full Docker stack
    ├── docker-compose.yml
    ├── backend.Dockerfile
    ├── frontend.Dockerfile
    ├── nginx.conf
    └── .env.example
```

### Ports
- Backend: 8083 (API docs at http://localhost:8083/docs)
- Frontend: 3000 (dev) / 80 (prod, via nginx)
- MySQL: 3307 (dev host) / 3306 (prod internal)

### Database Migrations (Alembic)
```bash
# From backend/ directory
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```
Migrations auto-run on backend startup. Fallback `create_all` if Alembic fails.

### Required Environment Variables
- `DATABASE_URL` — backend will not start without this (raises RuntimeError)
- `CLAUDE_CLI_PATH` — path to claude CLI binary

## Backend Architecture — DDD Four-Layer

```
backend/
├── domain/           # Pure business logic, no framework deps
│   ├── session/      # Session aggregate: Session, Message, Usage, Status
│   ├── project/      # Project aggregate
│   ├── im_binding/   # IM channel binding, channel registry
│   ├── channel_profile/
│   └── shared/       # Cross-domain value objects
├── application/      # Use case orchestration (one service per aggregate)
│   ├── session/      # SessionApplicationService + commands
│   ├── project/      # ProjectApplicationService + commands
│   ├── im_binding/   # ImChannelApplicationService
│   ├── channel_profile/ claude_session/ command/ plugin/ settings/ terminal/
│   └── (each has command/ for input DTOs, some have port/ for ABC interfaces)
├── infr/             # Infrastructure implementations
│   ├── config/       # database.py (SQLAlchemy async), im_config.py, base.py
│   ├── repository/   # *RepositoryImpl + SQLAlchemy ORM models + Alembic migrations
│   ├── client/       # ClaudeAgentGateway, ConnectionManager, etc.
│   └── im/           # IM adapters: lark/, openim/, qq/, weixin/
└── ohs/              # Open Host Service — external-facing layer
    ├── dependencies.py  # DI assembly (FastAPI Depends), singleton wiring
    ├── http/            # REST routers, ApiResponse<T>, DTOs, assemblers
    └── ws/              # WebSocket router (/ws/{session_id})
```

### Key Patterns
- **DI wiring**: `ohs/dependencies.py` creates singletons at module level and provides `get_*` factory functions for FastAPI `Depends`.
- **Domain ACL**: Domain defines abstract interfaces (e.g., `domain/session/acl/claude_agent_gateway.py`), infr layer implements them.
- **Commands**: Application layer uses frozen Pydantic models as input DTOs (e.g., `CreateSessionCommand`).
- **Assemblers**: `ohs/assembler/` converts between domain models and HTTP DTOs.
- **API response**: Unified `ApiResponse(code, message, data)` — code 0 is success.
- **WebSocket protocol**: `/ws/{session_id}` with action-based messages (`send_prompt`, `cancel`, `get_status`, `set_model`, `set_permission_mode`, `user_response`) and event-based responses (`connected`, `message`, `status_change`, `error`, `info`).
- **IM integration**: Plugin-style adapters registered in `ImChannelRegistry` (Lark, OpenIM, QQ, WeChat). Outbound sync via callback hook on assistant responses.

## Frontend Architecture — Vue 3 + Feature-Sliced

```
frontend/src/
├── app/        # App shell (App.vue, main.js, router)
├── pages/      # Route-level pages (chat-panel/)
├── features/   # Self-contained UI features
│   ├── session-list/    send-message/    message-display/
│   ├── cancel-query/    clear-context/   compact-context/
│   ├── command-palette/  plugin-manager/  settings-manager/
│   ├── im-binding/      terminal/        notification-center/
├── entities/   # Core business data (session/, project/)
└── shared/     # Shared utilities (api/, components/, styles/)
```

### Key Patterns
- **State management**: Module-level singleton composables (`useSession.js`, `useProject.js`) — not Pinia/Vuex.
- **HTTP client**: `shared/api/httpClient.js` — treats `code === 0` as success.
- **WS client**: `shared/api/wsClient.js` — auto-reconnect on abnormal close.
- **Path aliases**: `@app`, `@pages`, `@features`, `@entities`, `@shared`, `@` (→ `src/`).
- **No component library** — custom CSS throughout.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy (async), Alembic, claude-agent-sdk, aiomysql
- **Frontend**: Vue 3 (Composition API), Vite 8, marked, highlight.js
- **Database**: MySQL 8
- **Package management**: uv (backend), npm (frontend)
