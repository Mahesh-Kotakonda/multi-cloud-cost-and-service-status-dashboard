#!/bin/bash
set -euo pipefail

#########################################
# deploy-backend.sh
# Blue-Green Deployment for Backend (Containers Only)
#########################################

# === DEFAULT CONFIG ===
BACKEND_BLUE_PORT=8080
BACKEND_GREEN_PORT=8081

# === ARG PARSING ===
while [[ $# -gt 0 ]]; do
    case "$1" in
        --outputs-json)          OUTPUTS_JSON="$2"; shift 2 ;;
        --pem-path)              PEM_PATH="$2"; shift 2 ;;
        --db-host)               DB_HOST="$2"; shift 2 ;;
        --db-port)               DB_PORT="$2"; shift 2 ;;
        --db-name)               DB_NAME="$2"; shift 2 ;;
        --db-user)               DB_USER="$2"; shift 2 ;;
        --db-pass)               DB_PASS="$2"; shift 2 ;;
        --dockerhub-username)    DOCKERHUB_USERNAME="$2"; shift 2 ;;
        --dockerhub-token)       DOCKERHUB_TOKEN="$2"; shift 2 ;;
        --image-tag)             IMAGE_TAG="$2"; shift 2 ;;   # full image ref (username/repo:tag)
        --instance-ids)          INSTANCE_IDS="$2"; shift 2 ;;
        --blue-tg)               BACKEND_BLUE_TG="$2"; shift 2 ;;
        --green-tg)              BACKEND_GREEN_TG="$2"; shift 2 ;;
        --aws-access-key-id)     AWS_ACCESS_KEY_ID="$2"; shift 2 ;;
        --aws-secret-access-key) AWS_SECRET_ACCESS_KEY="$2"; shift 2 ;;
        --aws-region)            AWS_REGION="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# === VALIDATE INPUTS ===
if [[ -z "${OUTPUTS_JSON:-}" ]]; then echo "Must provide --outputs-json"; exit 1; fi
if [[ -z "${INSTANCE_IDS:-}" ]]; then echo "Must provide --instance-ids"; exit 1; fi
if [[ -z "${BACKEND_BLUE_TG:-}" || -z "${BACKEND_GREEN_TG:-}" ]]; then
    echo "Must provide --blue-tg and --green-tg"; exit 1
fi

IFS=',' read -ra INSTANCES <<< "$INSTANCE_IDS"

# === EXPORT AWS CREDS ===
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION

# === FUNCTION TO FETCH CURRENT CONTAINER IMAGE ===
get_current_container_image() {
    local instance_id=$1
    local color=$2
    local container_name="backend_${color,,}"
    IP=$(aws ec2 describe-instances --instance-ids "$instance_id" \
        --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" \
        "docker inspect --format '{{.Config.Image}}' $container_name" 2>/dev/null || echo ""
}

# === DEPLOY FUNCTION ===
deploy_container() {
    local instance_id=$1
    local port=$2
    local color=$3
    local docker_image=$4
    local container_name="backend_${color,,}"

    IP=$(aws ec2 describe-instances --instance-ids "$instance_id" \
        --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

    echo "Deploying backend $color on $instance_id ($IP) with image $docker_image"

    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" bash <<EOF
set -e
if docker ps -a --format '{{.Names}}' | grep -q '^${container_name}\$'; then
    echo "Stopping and removing existing container $container_name"
    docker stop $container_name || true
    docker rm $container_name || true
fi

echo "Logging in to Docker Hub..."
echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin

echo "Pulling image $docker_image..."
docker pull "$docker_image"

echo "Running container $container_name on port $port..."
docker run -d -p $port:8000 \
    --name $container_name \
    -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    -e AWS_REGION=$AWS_REGION \
    -e DB_HOST=$DB_HOST \
    -e DB_PORT=$DB_PORT \
    -e DB_NAME=$DB_NAME \
    -e DB_USER=$DB_USER \
    -e DB_PASS=$DB_PASS \
    "$docker_image"
EOF
}

# === FETCH CURRENT ACTIVE TG ===
LISTENER_ARN=$(jq -r '.alb_listener_arn' "$OUTPUTS_JSON")
if [[ -z "$LISTENER_ARN" || "$LISTENER_ARN" == "null" ]]; then
    echo "Could not fetch alb_listener_arn from $OUTPUTS_JSON"
    exit 1
fi

CURRENT_TG=$(aws elbv2 describe-rules \
    --listener-arn "$LISTENER_ARN" \
    --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values,'/api/aws/*')]].Actions[0].ForwardConfig.TargetGroups[0].TargetGroupArn" \
    --output text || echo "")

echo "Current active backend Target Group ARN: $CURRENT_TG"

# === FIRST-TIME DEPLOYMENT ===
if [[ -z "$CURRENT_TG" || "$CURRENT_TG" == "None" ]]; then
    echo "First-time backend deployment. Deploying BLUE and GREEN with same image but attaching BLUE only..."
    for instance in "${INSTANCES[@]}"; do
        deploy_container "$instance" "$BACKEND_BLUE_PORT" "BLUE" "$IMAGE_TAG"
        deploy_container "$instance" "$BACKEND_GREEN_PORT" "GREEN" "$IMAGE_TAG"
        echo "Registering BLUE instance $instance to target group $BACKEND_BLUE_TG"
        aws elbv2 register-targets --target-group-arn "$BACKEND_BLUE_TG" --targets Id=$instance,Port=$BACKEND_BLUE_PORT
    done

    DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Strip username from image
    IMAGE_CLEAN=$(echo "$IMAGE_TAG" | cut -d'/' -f2)

    echo "backend_active_env=GREEN" >> $GITHUB_OUTPUT
    echo "backend_current_image=$IMAGE_CLEAN" >> $GITHUB_OUTPUT
    echo "backend_previous_image=$IMAGE_CLEAN" >> $GITHUB_OUTPUT
    echo "backend_blue_tg=$BACKEND_BLUE_TG" >> $GITHUB_OUTPUT
    echo "backend_green_tg=$BACKEND_GREEN_TG" >> $GITHUB_OUTPUT
    echo "backend_deployed_at=$DEPLOYED_AT" >> $GITHUB_OUTPUT
    echo "backend_deployed_by=$GITHUB_ACTOR" >> $GITHUB_OUTPUT
    echo "backend_status=success" >> $GITHUB_OUTPUT

    echo "Backend BLUE is live."
    exit 0
fi

# === NORMAL BLUE/GREEN SWITCH ===
if [[ "$CURRENT_TG" == *"blue"* ]]; then
    CURRENT_COLOR="BLUE"
    NEXT_COLOR="GREEN"
    NEW_TG="$BACKEND_GREEN_TG"
    NEW_PORT=$BACKEND_GREEN_PORT
else
    CURRENT_COLOR="GREEN"
    NEXT_COLOR="BLUE"
    NEW_TG="$BACKEND_BLUE_TG"
    NEW_PORT=$BACKEND_BLUE_PORT
fi

echo "$CURRENT_COLOR active → deploying $NEXT_COLOR"

# === FETCH CURRENT IMAGE OF ACTIVE COLOR ===
CURRENT_IMAGE=$(get_current_container_image "${INSTANCES[0]}" "$CURRENT_COLOR")
NEW_IMAGE="$IMAGE_TAG"

# Strip username from images for output
NEW_IMAGE_CLEAN=$(echo "$NEW_IMAGE" | cut -d'/' -f2)
CURRENT_IMAGE_CLEAN=$(echo "$CURRENT_IMAGE" | cut -d'/' -f2)

# === DEPLOY NEW IMAGE TO NEXT COLOR ===
for instance in "${INSTANCES[@]}"; do
    deploy_container "$instance" "$NEW_PORT" "$NEXT_COLOR" "$NEW_IMAGE"
    echo "Registering $NEXT_COLOR instance $instance to target group $NEW_TG"
    aws elbv2 register-targets --target-group-arn "$NEW_TG" --targets Id=$instance,Port=$NEW_PORT
done

# === PUBLISH OUTPUTS ===
DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "backend_current_image=$NEW_IMAGE_CLEAN" >> $GITHUB_OUTPUT
echo "backend_previous_image=$CURRENT_IMAGE_CLEAN" >> $GITHUB_OUTPUT
echo "backend_active_env=$CURRENT_COLOR" >> $GITHUB_OUTPUT
echo "backend_blue_tg=$BACKEND_BLUE_TG" >> $GITHUB_OUTPUT
echo "backend_green_tg=$BACKEND_GREEN_TG" >> $GITHUB_OUTPUT
echo "backend_deployed_at=$DEPLOYED_AT" >> $GITHUB_OUTPUT
echo "backend_deployed_by=$GITHUB_ACTOR" >> $GITHUB_OUTPUT
echo "backend_status=success" >> $GITHUB_OUTPUT

echo "Backend $NEXT_COLOR deployment complete."
