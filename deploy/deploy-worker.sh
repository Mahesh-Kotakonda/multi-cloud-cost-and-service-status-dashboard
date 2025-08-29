#!/usr/bin/env bash
set -euo pipefail

WORKER_IMAGE="${1:-}"

# === Step 1: Check worker image ===
if [ -z "$WORKER_IMAGE" ] || [ "$WORKER_IMAGE" = "null" ]; then
  echo "No worker image provided. Skipping deployment."
  echo "worker_previous_image=" | tee -a "$GITHUB_OUTPUT"
  echo "worker_current_image=" | tee -a "$GITHUB_OUTPUT"
  echo "worker_deployed_instance_ids=" | tee -a "$GITHUB_OUTPUT"
  echo "worker_deploy_status=skipped" | tee -a "$GITHUB_OUTPUT"
  exit 0
fi

echo "Worker image: $WORKER_IMAGE"

# === Step 2: Fetch infra outputs ===
aws s3 cp "$S3_JSON_PATH" worker-outputs.json
if [ ! -f worker-outputs.json ]; then
  echo "ERROR: Failed to download $S3_JSON_PATH"
  echo "worker_previous_image=" | tee -a "$GITHUB_OUTPUT"
  echo "worker_current_image=$WORKER_IMAGE" | tee -a "$GITHUB_OUTPUT"
  echo "worker_deployed_instance_ids=" | tee -a "$GITHUB_OUTPUT"
  echo "worker_deploy_status=failed" | tee -a "$GITHUB_OUTPUT"
  exit 1
fi

DB_HOST=$(jq -r '.db.endpoint | split(":")[0]' worker-outputs.json)
DB_NAME=$(jq -r '.db.name' worker-outputs.json)
INSTANCE_IDS=$(jq -r '.ec2_instance_ids[]' worker-outputs.json)

if [ -z "$INSTANCE_IDS" ]; then
  echo "ERROR: No instance IDs found in infra outputs"
  echo "worker_previous_image=" | tee -a "$GITHUB_OUTPUT"
  echo "worker_current_image=$WORKER_IMAGE" | tee -a "$GITHUB_OUTPUT"
  echo "worker_deployed_instance_ids=" | tee -a "$GITHUB_OUTPUT"
  echo "worker_deploy_status=failed" | tee -a "$GITHUB_OUTPUT"
  exit 1
fi

# === Step 3: Fetch DB creds ===
PARAM_VALUE=$(aws ssm get-parameter --name "$SSM_PARAM_NAME" --with-decryption --query "Parameter.Value" --output text)
DB_USER=$(echo "$PARAM_VALUE" | jq -r '.username')
DB_PASS=$(echo "$PARAM_VALUE" | jq -r '.password')

SUCCESSFUL=()
FAILED=0
WORKER_PREVIOUS_IMAGE=""
FAILED_INSTANCE=""

# === Step 4: Deploy to instances sequentially ===
for ID in $INSTANCE_IDS; do
  echo "----"
  echo "Deploying to instance: $ID"

  IP=$(aws ec2 describe-instances --instance-ids "$ID" --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
  if [ "$IP" = "None" ]; then
    IP=$(aws ec2 describe-instances --instance-ids "$ID" --query "Reservations[0].Instances[0].PrivateIpAddress" --output text)
  fi
  echo "Instance $ID IP: $IP"

  # Get previous image from first instance only
  if [ -z "$WORKER_PREVIOUS_IMAGE" ]; then
    OLD_IMAGE=$(ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" \
      "docker inspect -f '{{.Config.Image}}' worker 2>/dev/null || echo ''")
    if [ -z "$OLD_IMAGE" ]; then
      echo "First deployment detected. Using current image as worker_previous_image."
      WORKER_PREVIOUS_IMAGE="$WORKER_IMAGE"
    else
      echo "Previous image on $ID: $OLD_IMAGE"
      WORKER_PREVIOUS_IMAGE="$OLD_IMAGE"
    fi
  fi

  # Deploy new worker container
  ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" bash -s <<EOF
set -euo pipefail
docker rm -f worker_new || true

echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
docker pull "$DOCKERHUB_USERNAME/$WORKER_IMAGE" || docker pull "$WORKER_IMAGE"

docker run -d --name worker_new \
  -e AWS_ACCESS_KEY_ID='$AWS_ACCESS_KEY_ID' \
  -e AWS_SECRET_ACCESS_KEY='$AWS_SECRET_ACCESS_KEY' \
  -e AWS_REGION='$AWS_REGION' \
  -e DB_HOST='$DB_HOST' \
  -e DB_NAME='$DB_NAME' \
  -e DB_USER='$DB_USER' \
  -e DB_PASS='$DB_PASS' \
  -e POLL_INTERVAL_SECONDS=60000 \
  "$DOCKERHUB_USERNAME/$WORKER_IMAGE"

sleep 25

if ! docker ps --filter 'name=worker_new' --filter 'status=running' | grep -q worker_new; then
  echo "Health check failed for worker_new"
  docker logs worker_new || true
  docker rm -f worker_new || true
  exit 2
fi
EOF

  RC=$?
  if [ "$RC" -eq 0 ]; then
    echo "Deployment succeeded on $ID"
    SUCCESSFUL+=("$ID")
  else
    echo "Deployment failed on $ID"
    FAILED=1
    FAILED_INSTANCE="$ID"
    break   # stop immediately, don’t try next instances
  fi
done

# === Step 5: Rollback if any failure ===
rollback_instances() {
  echo "Rolling back ${#SUCCESSFUL[@]} successful instances..."
  for ID in "${SUCCESSFUL[@]}"; do
    IP=$(aws ec2 describe-instances --instance-ids "$ID" --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
    if [ "$IP" = "None" ]; then
      IP=$(aws ec2 describe-instances --instance-ids "$ID" --query "Reservations[0].Instances[0].PrivateIpAddress" --output text)
    fi
    echo "Removing worker_new on $ID"
    ssh -o StrictHostKeyChecking=no -i "$PEM_PATH" ec2-user@"$IP" "docker rm -f worker_new || true"
  done
}

if [ "$FAILED" -eq 1 ]; then
  rollback_instances
  echo "worker_previous_image=$WORKER_PREVIOUS_IMAGE" | tee -a "$GITHUB_OUTPUT"
  echo "worker_current_image=$WORKER_IMAGE" | tee -a "$GITHUB_OUTPUT"
  echo "worker_deployed_instance_ids=" | tee -a "$GITHUB_OUTPUT"   # empty on failure
  echo "worker_deploy_status=failed" | tee -a "$GITHUB_OUTPUT"
  exit 1
fi

# === Step 6: Success output ===
DEPLOYED_CSV=$(IFS=,; echo "${SUCCESSFUL[*]}")
echo "worker_previous_image=$WORKER_PREVIOUS_IMAGE" | tee -a "$GITHUB_OUTPUT"
echo "worker_current_image=$WORKER_IMAGE" | tee -a "$GITHUB_OUTPUT"
echo "worker_deployed_instance_ids=$DEPLOYED_CSV" | tee -a "$GITHUB_OUTPUT"
echo "worker_deploy_status=success" | tee -a "$GITHUB_OUTPUT"
