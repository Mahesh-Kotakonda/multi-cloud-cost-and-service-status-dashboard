#!/bin/bash
set -euo pipefail

#########################################
# deploy-frontend.sh
# Blue-Green Deployment for Frontend (Rule-Based)
#########################################

# === DEFAULT CONFIG ===
FRONTEND_BLUE_PORT=3000
FRONTEND_GREEN_PORT=3001
LISTENER_ARN=""

# === ARG PARSING ===
while [[ $# -gt 0 ]]; do
  case "$1" in
    --outputs-json)          OUTPUTS_JSON="$2"; shift 2 ;;
    --pem-path)              PEM_PATH="$2"; shift 2 ;;
    --dockerhub-username)    DOCKERHUB_USERNAME="$2"; shift 2 ;;
    --dockerhub-token)       DOCKERHUB_TOKEN="$2"; shift 2 ;;
    --image-tag)             IMAGE_TAG="$2"; shift 2 ;;   # full image ref (username/repo:tag)
    --instance-ids)          INSTANCE_IDS="$2"; shift 2 ;;
    --blue-tg)               FRONTEND_BLUE_TG="$2"; shift 2 ;;
    --green-tg)              FRONTEND_GREEN_TG="$2"; shift 2 ;;
    --aws-access-key-id)     AWS_ACCESS_KEY_ID="$2"; shift 2 ;;
    --aws-secret-access-key) AWS_SECRET_ACCESS_KEY="$2"; shift 2 ;;
    --aws-region)            AWS_REGION="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# === VALIDATE REQUIREMENTS ===
if [[ -z "${OUTPUTS_JSON:-}" ]]; then echo "Must provide --outputs-json"; exit 1; fi
if [[ -z "${INSTANCE_IDS:-}" ]]; then echo "Must provide --instance-ids"; exit 1; fi
if [[ -z "${FRONTEND_BLUE_TG:-}" || -z "${FRONTEND_GREEN_TG:-}" ]]; then echo "Must provide --blue-tg and --green-tg"; exit 1; fi
if [[ -z "${IMAGE_TAG:-}" ]]; then echo "Must provide --image-tag (full image ref)"; exit 1; fi

# === FETCH LISTENER ARN ===
LISTENER_ARN=$(jq -r '.alb_listener_arn' "$OUTPUTS_JSON")
if [[ -z "$LISTENER_ARN" || "$LISTENER_ARN" == "null" ]]; then
  echo "Could not fetch alb_listener_arn from $OUTPUTS_JSON"; exit 1
fi

# === EXPORT AWS CREDS ===
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION
IFS=',' read -ra INSTANCES <<< "$INSTANCE_IDS"

# === DEPLOY FUNCTION ===
deploy_container() {
  local instance_id=$1
  local port=$2
  local color=$3
  local docker_image=$4
  local container_name="frontend_${color,,}"

  IP=$(aws ec2 describe-instances --instance-ids "$instance_id" \
        --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

  echo "Deploying frontend $color on $instance_id ($IP) with image $docker_image"

  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" bash <<EOF
    set -e
    if docker ps -a --format '{{.Names}}' | grep -q '^${container_name}\$'; then
      docker stop $container_name || true
      docker rm $container_name || true
    fi

    echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
    docker pull "$docker_image"

    docker run -d -p $port:3000 --name $container_name "$docker_image"
EOF
}

# === FETCH CURRENT IMAGE OF ACTIVE COLOR ===
get_current_container_image() {
  local instance_id=$1
  local color=$2
  local container_name="frontend_${color,,}"
  IP=$(aws ec2 describe-instances --instance-ids "$instance_id" \
      --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" \
      "docker inspect --format '{{.Config.Image}}' $container_name" 2>/dev/null || echo ""
}

# === DETERMINE CURRENT FRONTEND TG BASED ON "/" RULE ===
CURRENT_TG=$(aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/')]].Actions[0].ForwardConfig.TargetGroups[0].TargetGroupArn" \
  --output text || echo "")
echo "Current active frontend Target Group ARN: $CURRENT_TG"

DOCKER_IMAGE="$IMAGE_TAG"

# Strip username from image for outputs
IMAGE_CLEAN=$(echo "$DOCKER_IMAGE" | cut -d'/' -f2)

# === FIRST-TIME DEPLOYMENT ===
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  echo "First-time frontend deployment. Deploying FRONTEND BLUE + GREEN (but only registering BLUE)..."
  for instance in "${INSTANCES[@]}"; do
    deploy_container "$instance" "$FRONTEND_BLUE_PORT" "BLUE" "$DOCKER_IMAGE"
    deploy_container "$instance" "$FRONTEND_GREEN_PORT" "GREEN" "$DOCKER_IMAGE"
    aws elbv2 register-targets --target-group-arn "$FRONTEND_BLUE_TG" --targets Id=$instance,Port=$FRONTEND_BLUE_PORT
  done

  DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  echo "frontend_active_env=BLUE" >> $GITHUB_OUTPUT
  echo "frontend_current_image=$IMAGE_CLEAN" >> $GITHUB_OUTPUT
  echo "frontend_previous_image=$IMAGE_CLEAN" >> $GITHUB_OUTPUT
  echo "frontend_blue_tg=$FRONTEND_BLUE_TG" >> $GITHUB_OUTPUT
  echo "frontend_green_tg=$FRONTEND_GREEN_TG" >> $GITHUB_OUTPUT
  echo "frontend_deployed_at=$DEPLOYED_AT" >> $GITHUB_OUTPUT
  echo "frontend_deployed_by=$GITHUB_ACTOR" >> $GITHUB_OUTPUT
  echo "frontend_status=success" >> $GITHUB_OUTPUT
  exit 0
fi

# === NORMAL BLUE/GREEN SWITCH ===
if [[ "$CURRENT_TG" == *"blue"* ]]; then
  CURRENT_COLOR="BLUE"
  NEXT_COLOR="GREEN"
  NEW_TG="$FRONTEND_GREEN_TG"
  NEW_PORT=$FRONTEND_GREEN_PORT
else
  CURRENT_COLOR="GREEN"
  NEXT_COLOR="BLUE"
  NEW_TG="$FRONTEND_BLUE_TG"
  NEW_PORT=$FRONTEND_BLUE_PORT
fi

echo "$CURRENT_COLOR active → deploying $NEXT_COLOR"

CURRENT_IMAGE=$(get_current_container_image "${INSTANCES[0]}" "$CURRENT_COLOR")
NEW_IMAGE="$DOCKER_IMAGE"

# Strip username for outputs
NEW_IMAGE_CLEAN=$(echo "$NEW_IMAGE" | cut -d'/' -f2)
CURRENT_IMAGE_CLEAN=$(echo "$CURRENT_IMAGE" | cut -d'/' -f2)

for instance in "${INSTANCES[@]}"; do
  deploy_container "$instance" "$NEW_PORT" "$NEXT_COLOR" "$NEW_IMAGE"
  aws elbv2 register-targets --target-group-arn "$NEW_TG" --targets Id=$instance,Port=$NEW_PORT
done

DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "frontend_current_image=$NEW_IMAGE_CLEAN" >> $GITHUB_OUTPUT
echo "frontend_previous_image=$CURRENT_IMAGE_CLEAN" >> $GITHUB_OUTPUT
echo "frontend_active_env=$NEXT_COLOR" >> $GITHUB_OUTPUT
echo "frontend_blue_tg=$FRONTEND_BLUE_TG" >> $GITHUB_OUTPUT
echo "frontend_green_tg=$FRONTEND_GREEN_TG" >> $GITHUB_OUTPUT
echo "frontend_deployed_at=$DEPLOYED_AT" >> $GITHUB_OUTPUT
echo "frontend_deployed_by=$GITHUB_ACTOR" >> $GITHUB_OUTPUT
echo "frontend_status=success" >> $GITHUB_OUTPUT

echo "Frontend $NEXT_COLOR deployment complete!"
