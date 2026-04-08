#!/usr/bin/env bash
#
# Velpos - Dev 环境启动脚本
# Docker 仅运行 MySQL，后端和前端在宿主机运行
#
# 用法:
#   ./start.sh start    # 启动 MySQL + 后端 + 前端，tail 后端日志
#   ./start.sh stop     # 关闭全部
#   ./start.sh restart  # 重启全部
#   ./start.sh status   # 查看状态
#   ./start.sh logs     # 查看后端日志

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load .env from build/dev
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
PID_DIR="$ROOT_DIR/.pids"
LOG_DIR="$ROOT_DIR/.logs"

# Auto-detect Claude CLI if not set in .env
if [ -z "${CLAUDE_CLI_PATH:-}" ]; then
    if command -v claude &>/dev/null; then
        CLAUDE_CLI_PATH="$(command -v claude)"
        export CLAUDE_CLI_PATH
    else
        echo -e "\033[0;31m[ERROR]\033[0m Claude Code CLI not found."
        echo ""
        echo "  Install it with:  npm install -g @anthropic-ai/claude-code"
        echo "  More info:        https://github.com/anthropics/claude-code"
        echo ""
        echo "  Or set CLAUDE_CLI_PATH in build/dev/.env manually."
        exit 1
    fi
fi

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

BACKEND_PORT="${BACKEND_PORT:-8083}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# Colors
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

ensure_dirs() {
    mkdir -p "$PID_DIR" "$LOG_DIR"
}

is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$pid_file"
    fi
    return 1
}

start_mysql() {
    info "Starting MySQL via Docker..."
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

    info "Waiting for MySQL to be healthy..."
    local retries=0
    while ! docker compose -f "$SCRIPT_DIR/docker-compose.yml" exec -T mysql mysqladmin ping -h localhost -uroot -p"${MYSQL_ROOT_PASSWORD:-root123456}" > /dev/null 2>&1; do
        retries=$((retries + 1))
        if [ $retries -gt 30 ]; then
            error "MySQL failed to start"
            return 1
        fi
        sleep 2
    done
    ok "MySQL is ready"
}

start_backend() {
    if is_running "$BACKEND_PID_FILE"; then
        warn "Backend is already running (PID: $(cat "$BACKEND_PID_FILE"))"
        return 0
    fi

    info "Starting backend on port $BACKEND_PORT..."

    cd "$BACKEND_DIR"
    nohup uv run uvicorn main:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --reload \
        --log-level info \
        > "$BACKEND_LOG" 2>&1 &

    local pid=$!
    echo "$pid" > "$BACKEND_PID_FILE"

    local retries=0
    while ! curl -sf "http://localhost:$BACKEND_PORT/api/health" > /dev/null 2>&1; do
        retries=$((retries + 1))
        if [ $retries -gt 30 ]; then
            error "Backend failed to start. Check logs: $BACKEND_LOG"
            return 1
        fi
        sleep 1
    done

    ok "Backend started (PID: $pid) -> http://localhost:$BACKEND_PORT"
}

start_frontend() {
    if is_running "$FRONTEND_PID_FILE"; then
        warn "Frontend is already running (PID: $(cat "$FRONTEND_PID_FILE"))"
        return 0
    fi

    info "Starting frontend on port $FRONTEND_PORT..."

    cd "$FRONTEND_DIR"
    nohup npm run dev -- --host 0.0.0.0 > "$FRONTEND_LOG" 2>&1 &

    local pid=$!
    echo "$pid" > "$FRONTEND_PID_FILE"

    local retries=0
    while ! curl -sf "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; do
        retries=$((retries + 1))
        if [ $retries -gt 20 ]; then
            error "Frontend failed to start. Check logs: $FRONTEND_LOG"
            return 1
        fi
        sleep 1
    done

    ok "Frontend started (PID: $pid) -> http://localhost:$FRONTEND_PORT"
}

stop_process() {
    local name="$1"
    local pid_file="$2"

    if ! is_running "$pid_file"; then
        info "$name is not running"
        return 0
    fi

    local pid
    pid=$(cat "$pid_file")
    info "Stopping $name (PID: $pid)..."

    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true

    local retries=0
    while kill -0 "$pid" 2>/dev/null; do
        retries=$((retries + 1))
        if [ $retries -gt 10 ]; then
            warn "Force killing $name..."
            kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
            break
        fi
        sleep 0.5
    done

    rm -f "$pid_file"
    ok "$name stopped"
}

do_start() {
    ensure_dirs
    echo -e "${BOLD}${CYAN}"
    echo " __     __    _                  "
    echo " \ \   / /___| |_ __   ___  ___ "
    echo "  \ \ / // _ \ | '_ \ / _ \/ __|"
    echo "   \ V /|  __/ | |_) | (_) \__ \\"
    echo "    \_/  \___|_| .__/ \___/|___/"
    echo "               |_|              "
    echo -e "${NC}"
    echo -e "  ${YELLOW}[ DEV MODE ]${NC}"
    echo ""

    start_mysql
    start_backend
    start_frontend

    echo ""
    echo -e "${BOLD}All services started!${NC}"
    echo -e "  Frontend:  ${GREEN}http://localhost:$FRONTEND_PORT${NC}"
    echo -e "  Backend:   ${GREEN}http://localhost:$BACKEND_PORT${NC}"
    echo -e "  API Docs:  ${GREEN}http://localhost:$BACKEND_PORT/docs${NC}"
    echo -e "  MySQL:     ${GREEN}localhost:${MYSQL_HOST_PORT:-3307}${NC}"
    echo ""
    echo -e "Tailing backend logs... (${YELLOW}Ctrl+C${NC} to detach, services keep running)"
    echo -e "---"

    tail -f "$BACKEND_LOG"
}

do_stop() {
    ensure_dirs
    stop_process "Frontend" "$FRONTEND_PID_FILE"
    stop_process "Backend"  "$BACKEND_PID_FILE"

    lsof -ti:"$BACKEND_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
    lsof -ti:"$FRONTEND_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true

    info "Stopping MySQL..."
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" down
    ok "All services stopped"
}

do_restart() {
    info "Restarting all services..."
    do_stop
    sleep 1
    do_start
}

do_status() {
    ensure_dirs
    echo -e "${BOLD}Service Status:${NC}"
    echo ""

    # MySQL
    if docker compose -f "$SCRIPT_DIR/docker-compose.yml" ps --status running 2>/dev/null | grep -q mysql; then
        echo -e "  MySQL:     ${GREEN}RUNNING${NC} -> localhost:${MYSQL_HOST_PORT:-3307}"
    else
        echo -e "  MySQL:     ${RED}STOPPED${NC}"
    fi

    if is_running "$BACKEND_PID_FILE"; then
        echo -e "  Backend:   ${GREEN}RUNNING${NC} (PID: $(cat "$BACKEND_PID_FILE")) -> http://localhost:$BACKEND_PORT"
    else
        echo -e "  Backend:   ${RED}STOPPED${NC}"
    fi

    if is_running "$FRONTEND_PID_FILE"; then
        echo -e "  Frontend:  ${GREEN}RUNNING${NC} (PID: $(cat "$FRONTEND_PID_FILE")) -> http://localhost:$FRONTEND_PORT"
    else
        echo -e "  Frontend:  ${RED}STOPPED${NC}"
    fi

    echo ""
}

do_logs() {
    if [ ! -f "$BACKEND_LOG" ]; then
        error "No backend log found. Is the server running?"
        exit 1
    fi
    tail -f "$BACKEND_LOG"
}

# --- Entry ---
case "${1:-}" in
    start)   do_start   ;;
    stop)    do_stop    ;;
    restart) do_restart ;;
    status)  do_status  ;;
    logs)    do_logs    ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start    Start MySQL + backend + frontend, tail backend logs"
        echo "  stop     Stop all services (including MySQL)"
        echo "  restart  Restart all services"
        echo "  status   Show service status"
        echo "  logs     Tail backend logs"
        exit 1
        ;;
esac
