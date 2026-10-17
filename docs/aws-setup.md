# One-time AWS setup for PharmaCore

This guide creates the AWS resources described in [AWS_DEPLOYMENT_PLAN.md](AWS_DEPLOYMENT_PLAN.md). You only do it once. After that, everything runs from GitHub Actions:

- **Frontend** builds on changes to `frontend/`, and deploys to S3 and CloudFront on `main`.
- **Backend** tests on changes to `backend/` or `deploy/`, and deploys to ECR and EC2 on `main`.
- **Lab control** has start and stop buttons.

Run the commands in Git Bash or another POSIX shell with AWS CLI v2 and `jq` installed, signed in as an admin user of your account (`aws configure` or `aws login`). Keep the same shell open from start to finish, because later steps use variables set in earlier ones.

```bash
REGION=eu-north-1                      # pick the region closest to you and use it everywhere
GH_REPO=Sreerajraveendran/Pharma       # <owner>/<repo> on GitHub
export AWS_REGION=$REGION
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET=pharmacore-web-$ACCOUNT
```

---

## 1. Billing alerts (console)

1. Go to **Billing and Cost Management → Budgets → Create budget → Customize (advanced) → Cost budget**.
2. Make it a **Monthly** budget with a fixed amount of **$15**. Normal study use is $5–7 a month, and running 24/7 is about $26, so $15 catches a forgotten lab.
3. Under **Advanced options**, **untick Credits**. Credits cover your whole bill, so a budget that counts them sees about $0 and never alerts.
4. Add three alerts, all to your email:
   - actual cost above 50%;
   - actual cost above 100%;
   - forecasted cost above 100%.
5. Check **Billing → Credits** about once a week.

If you'd rather click through the AWS console than run commands, [aws-console-setup.md](aws-console-setup.md) covers every step that way.

## 2. Security groups (default VPC)

```bash
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
CF_PL=$(aws ec2 describe-managed-prefix-lists \
  --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
  --query 'PrefixLists[0].PrefixListId' --output text)

# EC2: port 80 from CloudFront only. No SSH; use Session Manager.
SG_EC2=$(aws ec2 create-security-group --group-name pharmacore-ec2 --vpc-id $VPC \
  --description "PharmaCore API - CloudFront only" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_EC2 \
  --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=$CF_PL}]"

# RDS: Postgres from the EC2 security group only
SG_RDS=$(aws ec2 create-security-group --group-name pharmacore-rds --vpc-id $VPC \
  --description "PharmaCore DB - from API only" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_RDS \
  --protocol tcp --port 5432 --source-group $SG_EC2
```

## 3. RDS PostgreSQL 16 (takes about 10 minutes)

```bash
DB_PASSWORD=$(openssl rand -hex 24)    # hex only: no characters that need escaping in a URL or .env
aws rds create-db-instance \
  --db-instance-identifier pharmacore-db \
  --engine postgres --engine-version 16 \
  --db-instance-class db.t4g.micro \
  --allocated-storage 20 --storage-type gp2 \
  --master-username pharmacore --master-user-password "$DB_PASSWORD" \
  --db-name pharmacore \
  --vpc-security-group-ids $SG_RDS \
  --no-publicly-accessible --no-multi-az \
  --backup-retention-period 1 \
  --no-enable-performance-insights
aws rds wait db-instance-available --db-instance-identifier pharmacore-db
DB_HOST=$(aws rds describe-db-instances --db-instance-identifier pharmacore-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)
```

Storage autoscaling stays off because no `--max-allocated-storage` is set. The database is not publicly accessible and only `pharmacore-ec2` can reach it.

## 4. App settings in SSM Parameter Store (free)

`deploy.sh` turns every `/pharmacore/prod/NAME` parameter into a `NAME=value` line in `.env` on the instance.

```bash
put()  { aws ssm put-parameter --overwrite --name "/pharmacore/prod/$1" --type String       --value "$2" >/dev/null; }
sput() { aws ssm put-parameter --overwrite --name "/pharmacore/prod/$1" --type SecureString --value "$2" >/dev/null; }

# RDS for PostgreSQL 16 requires SSL
sput DATABASE_URL "postgresql+asyncpg://pharmacore:$DB_PASSWORD@$DB_HOST:5432/pharmacore?ssl=require"
sput BOOTSTRAP_ADMIN_PASSWORD "$(openssl rand -hex 12)"   # temporary; the app forces a change on first login
put  BOOTSTRAP_ADMIN_EMAIL   "you@example.com"
put  BOOTSTRAP_ADMIN_NAME    "System Administrator"
put  ENVIRONMENT             production
put  ENABLE_DOCS             false
put  COOKIE_SECURE           true
put  DB_POOL_SIZE            5
put  SEED_DEMO_DATA          true        # sample data in the empty DB, useful for study
put  ALLOW_DEMO_RESET        false
put  ALLOW_SELF_REGISTRATION true

# Read the admin password back when you need it:
aws ssm get-parameter --name /pharmacore/prod/BOOTSTRAP_ADMIN_PASSWORD --with-decryption --query Parameter.Value --output text
```

## 5. ECR repository for the API image

```bash
aws ecr create-repository --repository-name pharmacore-api >/dev/null
aws ecr put-lifecycle-policy --repository-name pharmacore-api --lifecycle-policy-text '{
  "rules": [{ "rulePriority": 1, "description": "keep last 3",
    "selection": { "tagStatus": "any", "countType": "imageCountMoreThan", "countNumber": 3 },
    "action": { "type": "expire" } }]
}'
```

## 6. EC2 instance

```bash
# Instance role: Session Manager, ECR pull, read /pharmacore/prod/*
aws iam create-role --role-name pharmacore-ec2 --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [{ "Effect": "Allow", "Principal": { "Service": "ec2.amazonaws.com" }, "Action": "sts:AssumeRole" }]
}' >/dev/null
aws iam attach-role-policy --role-name pharmacore-ec2 --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam attach-role-policy --role-name pharmacore-ec2 --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
aws iam put-role-policy --role-name pharmacore-ec2 --policy-name app-params --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    { \"Effect\": \"Allow\", \"Action\": \"ssm:GetParametersByPath\",
      \"Resource\": \"arn:aws:ssm:$REGION:$ACCOUNT:parameter/pharmacore/prod*\" },
    { \"Effect\": \"Allow\", \"Action\": \"kms:Decrypt\", \"Resource\": \"*\",
      \"Condition\": { \"StringEquals\": { \"kms:ViaService\": \"ssm.$REGION.amazonaws.com\" } } }
  ]
}"
aws iam create-instance-profile --instance-profile-name pharmacore-ec2 >/dev/null
aws iam add-role-to-instance-profile --instance-profile-name pharmacore-ec2 --role-name pharmacore-ec2
sleep 15   # let the new instance profile propagate

AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)
SUBNET=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC Name=default-for-az,Values=true \
  --query 'Subnets[0].SubnetId' --output text)
EC2_ID=$(aws ec2 run-instances \
  --image-id $AMI --instance-type t3.micro \
  --subnet-id $SUBNET --associate-public-ip-address \
  --security-group-ids $SG_EC2 \
  --iam-instance-profile Name=pharmacore-ec2 \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=10,VolumeType=gp3}' \
  --metadata-options HttpTokens=required \
  --credit-specification CpuCredits=standard \
  --user-data file://deploy/user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=pharmacore-api}]' \
  --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-status-ok --instance-ids $EC2_ID
EC2_DNS=$(aws ec2 describe-instances --instance-ids $EC2_ID \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)
```

`CpuCredits=standard` matters. In the default `unlimited` mode, a t3 instance that stays busy is billed for extra CPU.

## 7. S3 bucket and CloudFront distribution

```bash
# Private bucket. AWS blocks public access on new buckets by default.
if [ "$REGION" = us-east-1 ]; then
  aws s3api create-bucket --bucket $BUCKET
else
  aws s3api create-bucket --bucket $BUCKET --create-bucket-configuration LocationConstraint=$REGION
fi

# SPA deep-link rewrite function
aws cloudfront create-function --name pharmacore-spa-rewrite \
  --function-config Comment="SPA routes to index.html",Runtime=cloudfront-js-2.0 \
  --function-code fileb://deploy/cloudfront/spa-rewrite.js > fn.json
aws cloudfront publish-function --name pharmacore-spa-rewrite --if-match $(jq -r .ETag fn.json) >/dev/null
FN_ARN=$(jq -r .FunctionSummary.FunctionMetadata.FunctionARN fn.json)

# Origin access control: only CloudFront may read the bucket
OAC_ID=$(aws cloudfront create-origin-access-control --origin-access-control-config \
  Name=pharmacore-s3,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3 \
  --query OriginAccessControl.Id --output text)
```

Create the distribution. The IDs below are AWS managed policies:

| Managed policy | ID |
|---|---|
| CachingOptimized | `658327ea-f89d-4fab-a63d-7e88639e58f6` |
| CachingDisabled | `4135ea2d-6df8-44a3-9df3-4b5a84be39ad` |
| AllViewerExceptHostHeader | `b689b0a8-53d0-40ab-baf2-68738e2966ac` |

```bash
cat > dist.json <<EOF
{
  "CallerReference": "pharmacore-$(date +%s)",
  "Comment": "PharmaCore",
  "Enabled": true,
  "DefaultRootObject": "index.html",
  "PriceClass": "PriceClass_200",
  "HttpVersion": "http2and3",
  "Origins": { "Quantity": 2, "Items": [
    { "Id": "s3-web", "DomainName": "$BUCKET.s3.$REGION.amazonaws.com",
      "OriginAccessControlId": "$OAC_ID",
      "S3OriginConfig": { "OriginAccessIdentity": "" } },
    { "Id": "ec2-api", "DomainName": "$EC2_DNS",
      "CustomOriginConfig": { "HTTPPort": 80, "HTTPSPort": 443,
        "OriginProtocolPolicy": "http-only", "OriginReadTimeout": 60 } }
  ]},
  "DefaultCacheBehavior": {
    "TargetOriginId": "s3-web",
    "ViewerProtocolPolicy": "redirect-to-https",
    "Compress": true,
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    "FunctionAssociations": { "Quantity": 1, "Items": [
      { "EventType": "viewer-request", "FunctionARN": "$FN_ARN" } ] }
  },
  "CacheBehaviors": { "Quantity": 1, "Items": [
    { "PathPattern": "/api/*",
      "TargetOriginId": "ec2-api",
      "ViewerProtocolPolicy": "redirect-to-https",
      "Compress": true,
      "AllowedMethods": { "Quantity": 7,
        "Items": ["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"],
        "CachedMethods": { "Quantity": 2, "Items": ["GET","HEAD"] } },
      "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
      "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac" }
  ]}
}
EOF
aws cloudfront create-distribution --distribution-config file://dist.json > cf.json
CF_ID=$(jq -r .Distribution.Id cf.json)
CF_DOMAIN=$(jq -r .Distribution.DomainName cf.json)

# Allow only this distribution to read the bucket
aws s3api put-bucket-policy --bucket $BUCKET --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{ \"Effect\": \"Allow\",
    \"Principal\": { \"Service\": \"cloudfront.amazonaws.com\" },
    \"Action\": \"s3:GetObject\", \"Resource\": \"arn:aws:s3:::$BUCKET/*\",
    \"Condition\": { \"StringEquals\": {
      \"AWS:SourceArn\": \"arn:aws:cloudfront::$ACCOUNT:distribution/$CF_ID\" } } }]
}"
echo "App URL: https://$CF_DOMAIN/"
```

Do not add distribution-wide custom error pages. They would also replace the API's JSON 404 and 403 responses with `index.html`. The `spa-rewrite` function handles deep links instead.

## 8. Nightly auto-stop (EventBridge Scheduler, free)

This step matters because AWS starts a stopped RDS instance again after 7 days.

```bash
aws iam create-role --role-name pharmacore-scheduler --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [{ "Effect": "Allow", "Principal": { "Service": "scheduler.amazonaws.com" }, "Action": "sts:AssumeRole" }]
}' >/dev/null
aws iam put-role-policy --role-name pharmacore-scheduler --policy-name stop-lab --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    { \"Effect\": \"Allow\", \"Action\": \"ec2:StopInstances\",
      \"Resource\": \"arn:aws:ec2:$REGION:$ACCOUNT:instance/$EC2_ID\" },
    { \"Effect\": \"Allow\", \"Action\": \"rds:StopDBInstance\",
      \"Resource\": \"arn:aws:rds:$REGION:$ACCOUNT:db:pharmacore-db\" }
  ]
}"
sleep 10
SCHED_ROLE=arn:aws:iam::$ACCOUNT:role/pharmacore-scheduler
TZ_NAME=Asia/Kolkata      # your time zone

aws scheduler create-schedule --name pharmacore-stop-ec2 \
  --schedule-expression "cron(30 23 * * ? *)" --schedule-expression-timezone $TZ_NAME \
  --flexible-time-window Mode=OFF \
  --target "{\"Arn\":\"arn:aws:scheduler:::aws-sdk:ec2:stopInstances\",\"RoleArn\":\"$SCHED_ROLE\",
             \"Input\":\"{\\\"InstanceIds\\\":[\\\"$EC2_ID\\\"]}\"}"

aws scheduler create-schedule --name pharmacore-stop-rds \
  --schedule-expression "cron(30 23 * * ? *)" --schedule-expression-timezone $TZ_NAME \
  --flexible-time-window Mode=OFF \
  --target "{\"Arn\":\"arn:aws:scheduler:::aws-sdk:rds:stopDBInstance\",\"RoleArn\":\"$SCHED_ROLE\",
             \"Input\":\"{\\\"DbInstanceIdentifier\\\":\\\"pharmacore-db\\\"}\"}"
```

If the database is already stopped, the RDS schedule fails harmlessly that night.

## 9. GitHub OIDC role (no AWS keys stored in GitHub)

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com

# GitHub's token now names the repo as owner@OWNER_ID/repo@REPO_ID. Allow both that and the older format.
GH_OWNER=${GH_REPO%%/*}; GH_NAME=${GH_REPO##*/}
GH_IDS=$(curl -fsS https://api.github.com/repos/$GH_REPO | jq -r '"\(.owner.id) \(.id)"')
GH_OWNER_ID=${GH_IDS% *}; GH_REPO_ID=${GH_IDS#* }

aws iam create-role --role-name pharmacore-gha --assume-role-policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{ \"Effect\": \"Allow\",
    \"Principal\": { \"Federated\": \"arn:aws:iam::$ACCOUNT:oidc-provider/token.actions.githubusercontent.com\" },
    \"Action\": \"sts:AssumeRoleWithWebIdentity\",
    \"Condition\": {
      \"StringEquals\": { \"token.actions.githubusercontent.com:aud\": \"sts.amazonaws.com\" },
      \"StringLike\": { \"token.actions.githubusercontent.com:sub\": [
        \"repo:$GH_OWNER@$GH_OWNER_ID/$GH_NAME@$GH_REPO_ID:ref:refs/heads/main\",
        \"repo:$GH_REPO:ref:refs/heads/main\" ] } } }]
}" >/dev/null

aws iam put-role-policy --role-name pharmacore-gha --policy-name deploy --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    { \"Effect\": \"Allow\", \"Action\": [\"s3:ListBucket\"], \"Resource\": \"arn:aws:s3:::$BUCKET\" },
    { \"Effect\": \"Allow\", \"Action\": [\"s3:PutObject\", \"s3:DeleteObject\"], \"Resource\": \"arn:aws:s3:::$BUCKET/*\" },
    { \"Effect\": \"Allow\",
      \"Action\": [\"cloudfront:CreateInvalidation\", \"cloudfront:GetDistribution\",
                   \"cloudfront:GetDistributionConfig\", \"cloudfront:UpdateDistribution\"],
      \"Resource\": \"arn:aws:cloudfront::$ACCOUNT:distribution/$CF_ID\" },
    { \"Effect\": \"Allow\", \"Action\": \"ecr:GetAuthorizationToken\", \"Resource\": \"*\" },
    { \"Effect\": \"Allow\",
      \"Action\": [\"ecr:BatchCheckLayerAvailability\", \"ecr:BatchGetImage\", \"ecr:GetDownloadUrlForLayer\",
                   \"ecr:InitiateLayerUpload\", \"ecr:UploadLayerPart\", \"ecr:CompleteLayerUpload\", \"ecr:PutImage\"],
      \"Resource\": \"arn:aws:ecr:$REGION:$ACCOUNT:repository/pharmacore-api\" },
    { \"Effect\": \"Allow\", \"Action\": [\"ec2:DescribeInstances\", \"ec2:DescribeInstanceStatus\"], \"Resource\": \"*\" },
    { \"Effect\": \"Allow\", \"Action\": [\"ec2:StartInstances\", \"ec2:StopInstances\"],
      \"Resource\": \"arn:aws:ec2:$REGION:$ACCOUNT:instance/$EC2_ID\" },
    { \"Effect\": \"Allow\", \"Action\": [\"rds:DescribeDBInstances\", \"rds:StartDBInstance\", \"rds:StopDBInstance\"],
      \"Resource\": \"arn:aws:rds:$REGION:$ACCOUNT:db:pharmacore-db\" },
    { \"Effect\": \"Allow\", \"Action\": \"ssm:SendCommand\",
      \"Resource\": [\"arn:aws:ec2:$REGION:$ACCOUNT:instance/$EC2_ID\",
                     \"arn:aws:ssm:$REGION::document/AWS-RunShellScript\"] },
    { \"Effect\": \"Allow\", \"Action\": [\"ssm:GetCommandInvocation\", \"ssm:DescribeInstanceInformation\"], \"Resource\": \"*\" }
  ]
}"
```

## 10. GitHub repository secrets and variables

In GitHub, open **Settings → Secrets and variables → Actions**.
- **Secrets tab:** four values that contain your account ID or resource IDs. The repo is public, and secrets show as `***` in its Actions logs.
- **Variables tab:** the generic names.

Print the values with:

```bash
cat <<EOF
--- Secrets tab ---
AWS_ROLE_ARN=arn:aws:iam::$ACCOUNT:role/pharmacore-gha
S3_BUCKET=$BUCKET
CF_DISTRIBUTION_ID=$CF_ID
EC2_INSTANCE_ID=$EC2_ID
--- Variables tab ---
AWS_REGION=$REGION
ECR_REPOSITORY=pharmacore-api
CF_API_ORIGIN_ID=ec2-api
RDS_INSTANCE_ID=pharmacore-db
EOF
```

Or set them with the GitHub CLI:
```bash
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::$ACCOUNT:role/pharmacore-gha"
gh secret set S3_BUCKET --body "$BUCKET"
gh secret set CF_DISTRIBUTION_ID --body "$CF_ID"
gh secret set EC2_INSTANCE_ID --body "$EC2_ID"
gh variable set AWS_REGION --body "$REGION"
gh variable set ECR_REPOSITORY --body pharmacore-api
gh variable set CF_API_ORIGIN_ID --body ec2-api
gh variable set RDS_INSTANCE_ID --body pharmacore-db
```

---

## First deploy

1. Run **Lab control → start**, then run **Actions → Frontend → Run workflow** and **Actions → Backend → Run workflow**. The first deploy needs both, and later pushes only run the part that changed. Frontend uploads the SPA. Backend tests, pushes the image and deploys it to the running instance.
2. Open `https://$CF_DOMAIN/`. Sign in with `BOOTSTRAP_ADMIN_EMAIL` and the password from step 4, then change the password when asked.
3. When you're done, run **Actions → Lab control → stop**.

## Daily use

| When | What to do |
|---|---|
| Start studying | **Lab control → start**. Takes about 10–15 minutes. The URL is in the job summary. |
| Change code | Push to `main`. Only the workflow for the part you changed runs. While the lab is stopped, Backend still pushes the image, and the next start deploys it. |
| Finish | **Lab control → stop**. The nightly schedule at 23:30 stops everything anyway. |
| Shell on the server | **EC2 console → Connect → Session Manager**, then `sudo docker compose -f /opt/pharmacore/docker-compose.prod.yml logs -f api` |

## Before the 6 months or the credits run out

1. Back up the database from a Session Manager shell:
   ```bash
   sudo docker run --rm --env-file /opt/pharmacore/.env postgres:16-alpine \
     sh -c 'pg_dump "$(echo $DATABASE_URL | sed "s/+asyncpg//; s/ssl=require/sslmode=require/")"' > pharmacore.sql
   ```
   Then copy `pharmacore.sql` somewhere you keep.
2. Either upgrade to a paid plan, or delete everything in this order: CloudFront distribution (disable it first), S3 bucket, EC2, RDS (skip the final snapshot), ECR, SSM parameters, schedules and IAM roles.
