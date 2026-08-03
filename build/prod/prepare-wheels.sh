#!/usr/bin/env bash
# Prepare offline Python wheels for production deployment.
# Run this on a machine with fast network, then deploy.sh will use the cached wheels.
#
# Usage:
#   ./build/prod/prepare-wheels.sh                    # prepare locally
#   ./build/prod/prepare-wheels.sh user@server        # prepare + rsync to server

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly WHEELS_DIR="${ROOT_DIR}/backend/.wheels"

log() { printf '[prepare-wheels] %s\n' "$*"; }
fail() { printf '[prepare-wheels] ERROR: %s\n' "$*" >&2; exit 1; }

main() {
  command -v docker >/dev/null 2>&1 || fail "Docker is required."

  log "Downloading wheels for linux/amd64..."
  rm -rf "${WHEELS_DIR}"
  mkdir -p "${WHEELS_DIR}"

  docker run --rm \
    --platform linux/amd64 \
    -v "${ROOT_DIR}/backend:/src:ro" \
    -v "${WHEELS_DIR}:/wheels" \
    python:3.12-slim \
    bash -c "pip install --quiet uv \
      && uv export --frozen --no-dev --project /src > /tmp/req.txt \
      && pip download -r /tmp/req.txt -d /wheels --only-binary=:all:" \
    || fail "pip download failed."

  local count
  count="$(find "${WHEELS_DIR}" -name '*.whl' | wc -l | tr -d ' ')"
  log "Done. ${count} wheels saved to backend/.wheels/"

  if [[ -n "${1:-}" ]]; then
    local target="$1"
    log "Syncing wheels to ${target}..."
    rsync -az --delete "${WHEELS_DIR}/" "${target}:$(ssh "${target}" 'cd velpos 2>/dev/null || cd ~/velpos; pwd')/backend/.wheels/"
    log "Sync complete."
  fi
}

main "$@"
