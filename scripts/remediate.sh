#!/usr/bin/env bash
#
# Emergency rollback from a terminal.
#
# This is the "remediate" half of the demo: a single command any on-call
# engineer can run — or any alerting system can shell out to — that turns the
# release flag off in LaunchDarkly. Every connected SDK, including the running
# demo app, sees the change over its streaming connection within milliseconds.
#
#   ./scripts/remediate.sh            # turn the flag OFF  (the kill switch)
#   ./scripts/remediate.sh --on       # turn it back ON    (needs LD_API_TOKEN)
#   ./scripts/remediate.sh --status   # show current on/off state (needs LD_API_TOKEN)
#
# Configuration is read from the .env file next to this repository's app.py.
# See README.md -> "Step 6: Wire up the kill switch".

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090  # .env is user-supplied, not tracked in git
  set -a; source "${ENV_FILE}"; set +a
else
  echo "warning: ${ENV_FILE} not found; relying on existing environment variables" >&2
fi

FLAG_KEY="${LD_FLAG_KEY:-release-order-insights-v2}"
PROJECT_KEY="${LD_PROJECT_KEY:-default}"
ENVIRONMENT_KEY="${LD_ENVIRONMENT_KEY:-test}"
API_BASE_URL="${LD_API_BASE_URL:-https://app.launchdarkly.com}"
TRIGGER_URL="${LD_KILL_SWITCH_TRIGGER_URL:-}"
API_TOKEN="${LD_API_TOKEN:-}"

ACTION="off"
case "${1:-}" in
  ""|--off)   ACTION="off" ;;
  --on)       ACTION="on" ;;
  --status)   ACTION="status" ;;
  -h|--help)  sed -n '3,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *)          echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
esac

require_api_token() {
  if [[ -z "${API_TOKEN}" ]]; then
    cat >&2 <<EOF
error: LD_API_TOKEN is not set.

  '--on' and '--status' use the LaunchDarkly REST API. Create a token under
  Account settings -> Authorization -> Create token (Writer role), then add it
  to your .env:

    LD_API_TOKEN=api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    LD_PROJECT_KEY=default
    LD_ENVIRONMENT_KEY=test
EOF
    exit 1
  fi
}

# Semantic patch: describe the change you want rather than a JSON diff, so the
# request cannot clobber someone else's concurrent edit to the same flag.
patch_flag() {
  local instruction="$1"
  require_api_token
  echo "Sending '${instruction}' for flag '${FLAG_KEY}' (${PROJECT_KEY}/${ENVIRONMENT_KEY})…"
  curl --fail-with-body --silent --show-error \
    --request PATCH \
    --url "${API_BASE_URL}/api/v2/flags/${PROJECT_KEY}/${FLAG_KEY}" \
    --header "Authorization: ${API_TOKEN}" \
    --header 'Content-Type: application/json; domain-model=launchdarkly.semanticpatch' \
    --data "{
      \"environmentKey\": \"${ENVIRONMENT_KEY}\",
      \"instructions\": [{\"kind\": \"${instruction}\"}],
      \"comment\": \"Fired from scripts/remediate.sh\"
    }" > /dev/null
  echo "Done. Watch the running demo app switch with no reload."
}

case "${ACTION}" in
  off)
    if [[ -n "${TRIGGER_URL}" ]]; then
      # Preferred path: a LaunchDarkly flag trigger. The URL *is* the
      # credential, so it is never echoed here.
      echo "Firing the LaunchDarkly kill-switch trigger for '${FLAG_KEY}'…"
      curl --fail-with-body --silent --show-error --request POST --url "${TRIGGER_URL}" > /dev/null
      echo "Trigger accepted. Watch the running demo app roll back with no reload."
    else
      echo "LD_KILL_SWITCH_TRIGGER_URL is not set; falling back to the REST API." >&2
      patch_flag "turnFlagOff"
    fi
    ;;
  on)
    # A trigger is bound to one action when it is created, so re-enabling always
    # goes through the API (or the LaunchDarkly UI).
    patch_flag "turnFlagOn"
    ;;
  status)
    require_api_token
    curl --fail-with-body --silent --show-error \
      --url "${API_BASE_URL}/api/v2/flags/${PROJECT_KEY}/${FLAG_KEY}?env=${ENVIRONMENT_KEY}" \
      --header "Authorization: ${API_TOKEN}" \
      | grep -o "\"on\":[a-z]*" | head -1 \
      | sed "s|\"on\":true|flag '${FLAG_KEY}' is ON in '${ENVIRONMENT_KEY}'|;s|\"on\":false|flag '${FLAG_KEY}' is OFF in '${ENVIRONMENT_KEY}'|"
    ;;
esac
