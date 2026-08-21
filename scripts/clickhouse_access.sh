#!/usr/bin/env bash
# Setup GCP + GKE credentials and port-forward ClickHouse HTTP (8123).
# Usage:
#   ./scripts/clickhouse_access.sh            # auth + port-forward
#   ./scripts/clickhouse_access.sh --auth-only
#   ./scripts/clickhouse_access.sh --force-login

set -euo pipefail

PROJECT="dfb-dev-env"
CLUSTER="arbitrage-cluster"
ZONE="us-central1-a"
ACCOUNT="renan.facanha@dfb.network"
EXPECTED_CONTEXT="gke_${PROJECT}_${ZONE}_${CLUSTER}"
NAMESPACE="clickhouse"
POD="chi-ch-ha-ch-0-0-0"
LOCAL_PORT="8123"
REMOTE_PORT="8123"

AUTH_ONLY=0
FORCE_LOGIN=0

for arg in "$@"; do
  case "$arg" in
    --auth-only) AUTH_ONLY=1 ;;
    --force-login) FORCE_LOGIN=1 ;;
    -h|--help)
      echo "Usage: $0 [--auth-only] [--force-login]"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 1
      ;;
  esac
done

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing dependency: $1" >&2
    echo "Install with Homebrew, e.g.: brew install --cask google-cloud-sdk && brew install kubectl" >&2
    exit 1
  fi
}

need_cmd gcloud
need_cmd kubectl

echo "==> Checking GCP login ($ACCOUNT)"
ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"

if [[ "$FORCE_LOGIN" -eq 1 || -z "$ACTIVE_ACCOUNT" ]]; then
  echo "Opening browser login for $ACCOUNT ..."
  gcloud auth login --account="$ACCOUNT"
else
  if [[ "$ACTIVE_ACCOUNT" != "$ACCOUNT" ]]; then
    echo "Switching active account: $ACTIVE_ACCOUNT -> $ACCOUNT"
    gcloud config set account "$ACCOUNT"
  else
    echo "Already logged in as $ACTIVE_ACCOUNT"
  fi

  # Refresh token if expired / invalid.
  if ! gcloud auth print-access-token >/dev/null 2>&1; then
    echo "Token invalid/expired. Re-login required..."
    gcloud auth login --account="$ACCOUNT"
  fi
fi

echo "==> Setting project: $PROJECT"
gcloud config set project "$PROJECT"

echo "==> Fetching GKE credentials: $CLUSTER ($ZONE)"
gcloud container clusters get-credentials "$CLUSTER" \
  --zone "$ZONE" \
  --project "$PROJECT"

echo "==> Confirming kubectl context"
CONTEXT="$(kubectl config current-context)"
echo "current-context: $CONTEXT"
if [[ "$CONTEXT" != "$EXPECTED_CONTEXT" ]]; then
  echo "Unexpected context. Expected: $EXPECTED_CONTEXT" >&2
  exit 1
fi

echo "==> Auth/setup OK"
if [[ "$AUTH_ONLY" -eq 1 ]]; then
  exit 0
fi

if lsof -nP -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $LOCAL_PORT already in use. Assuming ClickHouse port-forward is running."
  echo "Play UI: http://localhost:${LOCAL_PORT}/play"
  exit 0
fi

echo "==> Port-forward ClickHouse HTTP on localhost:${LOCAL_PORT}"
echo "Keep this terminal open. Play UI: http://localhost:${LOCAL_PORT}/play"
echo "Stop with Ctrl+C"
kubectl port-forward -n "$NAMESPACE" "pod/${POD}" "${LOCAL_PORT}:${REMOTE_PORT}"
