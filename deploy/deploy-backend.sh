#!/bin/bash
set -euo pipefail

#########################################
# deploy-backend.sh
# Blue-Green Deployment for Backend (Containers Only)
#
# Usage:
#   ./deploy-backend.sh --outputs-json backend-outputs.json --pem-path ~/ssh/key.pem --worker-instances "i-aaa,i-bbb"
#
# Requirements:
# - BACKEND_IMAGE env var set (full image ref, e.g. user/repo:tag)
# - SSM_PARAM_NAME env var set (parameter contains JSON {"username":"...","password":"..."})
# - AWS credentials & region in env (or instance profile)
# - jq installed on runner
#########################################

BACKEND_BLUE_PORT=8080
BACKEND_GREEN_PORT=8081

# === ARG PARSING ===
OUTPUTS_JSON=""
PEM_PATH=""
WORKER_INSTANCES_CSV=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --outputs-json) OUTPUTS_JSON="$2"; shift 2 ;;
    --pem-path)     PEM_PATH="$2"; shift 2 ;;
    --worker-instances) WORKER_INSTANCES_CSV="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "${OUTPUTS_JSON:-}" ]]; then
  echo "ERROR: --outputs-json is required"
  exit 1
fi
if [[ -z "${PEM_PATH:-}" ]]; then
  echo "ERROR: --pem-path is required"
  exit 1
fi
if [[ -z "${BACKEND_IMAGE:-}" ]]; then
  echo "ERROR: BACKEND_IMAGE environment variable is required"
  exit 1
fi
if [[ -z "${SSM_PARAM_NAME:-}" ]]; then
  echo "ERROR: SSM_PARAM_NAME environment variable is required"
  exit 1
fi

# Export AWS creds if present in env
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION

# === Read infra outputs from JSON ===
INSTANCE_IDS=$(jq -r '.ec2_instance_ids | join(",")' "$OUTPUTS_JSON" 2>/dev/null || echo "")
BACKEND_BLUE_TG=$(jq -r '.backend_blue_tg_arn' "$OUTPUTS_JSON" 2>/dev/null || echo "")
BACKEND_GREEN_TG=$(jq -r '.backend_green_tg_arn' "$OUTPUTS_JSON" 2>/dev/null || echo "")
LISTENER_ARN=$(jq -r '.alb_listener_arn' "$OUTPUTS_JSON" 2>/dev/null || echo "")

DB_ENDPOINT=$(jq -r '.db.endpoint // empty' "$OUTPUTS_JSON" 2>/dev/null || echo "")
DB_HOST=$(echo "$DB_ENDPOINT" | cut -d':' -f1)
DB_PORT=$(echo "$DB_ENDPOINT" | cut -d':' -f2)
DB_NAME=$(jq -r '.db.name // empty' "$OUTPUTS_JSON" 2>/dev/null || echo "")

if [[ -z "$INSTANCE_IDS" ]]; then
  echo "ERROR: no backend instance ids found in $OUTPUTS_JSON"
  exit 1
fi

IFS=',' read -ra INSTANCES <<< "$INSTANCE_IDS"

# Worker instances (comma-separated, optional)
WORKER_INSTANCES=()
if [[ -n "${WORKER_INSTANCES_CSV:-}" ]]; then
  IFS=',' read -ra WORKER_INSTANCES <<< "$WORKER_INSTANCES_CSV"
fi

# === Fetch DB credentials JSON from SSM and parse with jq ===
PARAM_VALUE=$(aws ssm get-parameter --name "$SSM_PARAM_NAME" --with-decryption --query "Parameter.Value" --output text) || {
  echo "ERROR: failed to read SSM parameter $SSM_PARAM_NAME"
  exit 1
}
DB_USER=$(echo "$PARAM_VALUE" | jq -r '.username')
DB_PASS=$(echo "$PARAM_VALUE" | jq -r '.password')

# encode DB creds to base64 to safely inject into remote shell
DB_USER_B64=$(printf '%s' "$DB_USER" | base64 | tr -d '\n')
DB_PASS_B64=$(printf '%s' "$DB_PASS" | base64 | tr -d '\n')

# === Helpers ===

_get_ip() {
  local instance_id=$1
  aws ec2 describe-instances --instance-ids "$instance_id" \
    --query "Reservations[0].Instances[0].PublicIpAddress" --output text
}

print_container_logs() {
  local instance_id=$1
  local container=$2
  ip="$(_get_ip "$instance_id")"
  echo "---- logs for $container on $instance_id ($ip) ----"
  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" "docker logs $container || true"
  echo "-----------------------------------------------"
}

# Deploy container on the remote instance.
# Note: this expands local variables into the remote script safely using base64 for credentials.
deploy_container() {
  local instance_id=$1
  local port=$2
  local color=$3
  local container_name="backend_${color,,}"

  local ip
  ip="$(_get_ip "$instance_id")"
  if [[ -z "$ip" || "$ip" == "None" ]]; then
    echo "ERROR: could not determine public IP for instance $instance_id"
    return 2
  fi

  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" bash <<EOF
set -e
docker stop $container_name || true
docker rm $container_name || true

# DockerHub login (token expanded locally into the here-doc)
echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin

docker pull "$BACKEND_IMAGE"

# decode DB creds (base64 encoded locally)
DB_USER=\$(echo '$DB_USER_B64' | base64 -d)
DB_PASS=\$(echo '$DB_PASS_B64' | base64 -d)

docker run -d -p $port:8000 \
  --name $container_name \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_REGION="$AWS_REGION" \
  -e DB_HOST="$DB_HOST" \
  -e DB_PORT="$DB_PORT" \
  -e DB_NAME="$DB_NAME" \
  -e DB_USER="\$DB_USER" \
  -e DB_PASS="\$DB_PASS" \
  "$BACKEND_IMAGE"
EOF
}

# Remove both backend_blue and backend_green on specified instances
rollback_backend_both_on() {
  if [[ $# -eq 0 ]]; then return; fi
  echo "Rolling back BOTH backend_blue and backend_green on instances: $*"
  for instance_id in "$@"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f backend_blue backend_green || true"
  done
}

# Remove only a given color container on specified instances
rollback_backend_color_on() {
  local color="$1"; shift
  if [[ $# -eq 0 ]]; then return; fi
  color="$(echo "$color" | tr '[:upper:]' '[:lower:]')"
  echo "Rolling back backend_${color} on instances: $*"
  for instance_id in "$@"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f backend_${color} || true"
  done
}

# Remove worker_new containers on worker instances (if any)
rollback_worker_new() {
  if [[ ${#WORKER_INSTANCES[@]} -eq 0 ]]; then
    echo "No worker instances to rollback."
    return
  fi
  echo "Rolling back worker_new on worker instances: ${WORKER_INSTANCES[*]}"
  for instance_id in "${WORKER_INSTANCES[@]}"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f worker_new || true"
  done
}

# === Detect current active target-group from ALB listener ===
CURRENT_TG=$(aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/api/aws/*')]].Actions[0].ForwardConfig.TargetGroups[0].TargetGroupArn" \
  --output text || echo "")

echo "Current TG: $CURRENT_TG"

DEPLOYED_INSTANCES=()

# === FIRST-TIME DEPLOY ===
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  echo "First-time deploy: deploying BLUE + GREEN on each instance"

  for instance in "${INSTANCES[@]}"; do
    echo "→ deploying BLUE on $instance"
    set +e
    deploy_container "$instance" $BACKEND_BLUE_PORT "BLUE"
    status_blue=$?
    set -e

    if [[ $status_blue -ne 0 ]]; then
      echo "❌ BLUE failed on $instance (status $status_blue)"
      print_container_logs "$instance" "backend_blue"
      rollback_targets=("${DEPLOYED_INSTANCES[@]}" "$instance")
      rollback_backend_both_on "${rollback_targets[@]}"
      rollback_worker_new
      {
        echo "backend_status=failed"
        echo "backend_active_env=NONE"
        echo "backend_inactive_env=NONE"
      } >> "$GITHUB_OUTPUT"
      exit 1
    fi

    echo "→ deploying GREEN on $instance"
    set +e
    deploy_container "$instance" $BACKEND_GREEN_PORT "GREEN"
    status_green=$?
    set -e

    if [[ $status_green -ne 0 ]]; then
      echo "❌ GREEN failed on $instance (status $status_green)"
      print_container_logs "$instance" "backend_green"
      rollback_targets=("${DEPLOYED_INSTANCES[@]}" "$instance")
      rollback_backend_both_on "${rollback_targets[@]}"
      rollback_worker_new
      {
        echo "backend_status=failed"
        echo "backend_active_env=NONE"
        echo "backend_inactive_env=NONE"
      } >> "$GITHUB_OUTPUT"
      exit 1
    fi

    # success for this instance (both colors)
    DEPLOYED_INSTANCES+=("$instance")
  done

  # All instances succeeded: attach BLUE to listener (BLUE = active)
  echo "Registering BLUE as active target group on listener..."
  aws elbv2 modify-listener \
    --listener-arn "$LISTENER_ARN" \
    --default-actions "Type=forward,ForwardConfig={TargetGroups=[{TargetGroupArn=$BACKEND_BLUE_TG,Weight=1}]}"

  ACTIVE_ENV="BLUE"
  INACTIVE_ENV="GREEN"
  ACTIVE_TG="$BACKEND_BLUE_TG"
  INACTIVE_TG="$BACKEND_GREEN_TG"

# === SUBSEQUENT DEPLOY ===
else
  if [[ "$CURRENT_TG" == "$BACKEND_BLUE_TG" ]]; then
    ACTIVE_ENV="BLUE"; NEW_COLOR="GREEN"; NEW_PORT=$BACKEND_GREEN_PORT
    NEW_TG="$BACKEND_GREEN_TG"; OLD_TG="$BACKEND_BLUE_TG"; INACTIVE_ENV="GREEN"
  else
    ACTIVE_ENV="GREEN"; NEW_COLOR="BLUE"; NEW_PORT=$BACKEND_BLUE_PORT
    NEW_TG="$BACKEND_BLUE_TG"; OLD_TG="$BACKEND_GREEN_TG"; INACTIVE_ENV="BLUE"
  fi

  echo "Currently serving: $ACTIVE_ENV"
  echo "Deploying NEW color: $NEW_COLOR"

  for instance in "${INSTANCES[@]}"; do
    echo "→ deploying $NEW_COLOR on $instance"
    set +e
    deploy_container "$instance" $NEW_PORT "$NEW_COLOR"
    status=$?
    set -e

    if [[ $status -ne 0 ]]; then
      echo "❌ Deploy of $NEW_COLOR failed on $instance (status $status)"
      print_container_logs "$instance" "backend_${NEW_COLOR,,}"
      rollback_targets=("${DEPLOYED_INSTANCES[@]}" "$instance")
      rollback_backend_color_on "$NEW_COLOR" "${rollback_targets[@]}"
      rollback_worker_new
      {
        echo "backend_status=failed"
        echo "backend_active_env=$ACTIVE_ENV"
        echo "backend_inactive_env=$NEW_COLOR"
      } >> "$GITHUB_OUTPUT"
      exit 1
    fi
    DEPLOYED_INSTANCES+=("$instance")
  done

  echo "Switching listener to NEW TG: $NEW_TG"
  aws elbv2 modify-listener \
    --listener-arn "$LISTENER_ARN" \
    --default-actions "Type=forward,ForwardConfig={TargetGroups=[{TargetGroupArn=$NEW_TG,Weight=1}]}"

  PREV_ACTIVE_ENV="$ACTIVE_ENV"
  ACTIVE_ENV="$NEW_COLOR"
  INACTIVE_ENV="$PREV_ACTIVE_ENV"
  ACTIVE_TG="$NEW_TG"
  INACTIVE_TG="$OLD_TG"
fi

# === SUCCESS outputs ===
{
  echo "backend_status=success"
  echo "backend_active_env=$ACTIVE_ENV"
  echo "backend_inactive_env=$INACTIVE_ENV"
  echo "backend_active_tg=$ACTIVE_TG"
  echo "backend_inactive_tg=$INACTIVE_TG"
  echo "backend_current_image=$BACKEND_IMAGE"
  echo "backend_deployed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "backend_deployed_by=${GITHUB_ACTOR:-manual}"
} >> "$GITHUB_OUTPUT"

echo "✅ Backend deployment completed. Active env: $ACTIVE_ENV"
exit 0
