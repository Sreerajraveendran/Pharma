#!/usr/bin/env bash
# Runs on the GitHub Actions runner. Copies the deploy/ files to the EC2 instance through SSM
# Run Command (no SSH) and runs deploy.sh there, then prints its output.
#
# Usage: deploy/ship.sh <instance-id> <image-repo-uri> <image-tag> <aws-region>
set -euo pipefail

INSTANCE_ID="$1"
IMAGE_REPO="$2"
IMAGE_TAG="$3"
REGION="$4"
HERE="$(cd "$(dirname "$0")" && pwd)"

# The SSM agent needs a moment after boot before it accepts commands
for _ in $(seq 1 40); do
  PING=$(aws ssm describe-instance-information \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || true)
  [ "$PING" = "Online" ] && break
  echo "Waiting for the SSM agent (status: $PING)..."
  sleep 10
done
[ "$PING" = "Online" ] || { echo "::error::SSM agent on $INSTANCE_ID is not online"; exit 1; }

# The three files are small, so they travel inside the command itself as a base64 tarball
BUNDLE=$(tar czf - -C "$HERE" docker-compose.prod.yml nginx-api.conf deploy.sh | base64 -w0)
REMOTE="set -e; mkdir -p /opt/pharmacore; echo '$BUNDLE' | base64 -d | tar xzf - -C /opt/pharmacore; \
bash /opt/pharmacore/deploy.sh '$IMAGE_REPO' '$IMAGE_TAG' '$REGION'"
PARAMS=$(jq -nc --arg c "$REMOTE" '{commands: [$c], executionTimeout: ["900"]}')

COMMAND_ID=$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "pharmacore deploy $IMAGE_TAG" \
  --parameters "$PARAMS" \
  --query Command.CommandId --output text)
echo "SSM command: $COMMAND_ID"

# `aws ssm wait command-executed` gives up after ~100 s, too short for an image pull
STATUS=Pending
for _ in $(seq 1 90); do
  sleep 10
  STATUS=$(aws ssm get-command-invocation --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
    --query Status --output text 2>/dev/null || echo Pending)
  case "$STATUS" in Pending|InProgress|Delayed) continue ;; *) break ;; esac
done

aws ssm get-command-invocation --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
  --query '[StandardOutputContent, StandardErrorContent]' --output text || true

[ "$STATUS" = "Success" ] || { echo "::error::Deploy on $INSTANCE_ID finished with status $STATUS"; exit 1; }
