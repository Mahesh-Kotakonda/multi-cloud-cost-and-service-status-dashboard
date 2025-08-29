#!/bin/bash
set -euo pipefail

#########################################
# deploy-backend.sh
# Blue-Green Deployment for Backend (Containers Only)
#########################################

BACKEND_BLUE_PORT=8080
BACKEND_GREEN_PORT=8081
OUTPUTS_JSON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --outputs-json) OUTPUTS_JSON="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "${OUTPUTS_JSON:-}" ]]; then
  echo "ERROR: --outputs-json is required"
  exit 1
fi
if [[ -z "${PEM_PATH:-}" ]]; then
  echo "ERROR: PEM_PATH env var is required"
  exit 1
fi
if [[ -z "${SSM_PARAM_NAME:-}" ]]; then
  echo "ERROR: SSM_PARAM_NAME env var is required"
  exit 1
fi

echo "Full image: $DOCKERHUB_USERNAME/$BACKEND_IMAGE"
FULL_IMAGE="$DOCKERHUB_USERNAME/$BACKEND_IMAGE"

# === Short-circuit if BACKEND_IMAGE is empty ===
if [[ -z "${BACKEND_IMAGE:-}" ]]; then
  echo "⚠️ BACKEND_IMAGE is empty. Skipping backend deployment."

  # Export skipped outputs to GitHub Actions
  {
    echo "backend_status=skipped"
    echo "backend_active_env="
    echo "backend_inactive_env="
    echo "backend_active_tg="
    echo "backend_inactive_tg="
    echo "backend_current_image="
    echo "backend_previous_image="
    echo "backend_first_deployment="
    echo "backend_deployed_at="
    echo "backend_deployed_by="
    echo "backend_instance_ids="
  } | tee >(cat) >> "$GITHUB_OUTPUT"

  exit 0
fi

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION

echo "Reading instance IDs and target groups from $OUTPUTS_JSON..."
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
WORKER_INSTANCES=()
if [[ -n "${WORKER_INSTANCE_IDS:-}" ]]; then
  IFS=',' read -ra WORKER_INSTANCES <<< "$WORKER_INSTANCE_IDS"
fi

echo "Fetching DB credentials from SSM parameter $SSM_PARAM_NAME..."
PARAM_VALUE=$(aws ssm get-parameter --name "$SSM_PARAM_NAME" --with-decryption --query "Parameter.Value" --output text) || {
  echo "ERROR: failed to read SSM parameter $SSM_PARAM_NAME"
  exit 1
}
DB_USER=$(echo "$PARAM_VALUE" | jq -r '.username')
DB_PASS=$(echo "$PARAM_VALUE" | jq -r '.password')
DB_USER_B64=$(printf '%s' "$DB_USER" | base64 | tr -d '\n')
DB_PASS_B64=$(printf '%s' "$DB_PASS" | base64 | tr -d '\n')

# === Helpers ===
_get_ip() {
  local instance_id=$1
  aws ec2 describe-instances --instance-ids "$instance_id" \
    --query "Reservations[0].Instances[0].PublicIpAddress" --output text | tr -d '\n'
}

get_container_image() {
  local instance_id=$1
  local container=$2
  local ip="$(_get_ip "$instance_id")"
  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
    "docker inspect --format='{{.Config.Image}}' $container 2>/dev/null || echo ''"
}

print_container_logs() {
  local instance_id=$1
  local container=$2
  ip="$(_get_ip "$instance_id")"
  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" "docker logs $container || true"
}

deploy_container() {
  local instance_id=$1
  local port=$2
  local color=$3
  local container_name="backend_${color,,}"
  local ip="$(_get_ip "$instance_id")"

  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" \
      ec2-user@"$ip" \
      DOCKERHUB_USERNAME="$DOCKERHUB_USERNAME" \
      DOCKERHUB_TOKEN="$DOCKERHUB_TOKEN" \
      AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
      AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
      AWS_REGION="$AWS_REGION" \
      FULL_IMAGE="$FULL_IMAGE" \
      CONTAINER_NAME="$container_name" \
      PORT="$port" \
      DB_USER_B64="$DB_USER_B64" \
      DB_PASS_B64="$DB_PASS_B64" \
      DB_HOST="$DB_HOST" \
      DB_PORT="$DB_PORT" \
      DB_NAME="$DB_NAME" \
      bash <<'EOF'
set -euo pipefail
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true
echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
docker pull "$FULL_IMAGE"
DB_USER=$(echo "$DB_USER_B64" | base64 -d)
DB_PASS=$(echo "$DB_PASS_B64" | base64 -d)
docker run -d -p "$PORT":8000 \
  --name "$CONTAINER_NAME" \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_REGION="$AWS_REGION" \
  -e DB_HOST="$DB_HOST" \
  -e DB_PORT="$DB_PORT" \
  -e DB_NAME="$DB_NAME" \
  -e DB_USER="$DB_USER" \
  -e DB_PASS="$DB_PASS" \
  "$FULL_IMAGE"
EOF
}

rollback_backend_both_on() {
  for instance_id in "$@"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f backend_blue backend_green 2>/dev/null || true"
  done
}

rollback_backend_color_on() {
  local color="$1"; shift
  color="$(echo "$color" | tr '[:upper:]' '[:lower:]')"
  for instance_id in "$@"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f backend_${color} 2>/dev/null || true"
  done
}

rollback_worker_new() {
  for instance_id in "${WORKER_INSTANCES[@]:-}"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f worker_new 2>/dev/null || true"
  done
}

# === Main deployment ===
CURRENT_TG=$(aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/api/aws/*')]].Actions[0].ForwardConfig.TargetGroups[0].TargetGroupArn" \
  --output text || echo "")

DEPLOYED_INSTANCES=()

# Determine previous image
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  PREVIOUS_IMAGE="$FULL_IMAGE"
  BACKEND_FIRST_DEPLOYMENT=true
else
  BACKEND_FIRST_DEPLOYMENT=false
  if [[ "$CURRENT_TG" == "$BACKEND_BLUE_TG" ]]; then
    PREVIOUS_IMAGE=$(get_container_image "${INSTANCES[0]}" "backend_blue")
  else
    PREVIOUS_IMAGE=$(get_container_image "${INSTANCES[0]}" "backend_green")
  fi
  [[ -z "$PREVIOUS_IMAGE" || "$PREVIOUS_IMAGE" == "null" ]] && PREVIOUS_IMAGE="$FULL_IMAGE"
fi

# === Deployment logic ===
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  # First-time deployment: deploy both colors
  for instance in "${INSTANCES[@]}"; do
    deploy_container "$instance" $BACKEND_BLUE_PORT "BLUE"
    deploy_container "$instance" $BACKEND_GREEN_PORT "GREEN"

    # === Register both colors to respective target groups ===
    aws elbv2 register-targets --target-group-arn "$BACKEND_BLUE_TG" --targets Id="$instance",Port=$BACKEND_BLUE_PORT
    aws elbv2 register-targets --target-group-arn "$BACKEND_GREEN_TG" --targets Id="$instance",Port=$BACKEND_GREEN_PORT

    DEPLOYED_INSTANCES+=("$instance")
  done
  ACTIVE_ENV="GREEN"
  INACTIVE_ENV="BLUE"
  ACTIVE_TG="$BACKEND_GREEN_TG"
  INACTIVE_TG="$BACKEND_BLUE_TG"
else
  # Subsequent deploy
  if [[ "$CURRENT_TG" == "$BACKEND_BLUE_TG" ]]; then
    ACTIVE_ENV="BLUE"; NEW_COLOR="GREEN"; NEW_PORT=$BACKEND_GREEN_PORT; NEW_TG="$BACKEND_GREEN_TG"; OLD_TG="$BACKEND_BLUE_TG"
  else
    ACTIVE_ENV="GREEN"; NEW_COLOR="BLUE"; NEW_PORT=$BACKEND_BLUE_PORT; NEW_TG="$BACKEND_BLUE_TG"; OLD_TG="$BACKEND_GREEN_TG"
  fi

  for instance in "${INSTANCES[@]}"; do
    deploy_container "$instance" $NEW_PORT "$NEW_COLOR"

    # === Register the new color to its target group ===
    if [[ "$NEW_COLOR" == "BLUE" ]]; then
      aws elbv2 register-targets --target-group-arn "$BACKEND_BLUE_TG" --targets Id="$instance",Port=$BACKEND_BLUE_PORT
    else
      aws elbv2 register-targets --target-group-arn "$BACKEND_GREEN_TG" --targets Id="$instance",Port=$BACKEND_GREEN_PORT
    fi

    DEPLOYED_INSTANCES+=("$instance")
  done


  ACTIVE_ENV="$ACTIVE_ENV"
  INACTIVE_ENV="$NEW_COLOR"
  ACTIVE_TG="$OLD_TG"
  INACTIVE_TG="$NEW_TG"
fi

# Strip Docker username from images
CURRENT_IMAGE_SHORT=$(echo "$FULL_IMAGE" | awk -F/ '{print $NF}')
PREVIOUS_IMAGE_SHORT=$(echo "$PREVIOUS_IMAGE" | awk -F/ '{print $NF}')

# === SUCCESS outputs ===
{
  echo "backend_status=success"
  echo "backend_active_env=$ACTIVE_ENV"
  echo "backend_inactive_env=$INACTIVE_ENV"
  echo "backend_active_tg=$ACTIVE_TG"
  echo "backend_inactive_tg=$INACTIVE_TG"
  echo "backend_current_image=$CURRENT_IMAGE_SHORT"
  echo "backend_previous_image=$PREVIOUS_IMAGE_SHORT"
  echo "backend_first_deployment=$BACKEND_FIRST_DEPLOYMENT"
  echo "backend_deployed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "backend_deployed_by=${GITHUB_ACTOR:-manual}"
  echo "backend_instance_ids=${INSTANCE_IDS}"
} | tee >(cat) >> "$GITHUB_OUTPUT"

echo "✅ Backend deployment completed. configuration will be done in the metadata job
exit 0
