#!/bin/bash
set -euo pipefail

#########################################
# deploy-backend.sh
# Blue-Green Deployment for Backend (Rule-Based)
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
    --aws-access-key-id)   AWS_ACCESS_KEY_ID="$2"; shift 2 ;;
    --aws-secret-access-key) AWS_SECRET_ACCESS_KEY="$2"; shift 2 ;;
    --aws-region)          AWS_REGION="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# === VALIDATE REQUIREMENTS ===
if [[ -z "${OUTPUTS_JSON:-}" ]]; then
  echo "Must provide --outputs-json"; exit 1
fi

if [[ -z "${INSTANCE_IDS:-}" ]]; then
  echo "Must provide --instance-ids"; exit 1
fi
if [[ -z "${BACKEND_BLUE_TG:-}" || -z "${BACKEND_GREEN_TG:-}" ]]; then
  echo "Must provide --blue-tg and --green-tg"; exit 1
fi

IFS=',' read -ra INSTANCES <<< "$INSTANCE_IDS"

# === FETCH LISTENER ARN FROM JSON ===
LISTENER_ARN=$(jq -r '.alb_listener_arn' "$OUTPUTS_JSON")
if [[ -z "$LISTENER_ARN" || "$LISTENER_ARN" == "null" ]]; then
  echo "Could not fetch alb_listener_arn from $OUTPUTS_JSON"; exit 1
fi

# === DEPLOY FUNCTION ===
deploy_container() {
  local instance_id=$1
  local port=$2
  local color=$3

  IP=$(aws ec2 describe-instances --instance-ids "$instance_id" \
        --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

  echo "Deploying backend $color on $instance_id ($IP)"

  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" bash <<EOF
    set -e
    docker ps -q --filter "publish=$port" | xargs -r docker stop | xargs -r docker rm || true

    echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
    docker pull "$DOCKERHUB_USERNAME/$IMAGE_REPO:backend-latest"

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
      "$DOCKERHUB_USERNAME/$IMAGE_REPO:backend-latest"
EOF
}

# === CREATE OR UPDATE LISTENER RULE ===
create_or_update_backend_rule() {
  local priority=$1
  local tg=$2

  RULE_ARN=$(aws elbv2 describe-rules \
    --listener-arn "$LISTENER_ARN" \
    --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/api/aws/*')]].RuleArn" \
    --output text || echo "")

  if [[ -z "$RULE_ARN" || "$RULE_ARN" == "None" ]]; then
    echo "Creating new listener rule for /api/aws/* -> TG $tg"
    aws elbv2 create-rule \
      --listener-arn "$LISTENER_ARN" \
      --priority $priority \
      --conditions Field=path-pattern,Values='/api/aws/*' \
      --actions Type=forward,TargetGroupArn=$tg
  else
    echo "Updating existing listener rule for /api/aws/* -> TG $tg"
    aws elbv2 modify-rule \
      --rule-arn "$RULE_ARN" \
      --conditions Field=path-pattern,Values='/api/aws/*' \
      --actions Type=forward,TargetGroupArn=$tg
  fi
}

# === DETERMINE CURRENT ACTIVE BACKEND TG VIA RULE ===
CURRENT_TG=$(aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/api/aws/*')]].Actions[0].ForwardConfig.TargetGroups[0].TargetGroupArn" \
  --output text)
echo "Current active backend Target Group ARN: $CURRENT_TG"

# === FIRST-TIME DEPLOYMENT ===
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  echo "First-time deployment detected. Deploying BOTH BLUE and GREEN..."

  for instance in "${INSTANCES[@]}"; do
    deploy_container "$instance" "$BACKEND_BLUE_PORT" "BLUE"
    aws elbv2 register-targets --target-group-arn "$BACKEND_BLUE_TG" --targets Id=$instance,Port=$BACKEND_BLUE_PORT

    deploy_container "$instance" "$BACKEND_GREEN_PORT" "GREEN"
    aws elbv2 register-targets --target-group-arn "$BACKEND_GREEN_TG" --targets Id=$instance,Port=$BACKEND_GREEN_PORT
  done

  echo "Waiting for BLUE targets to be healthy..."
  # aws elbv2 wait target-in-service --target-group-arn "$BACKEND_BLUE_TG"

  echo "Creating listener rule for /api/aws/* -> BACKEND BLUE"
  create_or_update_backend_rule 10 "$BACKEND_BLUE_TG"

  echo "First-time backend deployment complete. BACKEND BLUE is live."
  exit 0
fi

# === NORMAL BLUE/GREEN SWITCH ===
if [[ "$CURRENT_TG" == *"blue"* ]]; then
  CURRENT_COLOR="BLUE"
  NEXT_COLOR="GREEN"
  NEW_TG="$BACKEND_GREEN_TG"
  NEW_PORT=$BACKEND_GREEN_PORT
elif [[ "$CURRENT_TG" == *"green"* ]]; then
  CURRENT_COLOR="GREEN"
  NEXT_COLOR="BLUE"
  NEW_TG="$BACKEND_BLUE_TG"
  NEW_PORT=$BACKEND_BLUE_PORT
else
  echo "Unknown current backend Target Group. Exiting."
  exit 1
fi

echo "$CURRENT_COLOR active → deploying $NEXT_COLOR"

for instance in "${INSTANCES[@]}"; do
  deploy_container "$instance" "$NEW_PORT" "$NEXT_COLOR"
  aws elbv2 register-targets --target-group-arn "$NEW_TG" --targets Id=$instance,Port=$NEW_PORT
done

echo "Waiting for backend $NEXT_COLOR targets to be healthy..."
# aws elbv2 wait target-in-service --target-group-arn "$NEW_TG"

echo "Updating listener rule for /api/aws/* -> $NEXT_COLOR"
create_or_update_backend_rule 10 "$NEW_TG"

echo "Backend $NEXT_COLOR deployment complete."
