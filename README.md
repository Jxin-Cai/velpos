<div align="center">

# Velpos

**Package AI agents with identity, SOPs, and tools — on top of Claude Code.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D.svg?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Claude](https://img.shields.io/badge/Claude_Code-Agent_SDK-D97757.svg)](https://github.com/anthropics/claude-code-sdk-python)

[中文文档](./README_zh.md)&ensp;|&ensp;[Demo Video](https://www.bilibili.com/video/BV1iEDhBuEVZ/)&ensp;|&ensp;[License](./LICENSE)&ensp;|&ensp;[Code of Conduct](./CODE_OF_CONDUCT.md)

</div>

<br/>

Velpos is a web console for [Claude Code](https://github.com/anthropics/claude-code) built on the [Agent SDK](https://github.com/anthropics/claude-code-sdk-python). Its core value is **agent packaging** — turning reusable AI assistants into configurable units that bundle **identity definition**, **plugin-powered SOPs**, and **tool access** behind a visual interface.

This makes it much easier for **non-technical users** to build and operate multi-agent AI assistants — no hand-written prompts, no manual tool wiring, no fragile command chains.

Over the past month, Velpos has evolved from a chat-style Claude Code wrapper into a **project operation console**: it can manage projects and sessions, run scheduled work, branch and compare parallel attempts, track task progress, review workspace history, operate through IM channels, and keep the whole workflow controllable from a browser.

<br/>

## Table of Contents

- [Why Agent Packaging](#why-agent-packaging)
- [Highlights](#highlights)
- [Recent Updates](#recent-updates)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Deployment](#deployment)
  - [Development](#development)
  - [Production](#production)
- [First Run Setup](#first-run-setup)
- [Usage Overview](#usage-overview)
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
- **Marketplace refresh** — update plugin marketplace metadata before installing packaged agents so projects use current tool definitions

### Project Operations

- **Project workspaces** — create projects from local directories, organize sessions by project, and keep Claude Code work scoped to the selected workspace
- **Streaming chat** — real-time WebSocket responses with Markdown rendering, code highlighting, permission requests, and user choices
- **Attachments** — send images/files into sessions and keep attachment records with the conversation
- **Task progress** — render `TodoWrite` progress inline, show run steps, and surface timeline events while Claude Code is working
- **Built-in terminal** — run commands inside the current project directory with a drawer-style terminal based on xterm
- **Workspace history** — inspect recent workspace changes, browse file versions, and compare message/code differences across branches
- **Memory management** — edit `CLAUDE.md`, memory files, and project memory entries from the UI
- **Settings center** — manage Claude Code settings, channel profiles, model mappings, permission modes, and user input preferences in one place

### Governance and Collaboration

- **Plugin management** — install / uninstall Claude Code MCP plugins from the browser
- **Git management** — configure identity and SSH keys for Claude Code project work
- **IM integrations** — connect Lark, WeChat, QQ, and OpenIM for two-way session sync
- **Project Clock** — schedule recurring project work, bind each run to a selected IM channel instance, auto-disconnect after completion, and optionally delete successful one-shot execution sessions
- **Parallel sessions** — branch a conversation into multiple sessions, optionally isolate each branch in a Git worktree, compare message/code differences, and ask Claude to analyze the trade-offs
- **Branch convergence** — keep one target session, delete the alternatives, and merge committed worktree changes back into the base branch with safety checks
- **Usage governance** — track token usage and budget policy state for session-level visibility
- **Evolution proposals** — capture improvement proposals and project evolution ideas as first-class records

<br/>

## Recent Updates

The April 2026 development cycle focused on making Velpos practical for day-to-day project operations:

| Area | What changed | How it helps users |
|---|---|---|
| Project setup | Development and production configuration were consolidated under `build/dev/.env` and `build/prod/.env`; dev startup now auto-detects `claude` from PATH | Fewer setup files, less manual configuration, easier first run |
| Session reliability | Session execution state is isolated per session, WebSocket connections are unified, and database commits release locks more promptly | Long-running sessions and multi-session switching are more stable |
| Task visibility | Inline `TodoWrite` rendering, task progress panel, run steps, and timeline events were added | Users can see what Claude Code is doing instead of waiting on a black box |
| Scheduling | Project Clock can run recurring tasks, route output to a chosen IM channel, auto-unbind sessions, and clean up successful one-shot sessions | Repetitive project operations can be delegated safely |
| Branching | Parallel session branches, optional worktree isolation, branch comparison, and convergence flows were added | Teams can explore multiple solutions and keep the winning branch |
| Workspace | Workspace panel now shows richer project history, file/version comparison, and session-aware Git branch display | Users can review what changed without leaving the browser |
| Memory and evolution | Project memory entries, `CLAUDE.md` revision flow, and evolution proposals were added | Project knowledge and improvement ideas become manageable artifacts |
| Input and shortcuts | Global shortcuts, session navigation, permission-mode cycling, hotkey hints, IME-safe input, and configurable Enter behavior were added | Faster keyboard-driven operation with fewer accidental sends |
| UI polish | Sidebar, dialogs, settings, terminal, notification, message list, and startup visuals were refined | The console feels more consistent and easier to operate |

<br/>

## Current Release: v0.2.0

v0.2.0 is the first formal release focused on project operations and branch governance:

- Packaged-agent workflow console on top of Claude Code Agent SDK
- Project/session management with streaming chat, attachments, model switching, permissions, and context tools
- IM channel instances for Lark, WeChat, QQ, and OpenIM with bidirectional session sync
- Scheduled project tasks with selected IM delivery channel, automatic unbind, and optional one-shot session cleanup
- Parallel session branching with optional worktree isolation and session-aware branch display
- Session comparison with message diff, Git diff summary, and Claude-ready analysis prompts
- Target-session convergence that deletes alternatives and safely merges committed worktree branches back to the base branch

<br/>

## Keyboard Shortcuts

Velpos provides a comprehensive keyboard shortcut system for efficient navigation and control.

### Global Shortcuts

| Shortcut | Action |
|---|---|
| `ESC` | Close the topmost dialog; if no dialog is open, cancel the running query |
| `Cmd/Ctrl + ↑` | Switch to the previous session |
| `Cmd/Ctrl + ↓` | Switch to the next session |
| `Cmd/Ctrl + P` | Open Settings |
| `Cmd/Ctrl + B` | Toggle sidebar collapse |
| `Cmd/Ctrl + K` | Toggle voice input |
| `Shift + Tab` | Cycle through permission modes |

### Chat Input

| Shortcut | Action |
|---|---|
| `Enter` | Send message in the default input mode |
| `Ctrl/Cmd + Enter` | Insert a new line in the default input mode; send message in the alternative mode |

Velpos also protects IME composition, so selecting Chinese/Japanese/Korean candidate text with `Enter` will not accidentally send the message.

### Workspace Panel

| Shortcut | Action |
|---|---|
| `← / →` | Browse file versions in compare mode |

### Dialogs

All dialogs (Settings, Scheduler, Memory, Evolution, Plugin, Agent, Git, IM) respond to `ESC` to close. The hotkey system uses priority-based dispatch — dialogs always take precedence over global handlers.

<br/>

## Deployment

```bash
git clone git@github.com:Jxin-Cai/velpos.git
cd velpos
```

### Development

> Only MySQL runs in Docker. Backend and frontend run on the **host machine**, managing **host filesystem** paths directly.

**Prerequisites:** Node.js >= 18, Python >= 3.11, Docker, [uv](https://docs.astral.sh/uv/), Claude Code CLI (`claude` in PATH)

<details>
<summary><b>Install prerequisites</b></summary>

```bash
# Docker — https://docs.docker.com/get-docker/

# Python >= 3.11 — https://www.python.org/downloads/
python3 --version

# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js >= 18 — https://nodejs.org/
node -v && npm -v

# Claude Code CLI
npm install -g @anthropic-ai/claude-code
```

The startup script will automatically check all prerequisites and display install instructions for anything missing.

</details>

**1. Configure**

```bash
cp build/dev/.env.example build/dev/.env
```

All dev settings are in this single file. `CLAUDE_CLI_PATH` is **auto-detected** from your PATH at startup — no need to set it manually unless `claude` is installed in a non-standard location.

<details>
<summary><b>build/dev/.env</b></summary>

| Variable | Default | Description |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | `root123456` | MySQL root password |
| `MYSQL_DATABASE` | `velpos` | Database name |
| `MYSQL_HOST_PORT` | `3307` | MySQL port exposed to host |
| `DATABASE_URL` | `mysql+aiomysql://root:root123456@localhost:3307/velpos` | Backend database connection (must match MySQL settings above) |
| `BACKEND_PORT` | `8083` | Backend port |
| `FRONTEND_PORT` | `3000` | Frontend port |
| `CLAUDE_CLI_PATH` | *(auto-detected)* | Override only if `claude` is not in PATH |
| `CLAUDE_PERMISSION_MODE` | `acceptEdits` | Default permission mode |
| `DEFAULT_MODEL` | `claude-opus-4-6` | Default model |
| `PROJECTS_ROOT_DIR` | `~/claude-projects` | Project root on the **host filesystem** |
| `CORS_ALLOW_ORIGINS` | `*` | Allowed browser origins |

</details>

**2. Start**

```bash
build/dev/start.sh start
```

This will start MySQL (Docker), backend (`uv run uvicorn` on host), and frontend (`npm run dev` on host). Database migrations run automatically on backend startup.

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API Docs | http://localhost:8083/docs |

<details>
<summary><b>Service management</b></summary>

```bash
build/dev/start.sh start     # Start all
build/dev/start.sh stop      # Stop all
build/dev/start.sh restart   # Restart all
build/dev/start.sh status    # Show status
build/dev/start.sh logs      # Tail backend logs
```

</details>

### Production

> Everything runs in Docker (MySQL + backend + frontend/nginx). The backend manages files inside the **container**. A host directory is bind-mounted for project data persistence.

**1. Configure**

```bash
cp build/prod/.env.example build/prod/.env
```

<details>
<summary><b>build/prod/.env — all-in-one configuration</b></summary>

| Variable | Default | Description |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | — | MySQL root password |
| `MYSQL_DATABASE` | `velpos` | Database name |
| `APP_PORT` | `80` | Public port exposed by nginx |
| `PROJECTS_HOST_DIR` | `~/.agent_projects` | Host directory mounted into the container as `/data/projects` |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `CLAUDE_PERMISSION_MODE` | `acceptEdits` | Default permission mode |
| `DEFAULT_MODEL` | `claude-opus-4-6` | Default model |

The following are **auto-configured** by docker-compose and do not need to be set:

| Variable | Fixed value | Reason |
|---|---|---|
| `DATABASE_URL` | `mysql+aiomysql://root:...@mysql:3306/velpos` | Inter-container networking |
| `CLAUDE_CLI_PATH` | `/usr/local/bin/claude` | Installed in the backend image |
| `PROJECTS_ROOT_DIR` | `/data/projects` | Container-internal mount point |

</details>

**2. Build and start**

```bash
cd build/prod
docker compose up --build -d
```

The stack includes MySQL, backend, and frontend (nginx). Access the UI at `http://localhost` (or the port you configured).

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

**4.** Create a project from a local directory or a new path under `PROJECTS_ROOT_DIR`.

**5.** Create a session, choose model and permission mode, **load your packaged agents**, and start working.

<br/>

## Usage Overview

### Core Features

![Velpos Core Features](./doc/features-en.png)

### User Journey

![Velpos User Journey](./doc/journey-en.png)

| Area | What you can do |
|---|---|
| **Projects & Sessions** | Create projects from the sidebar, point each to a local directory, create/import sessions, pin important projects, and switch sessions with shortcuts |
| **Chat** | Send prompts, paste/drag images, view streamed Markdown with code highlighting, respond to permission requests, and monitor inline task progress |
| **Models & Permissions** | Switch models from the top bar, choose permission modes for autonomy control, and cycle modes quickly with `Shift + Tab` |
| **Terminal** | Open the built-in terminal, run commands in the project directory, and keep terminal work alongside the chat context |
| **Workspace** | Review project history, inspect generated files, compare versions, and understand how session branches changed the code |
| **Plugins & Agents** | Install MCP plugins, refresh marketplace-backed packaged agents, and load project-level agents for specialized work |
| **Memory** | Edit `CLAUDE.md`, project memory entries, and revision records directly in the UI |
| **Git** | Manage global Git identity and SSH keys used by Claude Code sessions |
| **IM Integration** | Bind sessions to **Lark**, **WeChat**, **QQ**, or **OpenIM** for two-way sync and remote operation |
| **Scheduled tasks** | Run recurring project work, route notifications through a selected IM channel instance, auto-unbind after completion, and optionally clean up successful one-shot sessions |
| **Parallel branches** | Create multiple session branches, isolate them with worktrees, compare message/code diffs, ask Claude to analyze trade-offs, and converge on one target session |
| **Evolution** | Record project improvement proposals so recurring ideas do not disappear inside chat history |

### Typical Workflow

1. Start the dev stack with `build/dev/start.sh start` and open the web console.
2. Configure a channel profile and activate the model mapping you want to use.
3. Create or select a project directory, then create a Claude Code session.
4. Load packaged agents or plugins that match the task.
5. Work through chat while watching task progress, timeline events, terminal output, and workspace changes.
6. For uncertain tasks, create parallel branches, compare the results, and converge on the best session.
7. For repeatable work, create a Project Clock schedule and route updates to the right IM channel.

<br/>

## Architecture

![Velpos Architecture](./doc/architecture-en.png)

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
| Frontend | Vue 3, Vite, marked, highlight.js, DOMPurify, xterm.js |
| Database | MySQL 8 |
| Package Mgmt | uv (backend), npm (frontend) |

<br/>

## Contributing

Please read the [Code of Conduct](./CODE_OF_CONDUCT.md) before participating.

If you plan to contribute significant changes, **open an issue first** to discuss direction and scope. We welcome bug reports, feature requests, and pull requests.

## License

Licensed under the [Apache License 2.0](./LICENSE).

Copyright 2026 jxin
