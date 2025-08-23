#!/bin/bash
set -euo pipefail

#########################################
# deploy-backend.sh
# Blue-Green Deployment for Backend
#########################################

# === DEFAULT CONFIG ===
BACKEND_BLUE_PORT=8080
BACKEND_GREEN_PORT=8081
LISTENER_ARN=""

# === ARG PARSING ===
while [[ $# -gt 0 ]]; do
  case "$1" in
    --outputs-json)        OUTPUTS_JSON="$2"; shift 2 ;;
    --pem-path)            PEM_PATH="$2"; shift 2 ;;
    --db-host)             DB_HOST="$2"; shift 2 ;;
    --db-port)             DB_PORT="$2"; shift 2 ;;
    --db-name)             DB_NAME="$2"; shift 2 ;;
    --db-user)             DB_USER="$2"; shift 2 ;;
    --db-pass)             DB_PASS="$2"; shift 2 ;;
    --dockerhub-username)  DOCKERHUB_USERNAME="$2"; shift 2 ;;
    --dockerhub-token)     DOCKERHUB_TOKEN="$2"; shift 2 ;;
    --image-repo)          IMAGE_REPO="$2"; shift 2 ;;
    --instance-ids)        INSTANCE_IDS="$2"; shift 2 ;;
    --blue-tg)             BACKEND_BLUE_TG="$2"; shift 2 ;;
    --green-tg)            BACKEND_GREEN_TG="$2"; shift 2 ;;
    --listener-arn)        LISTENER_ARN="$2"; shift 2 ;;
    --aws-access-key-id)   AWS_ACCESS_KEY_ID="$2"; shift 2 ;;
    --aws-secret-access-key) AWS_SECRET_ACCESS_KEY="$2"; shift 2 ;;
    --aws-region)          AWS_REGION="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "${OUTPUTS_JSON:-}" ]]; then
  echo "Must provide --outputs-json"; exit 1
fi

# === VALIDATE REQUIREMENTS ===
if [[ -z "${INSTANCE_IDS:-}" ]]; then
  echo "Must provide --instance-ids"; exit 1
fi
if [[ -z "${BACKEND_BLUE_TG:-}" || -z "${BACKEND_GREEN_TG:-}" ]]; then
  echo "Must provide --blue-tg and --green-tg"; exit 1
fi

# === DETERMINE CURRENT ACTIVE COLOR ===
CURRENT_TG=$(aws elbv2 describe-listeners \
  --listener-arns "$LISTENER_ARN" \
  --query "Listeners[0].DefaultActions[0].ForwardConfig.TargetGroups[0].TargetGroupArn" \
  --output text 2>/dev/null || echo "")

IFS=',' read -ra INSTANCES <<< "$INSTANCE_IDS"

# === FUNCTION TO DEPLOY A CONTAINER OVER SSH ===
deploy_container() {
  local instance_id=$1
  local port=$2
  local color=$3

  IP=$(aws ec2 describe-instances --instance-ids "$instance_id" \
        --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

  echo "Deploying backend $color on $instance_id ($IP)"

  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" bash <<EOF
    set -e
    # Remove old container if exists
    docker ps -q --filter "publish=$port" | xargs -r docker stop | xargs -r docker rm || true

    # Login and pull
    echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
    docker pull "$DOCKERHUB_USERNAME/$IMAGE_REPO:latest"

    # Run new container with AWS + DB creds
    docker run -d -p $port:$port \
      --name backend_${color,,} \
      -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
      -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
      -e AWS_REGION=$AWS_REGION \
      -e DB_HOST=$DB_HOST \
      -e DB_PORT=$DB_PORT \
      -e DB_NAME=$DB_NAME \
      -e DB_USER=$DB_USER \
      -e DB_PASS=$DB_PASS \
      "$DOCKERHUB_USERNAME/$IMAGE_REPO:latest"
EOF
}

# === FIRST-TIME DEPLOYMENT ===
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  echo "First-time deployment detected. Deploying BOTH blue and green..."

  for instance in "${INSTANCES[@]}"; do
    deploy_container "$instance" "$BACKEND_BLUE_PORT" "BLUE"
    aws elbv2 register-targets --target-group-arn "$BACKEND_BLUE_TG" --targets Id=$instance,Port=$BACKEND_BLUE_PORT

    deploy_container "$instance" "$BACKEND_GREEN_PORT" "GREEN"
    aws elbv2 register-targets --target-group-arn "$BACKEND_GREEN_TG" --targets Id=$instance,Port=$BACKEND_GREEN_PORT
  done

  echo "Waiting for BLUE targets to be healthy..."
  aws elbv2 wait target-in-service --target-group-arn "$BACKEND_BLUE_TG"

  echo "Switching ALB to backend BLUE"
  aws elbv2 modify-listener \
    --listener-arn "$LISTENER_ARN" \
    --default-actions "Type=forward,ForwardConfig={TargetGroups=[{TargetGroupArn=$BACKEND_BLUE_TG,Weight=1}]}"

  echo "First-time deployment complete. BLUE is live."
  exit 0
fi

# === NORMAL BLUE/GREEN SWITCH ===
if [[ "$CURRENT_TG" == "$BACKEND_BLUE_TG" ]]; then
  echo "BLUE active -> deploying GREEN"
  NEXT_COLOR="GREEN"
  NEW_TG="$BACKEND_GREEN_TG"
  NEW_PORT=$BACKEND_GREEN_PORT
else
  echo "GREEN active -> deploying BLUE"
  NEXT_COLOR="BLUE"
  NEW_TG="$BACKEND_BLUE_TG"
  NEW_PORT=$BACKEND_BLUE_PORT
fi

for instance in "${INSTANCES[@]}"; do
  deploy_container "$instance" "$NEW_PORT" "$NEXT_COLOR"
  aws elbv2 register-targets --target-group-arn "$NEW_TG" --targets Id=$instance,Port=$NEW_PORT
done

echo "Waiting for backend $NEXT_COLOR targets to be healthy..."
aws elbv2 wait target-in-service --target-group-arn "$NEW_TG"

echo "Switching ALB to backend $NEXT_COLOR"
aws elbv2 modify-listener \
  --listener-arn "$LISTENER_ARN" \
  --default-actions "Type=forward,ForwardConfig={TargetGroups=[{TargetGroupArn=$NEW_TG,Weight=1}]}"

echo "Backend $NEXT_COLOR deployment complete."
