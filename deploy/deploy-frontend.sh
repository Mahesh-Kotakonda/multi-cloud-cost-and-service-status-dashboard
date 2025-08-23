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
    --outputs-json)         OUTPUTS_JSON="$2"; shift 2 ;;
    --pem-path)             PEM_PATH="$2"; shift 2 ;;
    --dockerhub-username)   DOCKERHUB_USERNAME="$2"; shift 2 ;;
    --dockerhub-token)      DOCKERHUB_TOKEN="$2"; shift 2 ;;
    --image-repo)           IMAGE_REPO="$2"; shift 2 ;;
    --instance-ids)         INSTANCE_IDS="$2"; shift 2 ;;
    --blue-tg)              FRONTEND_BLUE_TG="$2"; shift 2 ;;
    --green-tg)             FRONTEND_GREEN_TG="$2"; shift 2 ;;
    --aws-access-key-id)    AWS_ACCESS_KEY_ID="$2"; shift 2 ;;
    --aws-secret-access-key) AWS_SECRET_ACCESS_KEY="$2"; shift 2 ;;
    --aws-region)           AWS_REGION="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# === VALIDATE REQUIREMENTS ===
if [[ -z "${OUTPUTS_JSON:-}" ]]; then echo "Must provide --outputs-json"; exit 1; fi
if [[ -z "${INSTANCE_IDS:-}" ]]; then echo "Must provide --instance-ids"; exit 1; fi
if [[ -z "${FRONTEND_BLUE_TG:-}" || -z "${FRONTEND_GREEN_TG:-}" ]]; then echo "Must provide --blue-tg and --green-tg"; exit 1; fi

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
  local container_name="frontend_${color,,}"

  IP=$(aws ec2 describe-instances --instance-ids "$instance_id" \
        --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

  echo "Deploying frontend $color on $instance_id ($IP)"

  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" bash <<EOF
    set -e
    if docker ps -a --format '{{.Names}}' | grep -q '^${container_name}\$'; then
      docker stop $container_name || true
      docker rm $container_name || true
    fi

    echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
    docker pull "$DOCKERHUB_USERNAME/$IMAGE_REPO:frontend-latest"

    docker run -d -p $port:3000 --name $container_name "$DOCKERHUB_USERNAME/$IMAGE_REPO:frontend-latest"
EOF
}

# === CREATE OR UPDATE FRONTEND RULES ===
create_or_update_frontend_rule() {
  local tg=$1
  local priority=500

  # Paths to forward to frontend TG
  declare -a paths=("/" "/favicon.ico" "/robots.txt" "/static/*")

  for path in "${paths[@]}"; do
    RULE_ARN=$(aws elbv2 describe-rules \
      --listener-arn "$LISTENER_ARN" \
      --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'$path')]].RuleArn" \
      --output text || echo "")
    
    if [[ -z "$RULE_ARN" || "$RULE_ARN" == "None" ]]; then
      echo "Creating rule for $path -> TG $tg"
      aws elbv2 create-rule \
        --listener-arn "$LISTENER_ARN" \
        --priority $priority \
        --conditions Field=path-pattern,Values="$path" \
        --actions Type=forward,TargetGroupArn=$tg
    else
      echo "Updating rule for $path -> TG $tg"
      aws elbv2 modify-rule \
        --rule-arn "$RULE_ARN" \
        --conditions Field=path-pattern,Values="$path" \
        --actions Type=forward,TargetGroupArn=$tg
    fi
    ((priority++))
  done

  # Catch-all invalid paths -> 404
  CATCH_ALL_ARN=$(aws elbv2 describe-rules \
    --listener-arn "$LISTENER_ARN" \
    --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/*')]].RuleArn" \
    --output text || echo "")
  if [[ -z "$CATCH_ALL_ARN" || "$CATCH_ALL_ARN" == "None" ]]; then
    echo "Creating catch-all 404 for /*"
    echo '{"MessageBody":"Not Found","StatusCode":"404","ContentType":"text/plain"}' > fixed-response.json
    aws elbv2 create-rule \
      --listener-arn "$LISTENER_ARN" \
      --priority 1000 \
      --conditions Field=path-pattern,Values='/*' \
      --actions "Type=fixed-response,FixedResponseConfig=file://fixed-response.json"
    rm -f fixed-response.json
  else
    echo "Updating catch-all 404 for /*"
    aws elbv2 modify-rule \
      --rule-arn "$CATCH_ALL_ARN" \
      --conditions Field=path-pattern,Values='/*' \
      --actions "Type=fixed-response,FixedResponseConfig=file://fixed-response.json"
  fi
}

# === DETERMINE CURRENT FRONTEND TG BASED ON / RULE ONLY ===
CURRENT_TG=$(aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/')]].Actions[0].ForwardConfig.TargetGroups[0].TargetGroupArn" \
  --output text || echo "")

echo "Current active frontend Target Group ARN: $CURRENT_TG"

# === FIRST-TIME DEPLOYMENT ===
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
  echo "First-time frontend deployment. Deploying FRONTEND BLUE only..."
  for instance in "${INSTANCES[@]}"; do
    deploy_container "$instance" "$FRONTEND_BLUE_PORT" "BLUE"
    aws elbv2 register-targets --target-group-arn "$FRONTEND_BLUE_TG" --targets Id=$instance,Port=$FRONTEND_BLUE_PORT
  done
  create_or_update_frontend_rule "$FRONTEND_BLUE_TG"
  echo "Frontend BLUE is live."
  exit 0
fi

# === NORMAL BLUE/GREEN SWITCH ===
if [[ "$CURRENT_TG" == *"blue"* ]]; then
  CURRENT_COLOR="BLUE"
  NEXT_COLOR="GREEN"
  NEW_TG="$FRONTEND_GREEN_TG"
  NEW_PORT=$FRONTEND_GREEN_PORT
elif [[ "$CURRENT_TG" == *"green"* ]]; then
  CURRENT_COLOR="GREEN"
  NEXT_COLOR="BLUE"
  NEW_TG="$FRONTEND_BLUE_TG"
  NEW_PORT=$FRONTEND_BLUE_PORT
else
  echo "Unknown current frontend TG. Exiting."
  exit 1
fi

echo "$CURRENT_COLOR active → deploying $NEXT_COLOR"

for instance in "${INSTANCES[@]}"; do
  deploy_container "$instance" "$NEW_PORT" "$NEXT_COLOR"
  aws elbv2 register-targets --target-group-arn "$NEW_TG" --targets Id=$instance,Port=$NEW_PORT
done

echo "Updating listener rules for $NEXT_COLOR"
create_or_update_frontend_rule "$NEW_TG"

echo "Frontend $NEXT_COLOR deployment complete!"
