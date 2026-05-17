#!/usr/bin/env bash
#
# Velpos — One-Click Setup
#
# Usage:
#   ./setup.sh              # Interactive: choose dev or prod
#   ./setup.sh dev          # Development mode (MySQL in Docker, backend+frontend on host)
#   ./setup.sh prod         # Production mode (full Docker stack)
#   ./setup.sh stop [dev|prod]   # Stop services
#   ./setup.sh status       # Show service status
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEV_DIR="$SCRIPT_DIR/build/dev"
PROD_DIR="$SCRIPT_DIR/build/prod"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

trap 'echo ""; error "Setup interrupted."; exit 1' INT TERM

# ── Helpers ──

command_exists() {
    command -v "$1" &>/dev/null
}

sed_inplace() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

get_env_value() {
    local file="$1" key="$2"
    grep "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2-
}

is_interactive() {
    [ -t 0 ]
}

# ── Prerequisite Checks ──

check_docker() {
    local missing=0

    if command_exists docker; then
        if ! docker info &>/dev/null; then
            error "Docker is installed but the daemon is not running."
            echo "  Start Docker Desktop or run: sudo systemctl start docker"
            missing=1
        else
            ok "Docker $(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
        fi
    else
        error "Docker not found"
        echo "  Install: https://docs.docker.com/get-docker/"
        missing=1
    fi

    if docker compose version &>/dev/null 2>&1; then
        ok "Docker Compose $(docker compose version --short 2>/dev/null || echo '(available)')"
    elif command_exists docker-compose; then
        warn "docker-compose (V1) detected. Please upgrade to Docker Compose V2."
        echo "  See: https://docs.docker.com/compose/install/"
        missing=1
    else
        error "Docker Compose not found"
        echo "  Install: https://docs.docker.com/compose/install/"
        missing=1
    fi

    return $missing
}

check_dev_prereqs() {
    local missing=0

    echo -e "${BOLD}Checking prerequisites...${NC}"
    echo ""

    check_docker || missing=1

    # Python >= 3.11
    if command_exists python3; then
        local py_ver py_major py_minor
        py_ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        py_major=$(echo "$py_ver" | cut -d. -f1)
        py_minor=$(echo "$py_ver" | cut -d. -f2)
        if [ "$py_major" -ge 3 ] && [ "$py_minor" -ge 11 ]; then
            ok "Python $py_ver"
        else
            error "Python $py_ver found, but >= 3.11 is required"
            echo "  Install: https://www.python.org/downloads/"
            missing=1
        fi
    else
        error "Python 3 not found"
        echo "  Install: https://www.python.org/downloads/"
        missing=1
    fi

    # uv
    if command_exists uv; then
        ok "uv $(uv --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo '(available)')"
    else
        warn "uv not found"
        if is_interactive && command_exists curl; then
            echo -n "  Install uv now? [Y/n] "
            read -r yn
            if [ -z "$yn" ] || [ "$yn" = "y" ] || [ "$yn" = "Y" ]; then
                curl -LsSf https://astral.sh/uv/install.sh | sh
                export PATH="$HOME/.local/bin:$PATH"
                if command_exists uv; then
                    ok "uv installed successfully"
                else
                    error "uv installation failed"
                    missing=1
                fi
            else
                error "uv is required for dev mode"
                echo "  Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
                missing=1
            fi
        else
            error "uv is required for dev mode"
            echo "  Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
            missing=1
        fi
    fi

    # Node.js >= 18
    if command_exists node; then
        local node_ver node_major
        node_ver=$(node -v | tr -d 'v')
        node_major=$(echo "$node_ver" | cut -d. -f1)
        if [ "$node_major" -ge 18 ]; then
            ok "Node.js $node_ver"
        else
            error "Node.js $node_ver found, but >= 18 is required"
            echo "  Install: https://nodejs.org/"
            missing=1
        fi
    else
        error "Node.js not found"
        echo "  Install: https://nodejs.org/"
        missing=1
    fi

    # npm
    if command_exists npm; then
        ok "npm $(npm --version 2>/dev/null)"
    else
        error "npm not found (usually comes with Node.js)"
        missing=1
    fi

    # Claude Code CLI
    if command_exists claude; then
        ok "Claude CLI ($(command -v claude))"
    else
        warn "Claude Code CLI not found"
        if is_interactive && command_exists npm; then
            echo -n "  Install Claude Code CLI via npm? [Y/n] "
            read -r yn
            if [ -z "$yn" ] || [ "$yn" = "y" ] || [ "$yn" = "Y" ]; then
                npm install -g @anthropic-ai/claude-code
                if command_exists claude; then
                    ok "Claude CLI installed successfully"
                else
                    error "Claude CLI installation failed"
                    missing=1
                fi
            else
                error "Claude Code CLI is required for dev mode"
                echo "  Install: npm install -g @anthropic-ai/claude-code"
                missing=1
            fi
        else
            error "Claude Code CLI is required for dev mode"
            echo "  Install: npm install -g @anthropic-ai/claude-code"
            missing=1
        fi
    fi

    echo ""
    if [ "$missing" -ne 0 ]; then
        error "Missing prerequisites. Please install them and try again."
        exit 1
    fi
    ok "All prerequisites satisfied!"
    echo ""
}

# ── Environment Setup ──

ensure_env() {
    local dir="$1"
    local env_file="$dir/.env"
    local example_file="$dir/.env.example"

    if [ -f "$env_file" ]; then
        ok "Environment file exists: $env_file"
    elif [ -f "$example_file" ]; then
        cp "$example_file" "$env_file"
        ok "Created $env_file from .env.example"
    else
        error "No .env.example found in $dir"
        exit 1
    fi
}

prompt_and_set_env() {
    local env_file="$1" key="$2" placeholder="$3" prompt_msg="$4"
    local current_value
    current_value=$(get_env_value "$env_file" "$key")

    if [ "$current_value" = "$placeholder" ]; then
        if is_interactive; then
            echo ""
            warn "$key is not configured (placeholder value: $placeholder)"
            echo -n "  $prompt_msg "
            read -r new_value
            if [ -n "$new_value" ]; then
                sed_inplace "s|^${key}=.*|${key}=${new_value}|" "$env_file"
                ok "$key configured"
            else
                error "$key is required. Please edit $env_file manually."
                exit 1
            fi
        else
            error "$key is set to placeholder '$placeholder'. Edit $env_file before running."
            exit 1
        fi
    fi
}

prompt_or_generate_password() {
    local env_file="$1" key="$2" placeholder="$3"
    local current_value
    current_value=$(get_env_value "$env_file" "$key")

    if [ "$current_value" = "$placeholder" ]; then
        if is_interactive; then
            echo ""
            warn "$key is set to '$placeholder'"
            echo -n "  Enter a MySQL root password (or press Enter to auto-generate): "
            read -r new_value
            if [ -z "$new_value" ]; then
                if command_exists openssl; then
                    new_value=$(openssl rand -base64 16 | tr -d '/+=')
                else
                    new_value=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 16)
                fi
                info "Auto-generated password: $new_value"
            fi
            sed_inplace "s|^${key}=.*|${key}=${new_value}|" "$env_file"
            ok "$key configured"
        else
            warn "$key is set to '$placeholder'. Consider changing it in $env_file."
        fi
    fi
}

expand_tilde_in_env() {
    local env_file="$1" key="$2"
    local current_value
    current_value=$(get_env_value "$env_file" "$key")

    if [[ "$current_value" == "~"* ]]; then
        local expanded="${current_value/#\~/$HOME}"
        warn "$key contains '~' which Docker does not expand."
        info "Replacing with absolute path: $expanded"
        sed_inplace "s|^${key}=.*|${key}=${expanded}|" "$env_file"
    fi
}

ensure_projects_dir() {
    local env_file="$1" key="$2"
    local dir_path
    dir_path=$(get_env_value "$env_file" "$key")

    if [ -n "$dir_path" ]; then
        if [ ! -d "$dir_path" ]; then
            mkdir -p "$dir_path"
            ok "Created projects directory: $dir_path"
        fi
    fi
}

# ── Wait for Docker Health ──

wait_for_service() {
    local compose_file="$1" service="$2" max_wait="${3:-120}"
    local elapsed=0

    info "Waiting for $service to be healthy..."
    while [ $elapsed -lt "$max_wait" ]; do
        local health
        health=$(docker compose -f "$compose_file" ps "$service" --format '{{.Health}}' 2>/dev/null || echo "unknown")
        if [ "$health" = "healthy" ]; then
            ok "$service is healthy"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done

    error "$service did not become healthy within ${max_wait}s"
    info "Check logs: docker compose -f $compose_file logs $service"
    return 1
}

# ── Dev Mode ──

do_dev() {
    ensure_env "$DEV_DIR"
    exec "$DEV_DIR/start.sh" start
}

# ── Prod Mode ──

do_prod() {
    echo -e "${BOLD}${CYAN}"
    echo " __     __    _                  "
    echo " \ \   / /___| |_ __   ___  ___ "
    echo "  \ \ / // _ \ | '_ \ / _ \/ __|"
    echo "   \ V /|  __/ | |_) | (_) \__ \\"
    echo "    \_/  \___|_| .__/ \___/|___/"
    echo "               |_|              "
    echo -e "${NC}"
    echo -e "  ${GREEN}[ PRODUCTION MODE ]${NC}"
    echo ""

    echo -e "${BOLD}Checking prerequisites...${NC}"
    echo ""
    check_docker || {
        error "Docker is required for production mode."
        exit 1
    }
    echo ""

    ensure_env "$PROD_DIR"

    local env_file="$PROD_DIR/.env"

    prompt_and_set_env "$env_file" "ANTHROPIC_API_KEY" "sk-ant-xxx" "Enter your Anthropic API key:"
    prompt_or_generate_password "$env_file" "MYSQL_ROOT_PASSWORD" "changeme"
    expand_tilde_in_env "$env_file" "PROJECTS_HOST_DIR"
    ensure_projects_dir "$env_file" "PROJECTS_HOST_DIR"

    echo ""
    info "Building and starting Docker stack..."
    info "This may take several minutes on first run (pulling images + building)."
    echo ""

    docker compose -f "$PROD_DIR/docker-compose.yml" up --build -d

    echo ""
    wait_for_service "$PROD_DIR/docker-compose.yml" "mysql" 60
    wait_for_service "$PROD_DIR/docker-compose.yml" "backend" 120
    wait_for_service "$PROD_DIR/docker-compose.yml" "frontend" 30

    local app_port
    app_port=$(get_env_value "$env_file" "APP_PORT")
    app_port="${app_port:-80}"

    echo ""
    echo -e "${BOLD}All services started!${NC}"
    echo -e "  Application:  ${GREEN}http://localhost:${app_port}${NC}"
    echo ""
    echo -e "  View logs:    ${CYAN}docker compose -f build/prod/docker-compose.yml logs -f${NC}"
    echo -e "  Stop:         ${CYAN}./setup.sh stop prod${NC}"
    echo ""
}

# ── Stop ──

is_dev_running() {
    local pid_dir="$SCRIPT_DIR/.pids"
    if [ -f "$pid_dir/backend.pid" ] && kill -0 "$(cat "$pid_dir/backend.pid")" 2>/dev/null; then
        return 0
    fi
    if docker compose -f "$DEV_DIR/docker-compose.yml" ps --status running 2>/dev/null | grep -q mysql; then
        return 0
    fi
    return 1
}

is_prod_running() {
    docker compose -f "$PROD_DIR/docker-compose.yml" ps --status running 2>/dev/null | grep -qE 'backend|frontend|mysql'
}

do_stop() {
    local mode="${1:-}"

    case "$mode" in
        dev)
            info "Stopping dev services..."
            "$DEV_DIR/start.sh" stop
            ;;
        prod)
            info "Stopping prod services..."
            docker compose -f "$PROD_DIR/docker-compose.yml" down
            ok "Prod services stopped"
            ;;
        "")
            local stopped=0
            if is_dev_running; then
                info "Dev services detected, stopping..."
                "$DEV_DIR/start.sh" stop
                stopped=1
            fi
            if is_prod_running; then
                info "Prod services detected, stopping..."
                docker compose -f "$PROD_DIR/docker-compose.yml" down
                ok "Prod services stopped"
                stopped=1
            fi
            if [ "$stopped" -eq 0 ]; then
                info "No running services found."
            fi
            ;;
        *)
            error "Unknown mode: $mode"
            echo "Usage: $0 stop [dev|prod]"
            exit 1
            ;;
    esac
}

# ── Status ──

do_status() {
    echo -e "${BOLD}Service Status:${NC}"
    echo ""

    echo -e "  ${BOLD}[Dev]${NC}"
    if is_dev_running; then
        "$DEV_DIR/start.sh" status 2>/dev/null || echo -e "    ${GREEN}RUNNING${NC} (some services active)"
    else
        echo -e "    ${RED}STOPPED${NC}"
    fi

    echo ""
    echo -e "  ${BOLD}[Prod]${NC}"
    if is_prod_running; then
        docker compose -f "$PROD_DIR/docker-compose.yml" ps 2>/dev/null
    else
        echo -e "    ${RED}STOPPED${NC}"
    fi
    echo ""
}

# ── Interactive Menu ──

do_interactive() {
    echo -e "${BOLD}${CYAN}"
    echo " __     __    _                  "
    echo " \ \   / /___| |_ __   ___  ___ "
    echo "  \ \ / // _ \ | '_ \ / _ \/ __|"
    echo "   \ V /|  __/ | |_) | (_) \__ \\"
    echo "    \_/  \___|_| .__/ \___/|___/"
    echo "               |_|              "
    echo -e "${NC}"
    echo ""
    echo -e "${BOLD}Select deployment mode:${NC}"
    echo ""
    echo "  1) Development  — MySQL in Docker, backend+frontend on host"
    echo "  2) Production   — Full Docker stack (MySQL + backend + frontend/nginx)"
    echo "  q) Quit"
    echo ""
    echo -n "  Choice [1/2/q]: "
    read -r choice

    case "$choice" in
        1|dev)   do_dev  ;;
        2|prod)  do_prod ;;
        q|Q)     echo "Bye."; exit 0 ;;
        *)       error "Invalid choice: $choice"; exit 1 ;;
    esac
}

# ── Entry ──

case "${1:-}" in
    dev)     do_dev     ;;
    prod)    do_prod    ;;
    stop)    do_stop "${2:-}" ;;
    status)  do_status  ;;
    help|-h|--help)
        echo "Usage: $0 {dev|prod|stop|status|help}"
        echo ""
        echo "Commands:"
        echo "  dev          Start development environment"
        echo "  prod         Start production environment"
        echo "  stop [mode]  Stop services (auto-detects or specify dev/prod)"
        echo "  status       Show service status"
        echo "  help         Show this help"
        echo ""
        echo "Run without arguments for interactive mode."
        ;;
    "")      do_interactive ;;
    *)
        error "Unknown command: $1"
        echo "Usage: $0 {dev|prod|stop|status|help}"
        exit 1
        ;;
esac
