#!/bin/bash
set -euo pipefail

#########################################
# deploy-frontend.sh
# Blue-Green Deployment for Frontend (Containers Only)
#########################################

FRONTEND_BLUE_PORT=3000
FRONTEND_GREEN_PORT=3001
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
if [[ -z "${FRONTEND_IMAGE:-}" ]]; then
  echo "ERROR: FRONTEND_IMAGE env var is required"
  exit 1
fi
if [[ -z "${DOCKERHUB_USERNAME:-}" || -z "${DOCKERHUB_TOKEN:-}" ]]; then
  echo "ERROR: DOCKERHUB_USERNAME and DOCKERHUB_TOKEN env vars are required"
  exit 1
fi

FULL_IMAGE="$DOCKERHUB_USERNAME/$FRONTEND_IMAGE"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION

INSTANCE_IDS=$(jq -r '.ec2_instance_ids | join(",")' "$OUTPUTS_JSON" 2>/dev/null || echo "")
FRONTEND_BLUE_TG=$(jq -r '.frontend_blue_tg_arn' "$OUTPUTS_JSON" 2>/dev/null || echo "")
FRONTEND_GREEN_TG=$(jq -r '.frontend_green_tg_arn' "$OUTPUTS_JSON" 2>/dev/null || echo "")
LISTENER_ARN=$(jq -r '.alb_listener_arn' "$OUTPUTS_JSON" 2>/dev/null || echo "")

BACKEND_INSTANCE_IDS="${BACKEND_INSTANCE_IDS:-}"
IFS=',' read -ra BACKEND_INSTANCES <<< "$BACKEND_INSTANCE_IDS"
BACKEND_INACTIVE_ENV="${BACKEND_INACTIVE_ENV:-}"
BACKEND_FIRST_DEPLOYMENT="${BACKEND_FIRST_DEPLOYMENT:-false}"


if [[ -z "$INSTANCE_IDS" ]]; then
  echo "ERROR: no frontend instance ids found in $OUTPUTS_JSON"
  exit 1
fi

IFS=',' read -ra INSTANCES <<< "$INSTANCE_IDS"
IFS=',' read -ra BACKEND_INSTANCES <<< "$BACKEND_INSTANCE_IDS"

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
  local container_name="frontend_${color,,}"
  local ip="$(_get_ip "$instance_id")"

  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      DOCKERHUB_USERNAME="$DOCKERHUB_USERNAME" \
      DOCKERHUB_TOKEN="$DOCKERHUB_TOKEN" \
      FULL_IMAGE="$FULL_IMAGE" \
      CONTAINER_NAME="$container_name" \
      PORT="$port" \
      bash <<'EOF'
set -euo pipefail
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true
echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
docker pull "$FULL_IMAGE"
docker run -d -p "$PORT":3000 --name "$CONTAINER_NAME" "$FULL_IMAGE"
EOF
}

rollback_frontend_both_on() {
  for instance_id in "$@"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f frontend_blue frontend_green 2>/dev/null || true"
  done
}

rollback_frontend_color_on() {
  local color="$1"; shift
  color="$(echo "$color" | tr '[:upper:]' '[:lower:]')"
  for instance_id in "$@"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f frontend_${color} 2>/dev/null || true"
  done
}

rollback_worker_new() {
  for instance_id in "${WORKER_INSTANCES[@]:-}"; do
    ip="$(_get_ip "$instance_id")"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
      "docker rm -f worker_new 2>/dev/null || true"
  done
}

rollback_backend_all() {
  local backend_first_deployment=$1
  local backend_inactive_env=$2
  shift 2
  local backend_instances=("$@")

  if [[ "$backend_first_deployment" == "true" ]]; then
    echo "Rolling back ALL backend containers on instances: ${backend_instances[*]}"
    for instance_id in "${backend_instances[@]}"; do
      ip="$(_get_ip "$instance_id")"
      ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
        "docker rm -f backend_blue backend_green 2>/dev/null || true"
    done
  else
    echo "Rolling back only INACTIVE backend ($backend_inactive_env) on instances: ${backend_instances[*]}"
    color="${backend_inactive_env,,}"
    for instance_id in "${backend_instances[@]}"; do
      ip="$(_get_ip "$instance_id")"
      ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$ip" \
        "docker rm -f backend_${color} 2>/dev/null || true"
    done
  fi
}

# === Main deployment ===
CURRENT_TG=$(aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/')]].Actions[0].ForwardConfig.TargetGroups[0].TargetGroupArn" \
  --output text || echo "")

DEPLOYED_INSTANCES=()

if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  FRONTEND_FIRST_DEPLOYMENT=true
  PREVIOUS_IMAGE="$FULL_IMAGE"
else
  FRONTEND_FIRST_DEPLOYMENT=false
  if [[ "$CURRENT_TG" == "$FRONTEND_BLUE_TG" ]]; then
    PREVIOUS_IMAGE=$(get_container_image "${INSTANCES[0]}" "frontend_blue")
  else
    PREVIOUS_IMAGE=$(get_container_image "${INSTANCES[0]}" "frontend_green")
  fi
  [[ -z "$PREVIOUS_IMAGE" || "$PREVIOUS_IMAGE" == "null" ]] && PREVIOUS_IMAGE="$FULL_IMAGE"
fi
echo "Previous image: $PREVIOUS_IMAGE"

# === Deployment logic ===
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  # First-time deployment: deploy both BLUE and GREEN
  for instance in "${INSTANCES[@]}"; do
    echo "→ deploying BLUE on $instance"
    set +e
    deploy_container "$instance" $FRONTEND_BLUE_PORT "BLUE"
    status_blue=$?
    set -e
    if [[ $status_blue -ne 0 ]]; then
      print_container_logs "$instance" "frontend_blue"
      rollback_frontend_both_on "${DEPLOYED_INSTANCES[@]}" "$instance"
      rollback_worker_new
      rollback_backend_all
      { echo "frontend_status=failed"; echo "frontend_active_env=NONE"; echo "frontend_inactive_env=NONE"; echo "frontend_current_image=$FULL_IMAGE"; echo "frontend_previous_image=$PREVIOUS_IMAGE"; echo "frontend_instance_ids=${INSTANCE_IDS}"; } >> "$GITHUB_OUTPUT"
      exit 1
    fi

    echo "→ deploying GREEN on $instance"
    set +e
    deploy_container "$instance" $FRONTEND_GREEN_PORT "GREEN"
    status_green=$?
    set -e
    if [[ $status_green -ne 0 ]]; then
      print_container_logs "$instance" "frontend_green"
      rollback_frontend_both_on "${DEPLOYED_INSTANCES[@]}" "$instance"
      rollback_worker_new
      rollback_backend_all
      { echo "frontend_status=failed"; echo "frontend_active_env=NONE"; echo "frontend_inactive_env=NONE"; echo "frontend_current_image=$FULL_IMAGE"; echo "frontend_previous_image=$PREVIOUS_IMAGE"; echo "frontend_instance_ids=${INSTANCE_IDS}"; } >> "$GITHUB_OUTPUT"
      exit 1
    fi
    DEPLOYED_INSTANCES+=("$instance")
  done

  echo "Registering BLUE as active target group..."
  aws elbv2 modify-listener \
    --listener-arn "$LISTENER_ARN" \
    --default-actions "Type=forward,ForwardConfig={TargetGroups=[{TargetGroupArn=$FRONTEND_BLUE_TG,Weight=1}]}"

  ACTIVE_ENV="GREEN"
  INACTIVE_ENV="BLUE"
  ACTIVE_TG="$FRONTEND_GREEN_TG"
  INACTIVE_TG="$FRONTEND_BLUE_TG"
else
  # Subsequent deploy: deploy new color
  if [[ "$CURRENT_TG" == "$FRONTEND_BLUE_TG" ]]; then
    ACTIVE_ENV="BLUE"; NEW_COLOR="GREEN"; NEW_PORT=$FRONTEND_GREEN_PORT; NEW_TG="$FRONTEND_GREEN_TG"; OLD_TG="$FRONTEND_BLUE_TG"; INACTIVE_ENV="GREEN"
  else
    ACTIVE_ENV="GREEN"; NEW_COLOR="BLUE"; NEW_PORT=$FRONTEND_BLUE_PORT; NEW_TG="$FRONTEND_BLUE_TG"; OLD_TG="$FRONTEND_GREEN_TG"; INACTIVE_ENV="BLUE"
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
      print_container_logs "$instance" "frontend_${NEW_COLOR,,}"
      rollback_frontend_color_on "$NEW_COLOR" "${DEPLOYED_INSTANCES[@]}" "$instance"
      rollback_worker_new
      rollback_backend_all
      { echo "frontend_status=failed"; echo "frontend_active_env=$ACTIVE_ENV"; echo "frontend_inactive_env=$NEW_COLOR"; echo "frontend_current_image=$FULL_IMAGE"; echo "frontend_previous_image=$PREVIOUS_IMAGE"; echo "frontend_instance_ids=${INSTANCE_IDS}"; } >> "$GITHUB_OUTPUT"
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

# Strip Docker username from frontend images
CURRENT_IMAGE_SHORT=$(echo "$FULL_IMAGE" | awk -F/ '{print $NF}')
PREVIOUS_IMAGE_SHORT=$(echo "$PREVIOUS_IMAGE" | awk -F/ '{print $NF}')

# === SUCCESS outputs ===
{
  echo "frontend_status=success"
  echo "frontend_active_env=$ACTIVE_ENV"
  echo "frontend_inactive_env=$INACTIVE_ENV"
  echo "frontend_active_tg=$ACTIVE_TG"
  echo "frontend_inactive_tg=$INACTIVE_TG"
  echo "frontend_current_image=$CURRENT_IMAGE_SHORT"
  echo "frontend_previous_image=$PREVIOUS_IMAGE_SHORT"
  echo "frontend_first_deployment=$FRONTEND_FIRST_DEPLOYMENT"
  echo "frontend_deployed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "frontend_deployed_by=${GITHUB_ACTOR:-manual}"
  echo "frontend_instance_ids=${INSTANCE_IDS}"
} | tee >(cat) >> "$GITHUB_OUTPUT"


echo "✅ Frontend deployment completed. Active env: $ACTIVE_ENV"
exit 0
