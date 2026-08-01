#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROD_DIR="${SCRIPT_DIR}"
readonly ENV_FILE="${PROD_DIR}/.env"
readonly ENV_EXAMPLE_FILE="${PROD_DIR}/.env.example"
readonly COMPOSE_FILE="${PROD_DIR}/docker-compose.yml"
readonly HEALTH_TIMEOUT_SECONDS="${DEPLOY_HEALTH_TIMEOUT_SECONDS:-300}"

log() {
  printf '[velpos-deploy] %s\n' "$*"
}

fail() {
  printf '[velpos-deploy] ERROR: %s\n' "$*" >&2
  show_diagnostics
  exit 1
}

compose() {
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

show_diagnostics() {
  if [[ -f "${ENV_FILE}" ]] && docker info >/dev/null 2>&1; then
    log "Container status:"
    compose ps >&2 || true
    log "Recent service logs:"
    compose logs --tail=80 mysql backend frontend >&2 || true
  fi
}

on_error() {
  local exit_code="$1"
  local line_number="$2"
  trap - ERR
  printf '[velpos-deploy] ERROR: deployment failed at line %s (exit code %s).\n' \
    "${line_number}" "${exit_code}" >&2
  show_diagnostics
  exit "${exit_code}"
}

trap 'on_error "$?" "$LINENO"' ERR

require_command() {
  local command_name="$1"
  command -v "${command_name}" >/dev/null 2>&1 || fail "Required command not found: ${command_name}"
}

read_env_value() {
  local key="$1"
  awk -F= -v key="${key}" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "${ENV_FILE}"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local temp_file
  temp_file="$(mktemp "${PROD_DIR}/.env.tmp.XXXXXX")"

  awk -v key="${key}" -v value="${value}" '
    BEGIN { updated = 0 }
    $0 ~ "^" key "=" {
      print key "=" value
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) print key "=" value
    }
  ' "${ENV_FILE}" >"${temp_file}"
  chmod --reference="${ENV_FILE}" "${temp_file}" 2>/dev/null || chmod 600 "${temp_file}"
  mv "${temp_file}" "${ENV_FILE}"
}

prompt_secret() {
  local key="$1"
  local prompt="$2"
  local minimum_length="$3"
  local value confirmation

  while true; do
    read -r -s -p "${prompt}: " value
    printf '\n'
    if (( ${#value} < minimum_length )); then
      log "Value must contain at least ${minimum_length} characters."
      continue
    fi

    read -r -s -p "Confirm ${prompt}: " confirmation
    printf '\n'
    if [[ "${value}" != "${confirmation}" ]]; then
      log "The two values do not match."
      continue
    fi

    set_env_value "${key}" "${value}"
    return
  done
}

initialize_environment() {
  [[ -f "${ENV_EXAMPLE_FILE}" ]] || fail "Missing environment template: ${ENV_EXAMPLE_FILE}"
  cp "${ENV_EXAMPLE_FILE}" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  log "Creating the production environment configuration."
}

configure_missing_secrets() {
  local jwt_secret admin_password mysql_password configuration_changed=0
  jwt_secret="$(read_env_value JWT_SECRET)"
  admin_password="$(read_env_value VELPOS_ADMIN_PASSWORD)"
  mysql_password="$(read_env_value MYSQL_ROOT_PASSWORD)"

  if (( ${#jwt_secret} < 32 )); then
    [[ -t 0 ]] || fail "JWT_SECRET is missing or invalid. Run ./build/prod/deploy.sh interactively to configure it."
    require_command openssl
    set_env_value JWT_SECRET "$(openssl rand -hex 32)"
    configuration_changed=1
  fi

  if (( ${#admin_password} < 12 )); then
    [[ -t 0 ]] || fail "VELPOS_ADMIN_PASSWORD is missing or invalid. Run ./build/prod/deploy.sh interactively to configure it."
    while true; do
      prompt_secret VELPOS_ADMIN_PASSWORD "Initial admin password (letters, digits, '.', '_', '~', '!', '@', '%', '+' or '-')" 12
      if [[ "$(read_env_value VELPOS_ADMIN_PASSWORD)" =~ ^[A-Za-z0-9._~!@%+-]+$ ]]; then
        configuration_changed=1
        break
      fi
      log "Admin password contains characters that cannot be stored safely in the dotenv file."
    done
  fi

  if [[ ! "${mysql_password}" =~ ^[A-Za-z0-9._~-]{12,}$ ]]; then
    [[ -t 0 ]] || fail "MYSQL_ROOT_PASSWORD is missing or invalid. Run ./build/prod/deploy.sh interactively to configure it."
    while true; do
      prompt_secret MYSQL_ROOT_PASSWORD "MySQL root password (letters, digits, '.', '_', '~' or '-')" 12
      if [[ "$(read_env_value MYSQL_ROOT_PASSWORD)" =~ ^[A-Za-z0-9._~-]+$ ]]; then
        configuration_changed=1
        break
      fi
      log "MySQL password contains unsupported characters; use only URL-safe characters."
    done
  fi

  if (( configuration_changed )); then
    log "Configuration saved to ${ENV_FILE}."
  fi
}

validate_environment() {
  local jwt_secret admin_password mysql_password projects_host_dir
  jwt_secret="$(read_env_value JWT_SECRET)"
  admin_password="$(read_env_value VELPOS_ADMIN_PASSWORD)"
  mysql_password="$(read_env_value MYSQL_ROOT_PASSWORD)"

  (( ${#jwt_secret} >= 32 )) || fail "JWT_SECRET in build/prod/.env must contain at least 32 characters."
  (( ${#admin_password} >= 12 )) || fail "VELPOS_ADMIN_PASSWORD in build/prod/.env must contain at least 12 characters."
  [[ "${mysql_password}" =~ ^[A-Za-z0-9._~-]{12,}$ ]] || \
    fail "MYSQL_ROOT_PASSWORD must contain at least 12 URL-safe characters."
  [[ "$(read_env_value VELPOS_MODE)" == "pro" ]] || fail "VELPOS_MODE must be set to pro."
  [[ "${HEALTH_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] || \
    fail "DEPLOY_HEALTH_TIMEOUT_SECONDS must be a positive integer."

  projects_host_dir="$(read_env_value PROJECTS_HOST_DIR)"
  projects_host_dir="${projects_host_dir//'${HOME}'/${HOME}}"
  projects_host_dir="${projects_host_dir//'$HOME'/${HOME}}"
  [[ "${projects_host_dir}" == /* ]] || \
    fail "PROJECTS_HOST_DIR must be an absolute path or start with \${HOME}."
  mkdir -p "${projects_host_dir}"
}

container_state() {
  local container_name="$1"
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
    "${container_name}" 2>/dev/null || printf 'missing'
}

wait_for_services() {
  local deadline mysql_state backend_state frontend_state
  deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))

  log "Waiting for services to become healthy (timeout: ${HEALTH_TIMEOUT_SECONDS}s)..."
  while (( SECONDS < deadline )); do
    mysql_state="$(container_state vp-mysql)"
    backend_state="$(container_state vp-backend)"
    frontend_state="$(container_state vp-frontend)"

    if [[ "${mysql_state}" == "healthy" && "${backend_state}" == "healthy" && "${frontend_state}" == "running" ]]; then
      return
    fi

    if [[ "${mysql_state}" =~ ^(exited|dead)$ || "${backend_state}" =~ ^(exited|dead)$ || "${frontend_state}" =~ ^(exited|dead)$ ]]; then
      fail "A service stopped during startup (mysql=${mysql_state}, backend=${backend_state}, frontend=${frontend_state})."
    fi
    sleep 3
  done

  fail "Services did not become ready in time (mysql=${mysql_state}, backend=${backend_state}, frontend=${frontend_state})."
}

main() {
  require_command docker
  docker compose version >/dev/null 2>&1 || fail "Docker Compose V2 is required."
  docker info >/dev/null 2>&1 || fail "Docker daemon is not available."

  if [[ ! -f "${ENV_FILE}" ]]; then
    [[ -t 0 ]] || fail "Missing build/prod/.env. Run ./build/prod/deploy.sh interactively once to create it."
    initialize_environment
  fi

  configure_missing_secrets
  validate_environment
  compose config --quiet

  log "Building production images..."
  compose build --pull

  log "Starting the production stack..."
  compose up -d --remove-orphans --force-recreate
  wait_for_services

  log "Deployment completed successfully."
  compose ps
  log "Open http://localhost:$(read_env_value APP_PORT)"
}

main "$@"
