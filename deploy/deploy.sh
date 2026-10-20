#!/usr/bin/env bash
# Runs on the EC2 instance (as root, via SSM). Writes .env from SSM Parameter Store, pulls the
# API image from ECR and (re)starts the compose stack.
#
# Usage: deploy.sh <image-repo-uri> <image-tag> <aws-region>
set -euo pipefail

IMAGE_REPO="$1"
IMAGE_TAG="${2:-latest}"
REGION="$3"
cd /opt/pharmacore

# Every /pharmacore/prod/<NAME> parameter becomes NAME=value
umask 077
aws ssm get-parameters-by-path --region "$REGION" --path /pharmacore/prod/ --recursive --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text \
  | while IFS=$'\t' read -r name value; do printf '%s=%s\n' "${name##*/}" "$value"; done > .env.new
mv .env.new .env
grep -q '^DATABASE_URL=' .env || { echo "DATABASE_URL is missing from /pharmacore/prod/"; exit 1; }

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${IMAGE_REPO%%/*}"

export API_IMAGE="$IMAGE_REPO:$IMAGE_TAG"
export AWS_REGION="$REGION"

# Container logs go to CloudWatch Logs only once /pharmacore/prod/CLOUDWATCH_LOGS is "true"
COMPOSE=(docker compose -f docker-compose.prod.yml)
if grep -qx 'CLOUDWATCH_LOGS=true' .env; then
  COMPOSE+=(-f docker-compose.cloudwatch.yml)
  echo "Logging to CloudWatch Logs (/pharmacore/api, /pharmacore/proxy)"
fi

"${COMPOSE[@]}" pull
"${COMPOSE[@]}" up -d --remove-orphans

# The container runs the Alembic migrations before uvicorn starts, so allow a few minutes
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/ >/dev/null; then
    echo "API is up: $API_IMAGE"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 5
done

echo "API did not become healthy; last log lines:"
"${COMPOSE[@]}" logs --tail 50 api
exit 1
