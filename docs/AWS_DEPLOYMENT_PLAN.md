# PharmaCore on AWS for study (S3 + CloudFront + EC2 + RDS, Docker, GitHub Actions)

## Context
PharmaCore needs to be hosted on AWS for study purposes. The account is on the AWS **Free plan with $140 in credits for 6 months**. Resources are created once and **only run while studying**: they are stopped otherwise, and stopped automatically every night.

At about 2–4 hours a day this costs **$5–7/month, so $30–42 of the $140**. Leaving everything running 24/7 would cost about $26/month and use up the credits in about 5.4 months.

What the app is made of:
- **Frontend:** a Vite/React SPA. `npm run build` writes to `frontend/dist`. It calls the API on the same origin under `/api`.
- **Backend:** FastAPI on port 8000. [backend/Dockerfile](../backend/Dockerfile) runs `alembic upgrade head` and then starts uvicorn.
- **Database:** PostgreSQL 16.

What exists today: [docker-compose.yml](../docker-compose.yml), [frontend/nginx/nginx.conf](../frontend/nginx/nginx.conf) (contains the `/api` proxy and the login/register rate limits), and [.env.example](../.env.example). Before this work there was no CI.

## Architecture
```
Browser ─HTTPS─> CloudFront (d123.cloudfront.net, free default cert)
                  ├─ /*      → S3 bucket (private, OAC)  + CloudFront Function: SPA rewrite → /index.html
                  └─ /api/*  → EC2 t3.micro public DNS :80   (SG: only CloudFront origin-facing prefix list)
                                 docker compose: proxy (nginx, rate limits) → api (FastAPI :8000)
                                                                                  │
                                 RDS PostgreSQL 16 db.t4g.micro (private, SG: 5432 from EC2 SG) ◄┘
Images: ECR (lifecycle: keep last 3)   Secrets/env: SSM Parameter Store /pharmacore/prod/*
Auto-stop: EventBridge Scheduler stops EC2 + RDS nightly
```

**Cost decisions:**
- No NAT Gateway, no ALB, no Elastic IP.
- EC2 has an 8–10 GB gp3 disk; RDS has 20 GB, single-AZ, with 1-day backups.
- Env values live in SSM Parameter Store rather than Secrets Manager.

**Public DNS changes on every EC2 start.** The `lab-control` workflow (below) updates the CloudFront origin each time it starts EC2.

## GitHub Actions workflows

The workflows are split by part of the app, not by test and deploy. Path filters mean a push only rebuilds and redeploys the part that changed: a frontend-only change never restarts the API, and a backend change never re-uploads the SPA.

In both files, the deploy job runs only on `main`, never on pull requests, and only after the test or build job passes. Only the deploy jobs get `id-token: write`. They log in to AWS with `aws-actions/configure-aws-credentials@v4` and `role-to-assume: ${{ secrets.AWS_ROLE_ARN }}` and `mask-aws-account-id: true` (OIDC, so no access keys are stored).

### 1. `.github/workflows/frontend.yml`
Runs on changes to `frontend/**`: on push to `main`, on pull requests, and on manual `workflow_dispatch`.
- **build job:** Node 20, `npm ci`, `npm run build`. The build runs `tsc --noEmit`, so types are checked. It uploads `dist` as an artifact. There's no lint step because ESLint isn't installed or configured in `frontend/` yet.
- **deploy job** (`main` only):
  1. Download the `dist` artifact.
  2. `aws s3 sync dist/assets s3://$S3_BUCKET/assets --cache-control "public,max-age=31536000,immutable"`.
  3. `aws s3 sync dist s3://$S3_BUCKET --exclude "assets/*" --cache-control "no-cache" --delete`.
  4. `aws cloudfront create-invalidation --distribution-id $CF_DISTRIBUTION_ID --paths "/index.html" "/"`.
- This workflow doesn't touch EC2, so it works while the lab is stopped and doesn't take the lab lock.

### 2. `.github/workflows/backend.yml`
Runs on changes to `backend/**` or `deploy/**`: on push to `main`, on pull requests, and on manual `workflow_dispatch`.
- **test job:**
  - Runs on `ubuntu-latest` with a `postgres:16-alpine` service container.
  - Sets up Python 3.13 and runs `pip install -r backend/requirements-dev.txt`.
  - Runs `pytest` with `TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres`. `backend/tests/conftest.py` already supports this: it creates a throwaway database and runs the real migrations.
- **deploy job** (`main` only; shares the `pharmacore-aws` lock with lab-control):
  1. `aws-actions/amazon-ecr-login@v2`.
  2. `docker build ./backend` for `linux/amd64`, which matches t3.micro and is native on the runner.
  3. Tag the image `:<commit sha>` and `:latest`, and push both to ECR.
  4. Check EC2 state with `aws ec2 describe-instances`. If it is `running`, run [deploy/ship.sh](../deploy/ship.sh). It sends the deploy files and `deploy.sh <sha>` through `aws ssm send-command` (AWS-RunShellScript), polls until the command finishes (the built-in waiter gives up after about 100 s), and prints the output.
  5. If the instance is stopped, write a notice and skip; the next `lab-control start` will deploy `:latest`.

### 3. `.github/workflows/lab-control.yml`: start or stop the lab (manual `workflow_dispatch`, input `action: start | stop`)
- **start:**
  1. `aws rds start-db-instance`, then `aws rds wait db-instance-available` (5–10 minutes).
  2. `aws ec2 start-instances`, then `aws ec2 wait instance-status-ok`.
  3. Read the new `PublicDnsName`.
  4. `aws cloudfront get-distribution-config`, set the `ec2-api` origin's DomainName with `jq`, then run `update-distribution` with `--if-match <ETag>`. Propagation takes about 2–5 minutes.
  5. Run `deploy.sh latest` on the instance through SSM.
  6. Smoke test: `curl -fsS https://<dist>.cloudfront.net/api/...` returns 401/200, not 5xx; retry for a few minutes.
- **stop:** `aws ec2 stop-instances` and `aws rds stop-db-instance`. Ignore the "already stopped" error.
- In the job summary, print the app URL and a reminder that RDS restarts on its own after 7 days. The nightly scheduler covers that.

## Files added to the repo
- **[deploy/docker-compose.prod.yml](../deploy/docker-compose.prod.yml):**
  - `api` uses the image `${ECR_REPO}:${IMAGE_TAG}`, `env_file: .env`, `restart: unless-stopped`, port `127.0.0.1:8000:8000` (used for the health check).
  - `proxy` is `nginx:1.27-alpine` on `80:80`, mounting `nginx-api.conf`, `restart: unless-stopped`.
  - There is no postgres service.
- **[deploy/docker-compose.cloudwatch.yml](../deploy/docker-compose.cloudwatch.yml):** an optional override that sends the api and proxy logs to the CloudWatch Logs groups `/pharmacore/api` and `/pharmacore/proxy`. `deploy.sh` adds it only when the parameter `/pharmacore/prod/CLOUDWATCH_LOGS` is `true`. The setup is step 11 of the console guide.
- **[deploy/nginx-api.conf](../deploy/nginx-api.conf):**
  - Copy the `limit_req_zone`, the `/api/auth/login`, `/api/auth/register` and `/api/` locations, `client_max_body_size 20m`, gzip and `proxy_read_timeout 120s` from [frontend/nginx/nginx.conf](../frontend/nginx/nginx.conf). Leave out the static-file and SPA blocks.
  - Add `set_real_ip_from 0.0.0.0/0; real_ip_header X-Forwarded-For; real_ip_recursive off;`. With recursive off, nginx uses the last XFF entry, which is the client IP CloudFront appends. The security group allows only CloudFront, so this is safe, and the per-IP rate limits and audit-log IPs stay correct.
- **[deploy/deploy.sh](../deploy/deploy.sh)**, runs on the instance. `ship.sh` sends it to `/opt/pharmacore/` together with the compose and nginx files, as a base64 tarball inside the SSM command:
  1. Pull every `/pharmacore/prod/*` parameter into `/opt/pharmacore/.env` with `aws ssm get-parameters-by-path --with-decryption` (file mode 600).
  2. ECR login.
  3. Set `IMAGE_TAG=$1`, then `docker compose -f docker-compose.prod.yml pull && up -d`.
  4. Wait until `curl -fsS localhost:8000/` succeeds.
  5. `docker image prune -f` to keep the small disk clear.
- **[deploy/user-data.sh](../deploy/user-data.sh):** for Amazon Linux 2023. Installs docker and the compose plugin, enables docker, creates a **2 GB swapfile** (PDF rendering is memory-heavy), and creates `/opt/pharmacore`. The app files arrive with each deploy through `ship.sh`, so S3 and the instance never share files.
- **[deploy/ship.sh](../deploy/ship.sh):** runs on the GitHub Actions runner. It waits until the SSM agent is online, sends the files and the deploy command, and reports the result.
- **[deploy/cloudfront/spa-rewrite.js](../deploy/cloudfront/spa-rewrite.js):** the CloudFront Function that rewrites deep links.
- **[docs/aws-console-setup.md](aws-console-setup.md):** the one-time AWS setup below, click by click in the AWS console.
- **[docs/aws-setup.md](aws-setup.md):** the same setup as copy-paste AWS CLI commands.

## One-time AWS setup (one region, used everywhere)
1. **Billing:** create Budgets at $20, $50 and $100 with email alerts. Check Billing → Credits weekly.
2. **Network:** use the default VPC. Create these security groups:
   - `sg-ec2`: inbound 80 from the prefix list `com.amazonaws.global.cloudfront.origin-facing`; no SSH.
   - `sg-rds`: inbound 5432 from `sg-ec2`.
3. **RDS:** PostgreSQL 16 on db.t4g.micro, single-AZ, 20 GB gp2, autoscaling off, not public, DB name `pharmacore`, 1-day backups, Performance Insights off.
4. **SSM parameters** under `/pharmacore/prod/`:
   - SecureString: `DATABASE_URL=postgresql+asyncpg://pharmacore:<pw>@<rds-endpoint>:5432/pharmacore?ssl=require` (RDS for PostgreSQL 16 requires SSL), `BOOTSTRAP_ADMIN_PASSWORD`.
   - Plain: `ENVIRONMENT=production`, `ENABLE_DOCS=false`, `COOKIE_SECURE=true`, `SEED_DEMO_DATA=false` (set it to `true` for a study demo database), `DB_POOL_SIZE=5`, `BOOTSTRAP_ADMIN_EMAIL`, and so on.
5. **ECR:** create the repo `pharmacore-api` with a lifecycle rule that keeps the last 3 images.
6. **EC2:**
   - Role `pharmacore-ec2`: `AmazonSSMManagedInstanceCore`, `AmazonEC2ContainerRegistryReadOnly`, `ssm:GetParametersByPath` on `/pharmacore/prod/*`, and `kms:Decrypt` through SSM.
   - Instance: t3.micro, Amazon Linux 2023, 10 GB gp3, auto-assign public IP, `sg-ec2`, the role above, and `user-data.sh`.
7. **S3 and CloudFront:**
   - A private bucket with Block Public Access on.
   - A distribution with an S3 origin (OAC, plus the bucket policy CloudFront generates) and an HTTP-only custom origin `ec2-api` (EC2 public DNS, port 80).
   - Behaviors: `/api/*` uses CachingDisabled, AllViewerExceptHostHeader, all methods, Redirect HTTP→HTTPS. Default `/*` uses CachingOptimized plus a CloudFront Function `spa-rewrite` that sends extensionless paths to `/index.html`.
   - No distribution-wide error pages, so API JSON 404s stay intact.
8. **Auto-stop:** EventBridge Scheduler with two daily schedules, for example 23:30 local time. They use the universal targets `ec2:stopInstances` and `rds:stopDBInstance`, through a role scoped to those two resources.
9. **GitHub OIDC:**
   - Add the IAM identity provider `token.actions.githubusercontent.com` with audience `sts.amazonaws.com`.
   - Role `pharmacore-gha` trusts the `main` branch of this repo. GitHub's token now identifies it as `repo:<owner>@<owner-id>/<repo>@<repo-id>:ref:refs/heads/main`, so the trust policy allows that and the older `repo:<owner>/<repo>:ref:refs/heads/main` format.
   - Permissions:
     - S3 put, delete and list on the bucket.
     - `cloudfront:CreateInvalidation`, `GetDistribution`, `GetDistributionConfig` and `UpdateDistribution` on the distribution.
     - `ecr:GetAuthorizationToken`, plus ECR push and pull on the repo.
     - `ec2:DescribeInstances`, `DescribeInstanceStatus`, `StartInstances` and `StopInstances`.
     - `rds:DescribeDBInstances`, `StartDBInstance` and `StopDBInstance`.
     - `ssm:SendCommand` on the instance and the AWS-RunShellScript document, plus `ssm:GetCommandInvocation` and `ssm:DescribeInstanceInformation`.
10. **GitHub repo settings:**
    - **Secrets:** `AWS_ROLE_ARN`, `S3_BUCKET`, `CF_DISTRIBUTION_ID`, `EC2_INSTANCE_ID`. These identify the account and its resources, and secrets are masked in the public Actions logs.
    - **Variables:** `AWS_REGION`, `ECR_REPOSITORY`, `CF_API_ORIGIN_ID=ec2-api`, `RDS_INSTANCE_ID`.
    - The workflows also set `mask-aws-account-id: true` on `configure-aws-credentials`.

## Daily study flow
1. Actions → **lab-control → start**. After about 10–15 minutes the app URL appears in the job summary.
2. Push to `main`. **Frontend** runs if `frontend/` changed and updates S3 and CloudFront. **Backend** runs if `backend/` or `deploy/` changed: it tests, then updates the API container.
3. Actions → **lab-control → stop** when done. If you forget, the nightly schedule stops everything.
4. Before day 180, take a `pg_dump` (through SSM on EC2) and decide whether to upgrade to a paid plan or delete everything.

## Verification
- **Path filters work:** a pull request that changes only `frontend/` runs only Frontend's build job, and a pull request that changes `backend/` runs only Backend's test job. Neither runs a deploy job.
- **lab-control start:** the job finishes green, and the CloudFront origin shows the new EC2 DNS name.
- **The app works:**
  - `https://<dist>.cloudfront.net/` loads, and refreshing on a deep link works.
  - Login sets a Secure cookie with path `/api`.
  - An invoice PDF downloads.
  - An unknown `/api/x` returns a JSON 404.
- **The API is not reachable directly:** `curl http://<ec2-public-dns>/api/` from your PC times out.
- **Deploy updates the API:** push a commit; the Backend deploy job's SSM output shows the new SHA, and `docker ps` in Session Manager shows the new image.
- **Rate limiting works:** 11 fast bad logins return 429.
- **Stop works:** after lab-control stop, the EC2 console shows stopped and RDS shows stopped. The next day, Cost Explorer shows only storage charges.
