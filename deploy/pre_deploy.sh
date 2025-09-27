#!/usr/bin/env bash
set -euo pipefail

IMAGE_REPO="multi-cloud-cost-and-service-status-dashboard-repo"
USER="${DOCKERHUB_USERNAME}"

CAN_DEPLOY=false
COMPONENTS=""
WORKER_VER=""
BACKEND_VER=""
FRONTEND_VER=""
WORKER_IMAGE=""
BACKEND_IMAGE=""
FRONTEND_IMAGE=""

# === Step 1: Check if allowed to deploy ===
if [ "${GITHUB_REF}" = "refs/heads/main" ]; then
  CAN_DEPLOY=true
fi
if [ "${GITHUB_EVENT_NAME}" = "workflow_dispatch" ] && [ "${GITHUB_ACTOR}" = "Mahesh-Kotakonda" ]; then
  CAN_DEPLOY=true
fi

# === Step 2: Parse manual inputs (only when manually triggered) ===
if [ "${GITHUB_EVENT_NAME}" = "workflow_dispatch" ]; then
  COMPONENTS="${INPUT_COMPONENTS}"
  WORKER_VER="${INPUT_WORKER_VERSION:-}"
  BACKEND_VER="${INPUT_BACKEND_VERSION:-}"
  FRONTEND_VER="${INPUT_FRONTEND_VERSION:-}"

  COMPONENTS=$(echo "$COMPONENTS" | tr '[:upper:]' '[:lower:]')

  VALID_COMPONENTS=(all worker backend frontend)
  for comp in $(echo $COMPONENTS | tr ',' ' '); do
    if [[ ! " ${VALID_COMPONENTS[@]} " =~ " $comp " ]]; then
      echo "❌ Invalid component: $comp. Allowed: all, worker, backend, frontend."
      exit 1
    fi
  done

  if [[ "$COMPONENTS" == *"all"* && "$COMPONENTS" != "all" ]]; then
    echo "❌ If you want to deploy all components, set components=all only."
    exit 1
  fi

  # === Step 2.1: Validate versions ===
  validate_version() {
    local comp=$1
    local ver=$2
    if [[ -z "$ver" || "$ver" == "latest" ]]; then
      echo "❌ Version for $comp is required and cannot be 'latest' or empty."
      exit 1
    fi
  }

  if [[ "$COMPONENTS" == "all" ]]; then
    validate_version "worker" "$WORKER_VER"
    validate_version "backend" "$BACKEND_VER"
    validate_version "frontend" "$FRONTEND_VER"
  else
    if [[ "$COMPONENTS" == *"worker"* ]]; then
      validate_version "worker" "$WORKER_VER"
    fi
    if [[ "$COMPONENTS" == *"backend"* ]]; then
      validate_version "backend" "$BACKEND_VER"
    fi
    if [[ "$COMPONENTS" == *"frontend"* ]]; then
      validate_version "frontend" "$FRONTEND_VER"
    fi
  fi
fi

# === Step 3: Resolve images ===
if [ "${GITHUB_EVENT_NAME}" = "workflow_dispatch" ]; then
  if [[ "$COMPONENTS" == "all" || "$COMPONENTS" == *"worker"* ]]; then
    WORKER_IMAGE="$(basename "$USER/$IMAGE_REPO:worker-$WORKER_VER")"
  fi
  if [[ "$COMPONENTS" == "all" || "$COMPONENTS" == *"backend"* ]]; then
    BACKEND_IMAGE="$(basename "$USER/$IMAGE_REPO:backend-$BACKEND_VER")"
  fi
  if [[ "$COMPONENTS" == "all" || "$COMPONENTS" == *"frontend"* ]]; then
    FRONTEND_IMAGE="$(basename "$USER/$IMAGE_REPO:frontend-$FRONTEND_VER")"
  fi
else
  if [[ -n "${CLIENT_PAYLOAD_WORKER:-}" ]]; then
    WORKER_IMAGE="$(basename "$CLIENT_PAYLOAD_WORKER")"
  fi
  if [[ -n "${CLIENT_PAYLOAD_BACKEND:-}" ]]; then
    BACKEND_IMAGE="$(basename "$CLIENT_PAYLOAD_BACKEND")"
  fi
  if [[ -n "${CLIENT_PAYLOAD_FRONTEND:-}" ]]; then
    FRONTEND_IMAGE="$(basename "$CLIENT_PAYLOAD_FRONTEND")"
  fi
fi

echo "==== ✅ Final Pre-deploy Results ===="
echo "can_deploy=$CAN_DEPLOY"
echo "components=$COMPONENTS"
echo "worker_version=$WORKER_VER"
echo "backend_version=$BACKEND_VER"
echo "frontend_version=$FRONTEND_VER"
echo "worker_image=$WORKER_IMAGE"
echo "backend_image=$BACKEND_IMAGE"
echo "frontend_image=$FRONTEND_IMAGE"

# Export to GitHub Actions outputs
{
  echo "can_deploy=$CAN_DEPLOY"
  echo "components=$COMPONENTS"
  echo "worker_version=$WORKER_VER"
  echo "backend_version=$BACKEND_VER"
  echo "frontend_version=$FRONTEND_VER"
  echo "worker_image=$WORKER_IMAGE"
  echo "backend_image=$BACKEND_IMAGE"
  echo "frontend_image=$FRONTEND_IMAGE"
} >> "$GITHUB_OUTPUT"
