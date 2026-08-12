#!/usr/bin/env bash
# One-session Fly.io provisioning for the Nornyx feedback gateway.
#
# Prerequisite (the only human-authority steps this script cannot do):
#   1. flyctl installed and authenticated:  flyctl auth login
#   2. when prompted below, a fine-grained GitHub token minted in the browser.
#
# Everything else — app, volume, deploy, single-replica pin, verification —
# is performed here, idempotently. Run from the repository root:
#
#   bash ops/feedback-gateway/deploy_fly.sh
#
# The token is read with echo disabled and goes only to `flyctl secrets set`.
# It is never written to a file, never echoed, and never passed on a command
# line that this script logs.

set -euo pipefail

APP="${NORNYX_FLY_APP:-nornyx-feedback-gateway}"
REGION="${NORNYX_FLY_REGION:-iad}"
CONFIG="ops/feedback-gateway/fly.toml"
INTAKE_REPOSITORY="mazinmarji/nornyx-lab-feedback"

[ -f "$CONFIG" ] || { echo "run from the repository root (missing $CONFIG)" >&2; exit 1; }
command -v flyctl >/dev/null || { echo "flyctl is not installed: https://fly.io/docs/flyctl/install/" >&2; exit 1; }
flyctl auth whoami >/dev/null || { echo "not authenticated: run 'flyctl auth login' first" >&2; exit 1; }
# The verifier's repository check and the smoke's independent issue fetch run
# under the OPERATOR's GitHub authority, deliberately not the pasted token.
command -v gh >/dev/null || { echo "gh is not installed: https://cli.github.com/" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh is not authenticated: run 'gh auth login' first" >&2; exit 1; }
command -v python >/dev/null || { echo "python 3.11+ is required on PATH" >&2; exit 1; }

echo "==> app"
if ! flyctl apps list --json | grep -qiE "\"name\": *\"$APP\""; then
  flyctl apps create "$APP" --org personal
fi

echo "==> persistent volume"
if ! flyctl volumes list --app "$APP" --json | grep -qiE '"name": *"nornyx_feedback"'; then
  flyctl volumes create nornyx_feedback --app "$APP" --region "$REGION" --size 1 --yes
fi

echo "==> volume ownership for the non-root gateway"
# A fresh Fly volume mounts root-owned, shadowing the directory the image
# chowned at build time (docker named volumes copy ownership up on first
# use; Fly volumes do not). The gateway runs as uid 999 and could not
# create its database. One idempotent root machine fixes the mount once;
# the health check and the live smoke below then prove the fix held.
flyctl machine run debian:bookworm-slim \
  --app "$APP" --region "$REGION" --rm --restart no \
  --volume nornyx_feedback:/var/lib/nornyx-feedback \
  --command "chown 999:999 /var/lib/nornyx-feedback" \
  || { echo "volume ownership initialization failed" >&2; exit 1; }

echo "==> GitHub credential"
if ! flyctl secrets list --app "$APP" | grep -q NORNYX_FEEDBACK_GITHUB_TOKEN; then
  cat <<GUIDE

  Mint the credential now (browser, human-only step):

    https://github.com/settings/personal-access-tokens/new

    Token name ........ nornyx-feedback-gateway
    Resource owner .... mazinmarji
    Repository access . Only select repositories -> $INTAKE_REPOSITORY
    Permissions ....... Repository permissions -> Issues: Read and write
                        (Metadata: Read-only is added automatically)
    Expiration ........ your call; put rotation on the calendar

  Paste it below. Input is hidden and goes only to Fly's secret store.

GUIDE
  read -r -s -p "fine-grained token for $INTAKE_REPOSITORY: " NORNYX_TOKEN
  echo
  [ -n "$NORNYX_TOKEN" ] || { echo "empty token — aborting" >&2; exit 1; }
  # stdin import, not `secrets set KEY=VALUE`: the value never appears in argv.
  printf 'NORNYX_FEEDBACK_GITHUB_TOKEN=%s\n' "$NORNYX_TOKEN" \
    | flyctl secrets import --app "$APP" --stage
  unset NORNYX_TOKEN
fi

echo "==> deploy (build context: gateway/)"
flyctl deploy gateway --config "$CONFIG" --app "$APP" --ha=false

echo "==> pin exactly one machine"
flyctl scale count 1 --app "$APP" --yes

echo "==> verify topology and runtime security against real state"
flyctl machines list --app "$APP" --json > /tmp/fly-machines.json
python scripts/verify_h1d_provisioning.py \
  --repository "$INTAKE_REPOSITORY" \
  --expect-visibility private \
  --endpoint "https://$APP.fly.dev" \
  --fly-config "$CONFIG" \
  --fly-machines-json /tmp/fly-machines.json \
  --fly-app "$APP" \
  --scan-tree .

# /health saying github_configured=true only proves a token is present. This
# proves the deployed gateway can actually write: a synthetic session goes
# through the production API end to end (created -> unchanged -> updated on
# one issue, marker present, write key absent) and the issue is then closed.
# An expired, malformed, wrong-repository, or under-permissioned credential
# fails here, before anything reports the provisioning ready.
echo "==> live gateway->GitHub credential smoke (synthetic session, closed afterwards)"
python scripts/smoke_h1d_gateway.py \
  --endpoint "https://$APP.fly.dev" \
  --repository "$INTAKE_REPOSITORY"

echo
echo "H1-D provisioning verified against real state."
echo "GATEWAY_ENDPOINT=https://$APP.fly.dev"
