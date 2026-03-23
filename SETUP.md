# SETUP.md — Velpos Setup Guide (for Claude Code)

This file guides Claude Code through setting up the Velpos development environment.
Follow each section in order. Ask the user when choices are needed.

## Prerequisites Check

Before starting, verify these tools are installed. If any are missing, install them.

> **Note:** For **prod mode** (full Docker), only Docker is required — Python, uv, Node.js, and Claude CLI are all installed inside the container automatically. The prerequisites below (sections 2-5) are only needed for **dev mode**.

### 1. Docker & Docker Compose

```bash
# Check if installed
docker --version && docker compose version
```

**Install if missing:**
- macOS: `brew install --cask docker` (or download Docker Desktop from https://www.docker.com/products/docker-desktop/)
- Linux (Ubuntu/Debian):
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER
  ```

### 2. Python 3.11+

```bash
python3 --version  # Must be >= 3.11
```

**Install if missing:**
- macOS: `brew install python@3.12`
- Linux: `sudo apt install python3.12 python3.12-venv`

### 3. uv (Python package manager)

```bash
uv --version
```

**Install if missing:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 4. Node.js 22+ & npm

```bash
node --version  # Must be >= 22
npm --version
```

**Install if missing:**
- macOS: `brew install node@22`
- Linux: 
  ```bash
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt install -y nodejs
  ```
- Or use nvm: `nvm install 22`

### 5. Claude Code CLI

```bash
claude --version
```

**Install if missing:**
```bash
npm install -g @anthropic-ai/claude-code
```

After installation, run `claude` once to complete authentication.

---

## Environment Setup

**Ask the user:** "Do you want to set up for **dev** (local development) or **prod** (Docker production)?"

### Option A: Dev Mode

Dev mode runs MySQL in Docker, backend and frontend on the host machine.

#### Step 1: Copy environment files

```bash
cp build/dev/.env.example build/dev/.env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

#### Step 2: Configure environment

Edit `build/dev/.env`:
- `CLAUDE_CLI_PATH` — set to the output of `which claude`
- `MYSQL_ROOT_PASSWORD` — change if desired
- `PROJECTS_ROOT_DIR` — directory where user projects will be stored (default: `~/claude-projects`)

Edit `backend/.env`:
- `DATABASE_URL` — must match the MySQL password set above. Format: `mysql+aiomysql://root:<password>@localhost:3307/velpos`
- `CLAUDE_CLI_PATH` — same as above

#### Step 3: Install dependencies

```bash
# Backend Python dependencies
cd backend && uv sync && cd ..

# Frontend Node dependencies
cd frontend && npm install && cd ..
```

#### Step 4: Start all services

```bash
build/dev/start.sh start
```

This starts MySQL (Docker), backend (port 8083), and frontend (port 3000).

**Verify:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8083/docs
- Health check: `curl http://localhost:8083/api/health`

#### Dev service management

```bash
build/dev/start.sh stop      # Stop all
build/dev/start.sh restart   # Restart all
build/dev/start.sh status    # Check status
build/dev/start.sh logs      # Tail backend logs
```

---

### Option B: Prod Mode (Full Docker)

Prod mode runs everything in Docker containers (MySQL + backend + frontend/nginx).
Claude Code CLI is installed **inside the backend container** automatically — no need to install it on the host or map from host.

#### Step 1: Copy environment file

```bash
cp build/prod/.env.example build/prod/.env
```

#### Step 2: Configure environment

Edit `build/prod/.env`:
- `MYSQL_ROOT_PASSWORD` — use a strong password
- `ANTHROPIC_API_KEY` — your Anthropic API key (required for prod, used by container-internal Claude CLI)
- `APP_PORT` — host port to expose (default: 80)
- `PROJECTS_HOST_DIR` — host directory for project files (default: `~/.agent_projects`)

#### Step 3: Build and start

```bash
cd build/prod && docker compose up --build -d
```

**Verify:**
- Application: http://localhost (or custom `APP_PORT`)
- Logs: `cd build/prod && docker compose logs -f`

#### Stop

```bash
cd build/prod && docker compose down
```

---

## Ports Summary

| Service  | Dev        | Prod           |
|----------|------------|----------------|
| Frontend | 3000       | 80 (nginx)     |
| Backend  | 8083       | 8083 (internal)|
| MySQL    | 3307 (host)| 3306 (internal)|

## Troubleshooting

- **Backend won't start**: Check `DATABASE_URL` in `backend/.env` matches MySQL credentials
- **Claude queries fail**: Verify `CLAUDE_CLI_PATH` points to a valid `claude` binary, and `claude` is authenticated
- **Port conflict**: Change ports in `build/dev/.env` or kill the conflicting process
- **MySQL connection refused**: Wait a few seconds after `start.sh start`, or check `docker ps` to ensure the MySQL container is running
