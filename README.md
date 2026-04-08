<div align="center">

# Velpos

**Package AI agents with identity, SOPs, and tools — on top of Claude Code.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D.svg?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Claude](https://img.shields.io/badge/Claude_Code-Agent_SDK-D97757.svg)](https://github.com/anthropics/claude-code-sdk-python)

[中文文档](./README_zh.md)&ensp;|&ensp;[License](./LICENSE)&ensp;|&ensp;[Code of Conduct](./CODE_OF_CONDUCT.md)

</div>

<br/>

Velpos is a web console for [Claude Code](https://github.com/anthropics/claude-code) built on the [Agent SDK](https://github.com/anthropics/claude-code-sdk-python). Its core value is **agent packaging** — turning reusable AI assistants into configurable units that bundle **identity definition**, **plugin-powered SOPs**, and **tool access** behind a visual interface.

This makes it much easier for **non-technical users** to build and operate multi-agent AI assistants — no hand-written prompts, no manual tool wiring, no fragile command chains.

<br/>

## Table of Contents

- [Why Agent Packaging](#why-agent-packaging)
- [Highlights](#highlights)
- [Quick Start](#quick-start)
- [First Run Setup](#first-run-setup)
- [Usage Overview](#usage-overview)
- [Production Deployment](#production-deployment)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Contributing](#contributing)
- [License](#license)

<br/>

## Why Agent Packaging

Most AI assistant setups break down because the real operating knowledge is scattered across prompts, tool permissions, plugin configs, and undocumented workflow habits.

Velpos packages those moving parts into something reusable:

| Layer | What it does |
|---|---|
| **Identity** | Define what an agent is, what role it plays, and how it should behave |
| **SOP** | Encode repeatable workflows so the agent follows a stable process — not ad-hoc prompting |
| **Tools** | Expose the right capabilities through plugins — end users never assemble the toolchain |
| **Reuse** | Apply the same packaged agent across projects, teams, and scenarios with less drift |

This is especially useful for teams where the operators are **product owners, support staff, domain experts, or founders** — people who need outcomes, not prompt engineering.

<br/>

## Highlights

### Agent Packaging

- **Packaged agents** — bundle identity, role boundaries, and behavior expectations into a reusable unit
- **Plugin-powered SOPs** — turn repeatable workflows into stable operating procedures through plugins
- **Tool encapsulation** — hide low-level tool wiring so end users work at the task level
- **Multi-agent collaboration** — combine packaged agents for specialized roles, handoffs, and team workflows

### Platform Capabilities

- **Project workspaces** — organize sessions by directory with isolated Claude Code working areas
- **Streaming chat** — real-time WebSocket with Markdown rendering and code highlighting
- **Built-in terminal** — run commands inside the current project directory
- **Plugin management** — install / uninstall Claude Code MCP plugins
- **Memory management** — edit `CLAUDE.md` and memory files from the UI
- **Git management** — configure identity and SSH keys
- **IM integrations** — connect Lark, WeChat, QQ, and OpenIM for two-way sync
- **Channel profiles** — manage multiple API keys, hosts, and model mappings
- **Settings center** — manage Claude Code core settings in one place

<br/>

## Quick Start

### Prerequisites

| Dependency | Version |
|---|---|
| [Node.js](https://nodejs.org/) | >= 18 |
| [Python](https://www.python.org/) | >= 3.11, < 3.13 |
| [Docker](https://www.docker.com/) | with Compose |
| [uv](https://docs.astral.sh/uv/) | latest |
| [Claude Code CLI](https://github.com/anthropics/claude-code) | `claude` available in PATH |

### 1. Clone

```bash
git clone git@github.com:Jxin-Cai/velpos.git
cd velpos
```

### 2. Configure

```bash
cp build/dev/.env.example build/dev/.env
cp backend/.env.example backend/.env
```

<details>
<summary><b>Environment variables reference</b></summary>

#### `build/dev/.env`

| Variable | Default | Description |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | `root123456` | MySQL root password |
| `MYSQL_DATABASE` | `velpos` | Database name |
| `MYSQL_HOST_PORT` | `3307` | Exposed MySQL port |
| `BACKEND_PORT` | `8083` | Backend port |
| `FRONTEND_PORT` | `3000` | Frontend port |
| `CLAUDE_CLI_PATH` | `/usr/local/bin/claude` | Path to Claude CLI binary |
| `CLAUDE_PERMISSION_MODE` | `acceptEdits` | Default permission mode |
| `DEFAULT_MODEL` | `claude-opus-4-6` | Default model |
| `PROJECTS_ROOT_DIR` | `~/claude-projects` | Root directory for managed projects |
| `CORS_ALLOW_ORIGINS` | `*` | Allowed browser origins |

#### `backend/.env`

```env
DATABASE_URL=mysql+aiomysql://root:yourpassword@localhost:3307/velpos
```

</details>

### 3. Start

```bash
build/dev/start.sh start
```

The script will start MySQL (Docker), backend (`uv run uvicorn`), and frontend (`npm run dev`). Database migrations run automatically on backend startup.

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API Docs | http://localhost:8083/docs |

<details>
<summary><b>Service management commands</b></summary>

```bash
build/dev/start.sh start     # Start all services
build/dev/start.sh stop      # Stop all services
build/dev/start.sh restart   # Restart all services
build/dev/start.sh status    # Show status
build/dev/start.sh logs      # Tail backend logs
```

</details>

<br/>

## First Run Setup

> **Important:** After starting services, you must configure settings in the web UI before Claude Code sessions work.

**1.** Click the **gear icon** in the top bar to open Settings.

**2.** Create a **Channel Profile** (API endpoint + key + model mapping):

&emsp;&emsp;Add Channel &#8594; fill Name, Host, API Key &#8594; Create &#8594; Activate

**3.** Review **Settings Configuration**:

<details>
<summary><b>Available settings</b></summary>

| Setting | Description |
|---|---|
| **Permission Mode** | Default / Accept Edits / Plan / Bypass |
| **Completed Onboarding** | Skip onboarding UI |
| **Effort Level** | Low / Medium / High reasoning effort |
| **Skip Dangerous Mode Prompt** | Skip extra confirmation for bypass modes |
| **Disable Non-Essential Traffic** | Disable non-core network traffic |
| **Agent Teams** | Experimental multi-agent support |
| **Tool Search** | Enable MCP tool search and dynamic loading |
| **Attribution** | Configure attribution text for commits and PRs |

</details>

**4.** Create a project, create a session, **load your packaged agents**, and start working.

<br/>

## Usage Overview

| Area | What you can do |
|---|---|
| **Projects & Sessions** | Create projects from the sidebar, point each to a local directory, manage sessions |
| **Chat** | Send prompts, paste/drag images, view streamed Markdown with code highlighting |
| **Models & Permissions** | Switch models from the top bar, choose permission modes for autonomy control |
| **Terminal** | Open the built-in terminal, run commands in the project directory |
| **Plugins & Agents** | Install MCP plugins, load project-level packaged agents |
| **Memory** | Edit `CLAUDE.md` and memory files directly in the UI |
| **Git** | Manage global Git identity and SSH keys |
| **IM Integration** | Bind sessions to **Lark**, **WeChat**, **QQ**, or **OpenIM** for two-way sync |

<br/>

## Production Deployment

Full Docker deployment under `build/prod`:

```bash
cp build/prod/.env.example build/prod/.env
cd build/prod
docker compose up --build -d
```

<details>
<summary><b>Production environment variables</b></summary>

| Variable | Description |
|---|---|
| `APP_PORT` | Public port |
| `MYSQL_ROOT_PASSWORD` | MySQL password |
| `CLAUDE_CLI_PATH` | Claude CLI path inside the container |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `PROJECTS_HOST_DIR` | Host directory mounted into the container |

</details>

> Production also requires initial configuration via the web UI after the stack is running.

<br/>

## Architecture

```text
velpos/
├── backend/                  # Python FastAPI
│   ├── domain/               # Domain layer — pure business logic
│   ├── application/          # Application services — use case orchestration
│   ├── infr/                 # Infrastructure — repos, clients, adapters
│   ├── ohs/                  # Open Host Service — REST + WebSocket
│   └── alembic/              # Database migrations
├── frontend/                 # Vue 3 + Vite
│   └── src/
│       ├── app/              # Shell, router, bootstrap
│       ├── pages/            # Route-level pages
│       ├── features/         # Isolated UI features
│       ├── entities/         # Core business data
│       └── shared/           # Utilities, HTTP/WS clients
└── build/
    ├── dev/                  # Dev: Docker MySQL + host services
    └── prod/                 # Prod: full Docker stack
```

The backend follows a **DDD four-layer** architecture. The frontend uses a **feature-sliced** structure.

<br/>

## Tech Stack

| Layer | Technologies |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy (async), Alembic, Claude Agent SDK, aiomysql |
| Frontend | Vue 3, Vite, marked, highlight.js |
| Database | MySQL 8 |
| Package Mgmt | uv (backend), npm (frontend) |

<br/>

## Contributing

Please read the [Code of Conduct](./CODE_OF_CONDUCT.md) before participating.

If you plan to contribute significant changes, **open an issue first** to discuss direction and scope. We welcome bug reports, feature requests, and pull requests.

## License

Licensed under the [Apache License 2.0](./LICENSE).

Copyright 2026 jxin
