# Velpos Deploy Guide

> Machine-readable setup guide. Follow each section in order.
> For Claude Code: execute commands exactly as shown, verify each step before proceeding.

## Quick Start

```bash
git clone git@github.com:Jxin-Cai/velpos.git
cd velpos

# Interactive (asks dev or prod)
./setup.sh

# Or specify directly
./setup.sh dev    # Development
./setup.sh prod   # Production
```

The `setup.sh` script handles prerequisite checks, environment configuration, and service startup automatically. The sections below describe the manual process for reference and troubleshooting.

---

## Prerequisites

### All Modes

| Tool | Version | Check command | Install |
|------|---------|---------------|---------|
| Docker | Any recent | `docker --version` | https://docs.docker.com/get-docker/ |
| Docker Compose | V2 | `docker compose version` | Included with Docker Desktop |

### Dev Mode Only

| Tool | Version | Check command | Install |
|------|---------|---------------|---------|
| Python | >= 3.11 | `python3 -c 'import sys; print(sys.version_info[:2])'` | https://www.python.org/downloads/ |
| uv | Any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | >= 18 | `node -v` | https://nodejs.org/ |
| npm | Any | `npm -v` | Comes with Node.js |
| Claude CLI | Any | `claude --version` | `npm install -g @anthropic-ai/claude-code` |

Verify Docker daemon is running:

```bash
docker info > /dev/null 2>&1 && echo "Docker OK" || echo "Docker daemon not running"
```

---

## Dev Mode Setup

Dev mode runs MySQL in Docker. Backend and frontend run on the host machine, managing host filesystem paths directly.

### Step 1: Environment

```bash
cp build/dev/.env.example build/dev/.env
```

The defaults work out of the box. Key variables:

| Variable | Default | Notes |
|----------|---------|-------|
| `MYSQL_ROOT_PASSWORD` | `root123456` | |
| `MYSQL_DATABASE` | `velpos` | |
| `MYSQL_HOST_PORT` | `3307` | MySQL port on host |
| `DATABASE_URL` | `mysql+aiomysql://root:root123456@localhost:3307/velpos` | Must match MySQL settings |
| `BACKEND_PORT` | `8083` | |
| `FRONTEND_PORT` | `3000` | |
| `CLAUDE_CLI_PATH` | *(auto-detected)* | Only set if `claude` is not in PATH |
| `PROJECTS_ROOT_DIR` | `~/claude-projects` | Project workspace directory |

### Step 2: Start

```bash
build/dev/start.sh start
```

This command:
1. Starts MySQL container via Docker Compose
2. Waits for MySQL to be healthy
3. Syncs backend Python dependencies (`uv sync`)
4. Starts backend with `uv run uvicorn main:app --reload`
5. Installs frontend dependencies if needed (`npm install`)
6. Starts frontend with `npm run dev`
7. Tails backend logs

### Step 3: Verify

```bash
# Backend health
curl -sf http://localhost:8083/api/health && echo " OK" || echo " FAILED"

# Frontend
curl -sf http://localhost:3000 > /dev/null && echo "Frontend OK" || echo "Frontend FAILED"

# MySQL
docker compose -f build/dev/docker-compose.yml exec -T mysql mysqladmin ping -h localhost -uroot -proot123456
```

Expected: all three return successfully.

Access points:
- Frontend: http://localhost:3000
- API Docs: http://localhost:8083/docs

### Service Management

```bash
build/dev/start.sh stop      # Stop all (including MySQL container)
build/dev/start.sh restart   # Restart all
build/dev/start.sh status    # Show running state
build/dev/start.sh logs      # Tail backend logs
```

---

## Prod Mode Setup

Prod mode runs everything in Docker: MySQL + backend + frontend (nginx). Claude Code CLI is installed inside the backend container.

### Step 1: Environment

```bash
cp build/prod/.env.example build/prod/.env
```

Edit `build/prod/.env` — two values must be changed:

| Variable | Action | Example |
|----------|--------|---------|
| `ANTHROPIC_API_KEY` | **Required.** Replace `sk-ant-xxx` with your real key | `sk-ant-api03-...` |
| `MYSQL_ROOT_PASSWORD` | **Recommended.** Replace `changeme` with a strong password | `MyStr0ngP@ss!` |
| `APP_PORT` | Optional. Default `80` | `8080` |
| `PROJECTS_HOST_DIR` | Optional. Default `/tmp/agent_projects` | `/home/user/projects` |

Auto-configured by docker-compose (do not set manually):
- `DATABASE_URL` — inter-container MySQL connection
- `CLAUDE_CLI_PATH` — `/usr/local/bin/claude` inside backend container
- `PROJECTS_ROOT_DIR` — `/data/projects` inside container

**Important:** `PROJECTS_HOST_DIR` must be an absolute path. Docker does not expand `~`.

### Step 2: Create projects directory

```bash
mkdir -p /tmp/agent_projects   # or your configured PROJECTS_HOST_DIR
```

### Step 3: Build and start

```bash
docker compose -f build/prod/docker-compose.yml up --build -d
```

First run takes several minutes (image pulls + build).

### Step 4: Verify

```bash
# Check container status
docker compose -f build/prod/docker-compose.yml ps

# Expected: all three services show "healthy"
# mysql     — healthy
# backend   — healthy
# frontend  — healthy (or running)

# Backend health (from inside Docker network)
docker compose -f build/prod/docker-compose.yml exec backend curl -sf http://localhost:8083/api/health

# Frontend (from host)
curl -sf http://localhost:80 > /dev/null && echo "App OK" || echo "App FAILED"
```

Access point: http://localhost (or your configured `APP_PORT`)

### Logs and Management

```bash
# View logs
docker compose -f build/prod/docker-compose.yml logs -f
docker compose -f build/prod/docker-compose.yml logs -f backend    # backend only

# Stop
docker compose -f build/prod/docker-compose.yml down

# Stop and remove volumes (destructive — deletes database)
docker compose -f build/prod/docker-compose.yml down -v

# Rebuild after code changes
docker compose -f build/prod/docker-compose.yml up --build -d
```

---

## First Run Configuration

After services are running, configure the web UI:

1. Open the application in a browser
2. Click the **gear icon** (top bar) to open Settings
3. Create a **Channel Profile**: Add Channel → fill Name, Host (`https://api.anthropic.com`), API Key → Create → Activate
4. Create a **project** from a local directory
5. Create a **session**, choose model and permission mode, start working

---

## Port Reference

| Service | Dev | Prod |
|---------|-----|------|
| Frontend | 3000 | 80 (nginx) |
| Backend API | 8083 | 8083 (internal, proxied via nginx) |
| API Docs | 8083/docs | Not exposed (access via nginx /api/) |
| MySQL | 3307 (host) | 3306 (internal only) |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `docker: command not found` | Docker not installed | Install from https://docs.docker.com/get-docker/ |
| `Cannot connect to the Docker daemon` | Docker daemon not running | Start Docker Desktop or `sudo systemctl start docker` |
| Backend won't start in dev | `DATABASE_URL` mismatch or MySQL not ready | Check `build/dev/.env`, ensure MySQL container is running: `docker ps` |
| `claude: command not found` (dev) | Claude CLI not installed | `npm install -g @anthropic-ai/claude-code` |
| Port already in use | Another process on the port | Kill it: `lsof -ti:8083 \| xargs kill` or change port in `.env` |
| Frontend blank page (prod) | nginx not proxying correctly | Check `docker compose -f build/prod/docker-compose.yml logs frontend` |
| `ANTHROPIC_API_KEY` error (prod) | Placeholder not replaced | Edit `build/prod/.env`, set real API key |
| MySQL connection refused | Container still starting | Wait 10-20s, check: `docker compose -f build/dev/docker-compose.yml ps` |
| `uv: command not found` | uv not installed | `curl -LsSf https://astral.sh/uv/install.sh \| sh` then restart shell |
| PROJECTS_HOST_DIR with `~` (prod) | Docker doesn't expand tilde | Use absolute path in `build/prod/.env` |
