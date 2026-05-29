#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-status}"
IMAGE_ARG="${2:-${GMM_IMAGE:-}}"

STATE_FILE="${GMM_DEPLOY_STATE:-/opt/gmm_deploy/deploy-state.env}"
ENV_FILE="${GMM_ENV_FILE:-/opt/gmm_project/Gmail-Monitor/.env}"
RUNTIME_DIR="${GMM_RUNTIME_DIR:-/opt/gmm_runtime}"
HOST_PORT="${GMM_HOST_PORT:-127.0.0.1:8080:8080}"
SYSTEMD_ENV="${GMM_SYSTEMD_ENV:-/etc/gmm/deploy-image.env}"
LOCK_FILE="${STATE_FILE}.lock"

ACTIVE_IMAGE=""
ACTIVE_DIGEST=""
PREVIOUS_IMAGE=""
PREVIOUS_DIGEST=""
LAST_CHECKED_IMAGE=""
LAST_CHECKED_DIGEST=""
LAST_CHECK_STATUS=""
LAST_CHECK_AT=""

usage() {
  cat <<'USAGE'
Usage:
  deploy-image.sh status
  deploy-image.sh pull IMAGE
  deploy-image.sh check [IMAGE]
  deploy-image.sh activate [IMAGE]
  deploy-image.sh rollback

Environment:
  GMM_DEPLOY_STATE   Host-side state file for active and previous image references.
  GMM_ENV_FILE       Existing env file used by the Gmail Monitor container.
  GMM_RUNTIME_DIR    Runtime directory containing credentials.json, token.json, filters.json, log/.
  GMM_HOST_PORT      Docker port publish value, default 127.0.0.1:8080:8080.
  GMM_SYSTEMD_ENV    Optional systemd-readable env file updated on activation.
USAGE
}

log() {
  printf '[%s] %s\n' "$1" "$2"
}

fail() {
  log "ERROR" "$1" >&2
  exit "${2:-1}"
}

ensure_state_dir() {
  mkdir -p "$(dirname "$STATE_FILE")"
}

load_state() {
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
  fi
}

quote_value() {
  local value="${1:-}"
  printf "'%s'" "${value//\'/\'\\\'\'}"
}

write_state() {
  ensure_state_dir
  local tmp
  tmp="$(mktemp "${STATE_FILE}.tmp.XXXXXX")"
  {
    printf 'ACTIVE_IMAGE=%s\n' "$(quote_value "$ACTIVE_IMAGE")"
    printf 'ACTIVE_DIGEST=%s\n' "$(quote_value "$ACTIVE_DIGEST")"
    printf 'PREVIOUS_IMAGE=%s\n' "$(quote_value "$PREVIOUS_IMAGE")"
    printf 'PREVIOUS_DIGEST=%s\n' "$(quote_value "$PREVIOUS_DIGEST")"
    printf 'LAST_CHECKED_IMAGE=%s\n' "$(quote_value "$LAST_CHECKED_IMAGE")"
    printf 'LAST_CHECKED_DIGEST=%s\n' "$(quote_value "$LAST_CHECKED_DIGEST")"
    printf 'LAST_CHECK_STATUS=%s\n' "$(quote_value "$LAST_CHECK_STATUS")"
    printf 'LAST_CHECK_AT=%s\n' "$(quote_value "$LAST_CHECK_AT")"
  } > "$tmp"
  chmod 0600 "$tmp"
  mv "$tmp" "$STATE_FILE"
}

with_lock() {
  ensure_state_dir
  if ! mkdir "$LOCK_FILE" 2>/dev/null; then
    fail "another deploy operation is already in progress: $LOCK_FILE" 12
  fi
  trap 'rmdir "$LOCK_FILE" 2>/dev/null || true' EXIT
}

require_image() {
  [[ -n "${1:-}" ]] || fail "image reference is required" 2
}

image_digest() {
  local image="$1"
  docker image inspect "$image" --format '{{index .RepoDigests 0}}' 2>/dev/null || true
}

status() {
  load_state
  cat <<STATUS
ACTIVE_IMAGE=${ACTIVE_IMAGE}
ACTIVE_DIGEST=${ACTIVE_DIGEST}
PREVIOUS_IMAGE=${PREVIOUS_IMAGE}
PREVIOUS_DIGEST=${PREVIOUS_DIGEST}
LAST_CHECKED_IMAGE=${LAST_CHECKED_IMAGE}
LAST_CHECKED_DIGEST=${LAST_CHECKED_DIGEST}
LAST_CHECK_STATUS=${LAST_CHECK_STATUS}
LAST_CHECK_AT=${LAST_CHECK_AT}
STATE_FILE=${STATE_FILE}
RUNTIME_DIR=${RUNTIME_DIR}
STATUS
}

pull_image() {
  local image="$1"
  require_image "$image"
  with_lock
  load_state
  log "PULL" "pulling candidate image: $image"
  docker pull "$image"
  LAST_CHECKED_IMAGE="$image"
  LAST_CHECKED_DIGEST="$(image_digest "$image")"
  LAST_CHECK_STATUS="PULLED"
  LAST_CHECK_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_state
  log "PULL" "candidate recorded: ${LAST_CHECKED_DIGEST:-$LAST_CHECKED_IMAGE}"
}

check_runtime_inputs() {
  [[ -f "$ENV_FILE" ]] || fail "env file missing: $ENV_FILE" 20
  [[ -f "$RUNTIME_DIR/credentials.json" ]] || fail "credentials missing: $RUNTIME_DIR/credentials.json" 21
  [[ -f "$RUNTIME_DIR/token.json" ]] || fail "token missing: $RUNTIME_DIR/token.json" 22
  [[ -f "$RUNTIME_DIR/filters.json" ]] || fail "filters missing: $RUNTIME_DIR/filters.json" 23
  mkdir -p "$RUNTIME_DIR/log"
}

check_image() {
  local image="${1:-$LAST_CHECKED_IMAGE}"
  load_state
  image="${image:-$LAST_CHECKED_IMAGE}"
  require_image "$image"
  with_lock
  load_state
  check_runtime_inputs
  log "CHECK" "running no-external-API container check for: $image"
  docker run --rm \
    --env-file "$ENV_FILE" \
    -e GMM_FLASK_HOST=0.0.0.0 \
    -e GMM_FLASK_PORT=8080 \
    -e GMM_CREDS_PATH=/runtime/credentials.json \
    -e GMM_TOKEN_PATH=/runtime/token.json \
    -e GMM_FILTER_PATH=/runtime/filters.json \
    -e GMM_LOG_FILE=/runtime/log/gmm_app.log \
    --mount "type=bind,src=$RUNTIME_DIR/credentials.json,dst=/runtime/credentials.json,readonly" \
    --mount "type=bind,src=$RUNTIME_DIR/token.json,dst=/runtime/token.json" \
    --mount "type=bind,src=$RUNTIME_DIR/filters.json,dst=/runtime/filters.json,readonly" \
    --mount "type=bind,src=$RUNTIME_DIR/log,dst=/runtime/log" \
    "$image" python scripts/container_check.py
  LAST_CHECKED_IMAGE="$image"
  LAST_CHECKED_DIGEST="$(image_digest "$image")"
  LAST_CHECK_STATUS="OK"
  LAST_CHECK_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_state
  log "CHECK" "preflight OK: ${LAST_CHECKED_DIGEST:-$LAST_CHECKED_IMAGE}"
}

write_systemd_env() {
  local image="$1"
  local tmp
  mkdir -p "$(dirname "$SYSTEMD_ENV")"
  tmp="$(mktemp "${SYSTEMD_ENV}.tmp.XXXXXX")"
  {
    printf 'GMM_ACTIVE_IMAGE=%s\n' "$(quote_value "$image")"
    printf 'GMM_ENV_FILE=%s\n' "$(quote_value "$ENV_FILE")"
    printf 'GMM_RUNTIME_DIR=%s\n' "$(quote_value "$RUNTIME_DIR")"
    printf 'GMM_HOST_PORT=%s\n' "$(quote_value "$HOST_PORT")"
  } > "$tmp"
  chmod 0600 "$tmp"
  mv "$tmp" "$SYSTEMD_ENV"
}

activate_image() {
  local image="${1:-$LAST_CHECKED_IMAGE}"
  load_state
  image="${image:-$LAST_CHECKED_IMAGE}"
  require_image "$image"
  with_lock
  load_state
  [[ "$LAST_CHECK_STATUS" == "OK" ]] || fail "last preflight did not pass; run check first" 30
  [[ "$LAST_CHECKED_IMAGE" == "$image" ]] || fail "checked image does not match requested activation" 31
  PREVIOUS_IMAGE="$ACTIVE_IMAGE"
  PREVIOUS_DIGEST="$ACTIVE_DIGEST"
  ACTIVE_IMAGE="$image"
  ACTIVE_DIGEST="${LAST_CHECKED_DIGEST:-$(image_digest "$image")}"
  write_state
  write_systemd_env "$ACTIVE_IMAGE"
  log "ACTIVATE" "active image updated: ${ACTIVE_DIGEST:-$ACTIVE_IMAGE}"
  log "ACTIVATE" "run service manually and inspect journal before waiting for timer"
}

rollback_image() {
  load_state
  [[ -n "$PREVIOUS_IMAGE" ]] || fail "no previous image recorded; consider Python direct rollback" 40
  with_lock
  load_state
  local old_active="$ACTIVE_IMAGE"
  local old_digest="$ACTIVE_DIGEST"
  ACTIVE_IMAGE="$PREVIOUS_IMAGE"
  ACTIVE_DIGEST="$PREVIOUS_DIGEST"
  PREVIOUS_IMAGE="$old_active"
  PREVIOUS_DIGEST="$old_digest"
  LAST_CHECK_STATUS="ROLLBACK"
  LAST_CHECK_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_state
  write_systemd_env "$ACTIVE_IMAGE"
  log "ROLLBACK" "active image restored: ${ACTIVE_DIGEST:-$ACTIVE_IMAGE}"
  log "ROLLBACK" "verify with manual service run and journal before next timer"
}

case "$ACTION" in
  status)
    status
    ;;
  pull)
    pull_image "$IMAGE_ARG"
    ;;
  check)
    check_image "$IMAGE_ARG"
    ;;
  activate)
    activate_image "$IMAGE_ARG"
    ;;
  rollback)
    rollback_image
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    fail "unknown action: $ACTION" 2
    ;;
esac
