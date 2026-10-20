# AWS console setup for PharmaCore, step by step

This guide sets up the same AWS resources as [aws-setup.md](aws-setup.md), but in the **AWS web console** instead of with CLI commands. It's written for learning, so each step explains why it matters. Do the steps in order. It takes about an hour, most of it waiting for RDS and CloudFront.

AWS changes its console layout from time to time. If a button has moved, look for the **setting name** in **bold**. The settings themselves don't change.

---

## Before you start

### Pick one region
In the top-right corner of the console, choose a region, for example **Europe (Stockholm) eu-north-1**. Use the same region for every step.

IAM and CloudFront are *global* services. When you open them, the selector shows "Global"; that's normal.

### Keep a values worksheet
Copy this table into a notes file and fill it in as you go. You'll need these values in later steps and in GitHub.

| Value | Where you get it | Your value |
|---|---|---|
| Region | Top-right selector | `eu-north-1` |
| Account ID | Click your name at the top right; it's the 12-digit number | |
| DB password | Step 3 (you generate it) | |
| RDS endpoint | Step 3 | |
| EC2 instance ID | Step 6 (`i-...`) | |
| EC2 public DNS | Step 6 (`ec2-...compute.amazonaws.com`) | |
| S3 bucket name | Step 7 | |
| CloudFront distribution ID | Step 7 (`E...`) | |
| CloudFront domain | Step 7 (`d....cloudfront.net`) | |
| GitHub deploy role ARN | Step 9 | |

### Generate two passwords
Open **Git Bash** and run these two commands. They generate a password for the database and a temporary one for the admin user:
```bash
openssl rand -hex 24
openssl rand -hex 12
```
The first is the **DB password** and the second is the **admin password**. They contain only `0-9a-f`, so they never need escaping in a URL or `.env` file.

---

## Step 1: Budget alerts (5 min)

This is your safety net. It emails you if spending goes above normal.

1. Search the top bar for **Billing and Cost Management** and open it. Choose **Budgets**, then **Create budget**.
2. Choose **Customize (advanced)**, then **Cost budget**. Click **Next**.
3. Fill in the budget:
   - **Budget name:** `pharmacore-monthly`
   - **Period:** Monthly
   - **Budget renewal type:** Recurring
   - **Budgeting method:** Fixed
   - **Budgeted amount:** `15`
4. Open **Advanced options** and **untick Credits**. This step matters: your credits pay the whole bill, so a budget that counts them would see about $0 and never alert you.
5. Click **Next** and add three alert thresholds, all sent to your email:
   - **Actual**, **50%** ($7.50)
   - **Actual**, **100%** ($15)
   - **Forecasted**, **100%**
6. Click **Next**, then **Create budget**.

Also bookmark **Billing and Cost Management → Credits** and check your remaining credits weekly.

---

## Step 2: Security groups (5 min)

Security groups are firewalls. You need two:
- **pharmacore-ec2:** lets only CloudFront reach the server on port 80.
- **pharmacore-rds:** lets only the server reach the database on port 5432.

1. Open **EC2**. In the left menu, under **Network & Security**, choose **Security Groups**, then **Create security group**.
2. Create the first group:
   - **Name:** `pharmacore-ec2`
   - **Description:** `PharmaCore API - CloudFront only`
   - **VPC:** the default VPC, which has `(default)` in its name
   - **Inbound rules → Add rule:**
     - **Type:** HTTP (port 80)
     - **Source:** Custom. Type `cloudfront` in the box and pick **com.amazonaws.global.cloudfront.origin-facing** (its ID starts with `pl-`).
   - **Outbound rules:** leave the default (all traffic allowed). The server needs it to download Docker images.
   - Click **Create security group**.
3. Click **Create security group** again for the second group:
   - **Name:** `pharmacore-rds`
   - **Description:** `PharmaCore DB - from API only`
   - **VPC:** the default VPC
   - **Inbound rules → Add rule:**
     - **Type:** PostgreSQL (port 5432)
     - **Source:** Custom. Type `pharmacore-ec2` and pick that security group.
   - Click **Create security group**.

Don't add an SSH (port 22) rule. You'll get a shell through Session Manager instead, which needs no open port.

---

## Step 3: RDS PostgreSQL database (15 min, mostly waiting)

1. Open **Aurora and RDS**. Choose **Databases**, then **Create database**.
2. **Choose a database creation method:** **Full configuration**. Older consoles call it "Standard create".
   - Don't choose Express configuration ("Easy create"). It hides the initial database name and storage autoscaling settings.
   - Don't choose the S3 option either. It restores a database from a backup file.
3. **Engine options:**
   - **Engine type:** PostgreSQL
   - **Engine version:** the newest **PostgreSQL 16.x**
4. **Templates:** **Free tier** if it's offered, otherwise **Dev/Test**.
5. **Availability and durability:** **Single-AZ DB instance deployment (1 instance)**. Multi-AZ doubles the cost.
6. **Settings:**
   - **DB instance identifier:** `pharmacore-db`
   - **Master username:** `pharmacore`
   - **Credentials management:** **Self managed**. ⚠️ Don't choose "Managed in AWS Secrets Manager": it costs $0.40/month, and the app needs the password in its connection URL anyway.
   - **Master password:** paste your **DB password**, then confirm it.
7. **Instance configuration:**
   - **Burstable classes**
   - **db.t4g.micro**
8. **Storage:**
   - **Storage type:** General Purpose SSD (gp2)
   - **Allocated storage:** `20` GiB
   - **Additional storage configuration:** **untick Enable storage autoscaling**
9. **Connectivity:**
   - **Compute resource:** Don't connect to an EC2 compute resource
   - **VPC:** the default VPC
   - **DB subnet group:** default
   - **Public access:** **No**
   - **VPC security group:** Choose existing. **Remove `default`** and add **`pharmacore-rds`**.
   - **Database port:** 5432
10. **Database authentication:** Password authentication.
11. **Monitoring:**
    - Leave **Database Insights - Standard** as it is (free).
    - **Untick Enhanced Monitoring.**
12. **Additional configuration**, which is collapsed by default, so open it:
    - **Initial database name:** `pharmacore`. ⚠️ Don't skip this. Without it, RDS doesn't create the database the app expects.
    - **Backup retention period:** 1 day
    - Leave encryption on (free).
    - **Deletion protection:** optional. If you turn it on, you'll have to turn it off before you can delete the database at the end.
13. Click **Create database**. If a pop-up offers add-ons, close it.
14. Wait until **Status** shows **Available** (about 10 minutes).
15. Click **pharmacore-db**. On the **Connectivity & security** tab, copy the **Endpoint**, for example `pharmacore-db.abc123xyz.eu-north-1.rds.amazonaws.com`, into your worksheet.

---

## Step 4: App settings in Parameter Store (10 min)

These parameters become the app's `.env` file on the server. `deploy.sh` reads everything under `/pharmacore/prod/`.

1. Open **Systems Manager**. In the left menu, under **Application Tools**, choose **Parameter Store**, then **Create parameter**.
2. Create the database URL first, because it's secret:
   - **Name:** `/pharmacore/prod/DATABASE_URL`
   - **Tier:** Standard (free)
   - **Type:** **SecureString**
   - **KMS key source:** My current account, key **alias/aws/ssm** (the default)
   - **Value:** fill in your DB password and RDS endpoint:
     ```
     postgresql+asyncpg://pharmacore:<DB password>@<RDS endpoint>:5432/pharmacore?ssl=require
     ```
   - Click **Create parameter**.
3. Repeat **Create parameter** for each row below. Every name starts with `/pharmacore/prod/`.

| Name | Type | Value |
|---|---|---|
| `BOOTSTRAP_ADMIN_PASSWORD` | **SecureString** | your **admin password** |
| `BOOTSTRAP_ADMIN_EMAIL` | String | your email, which becomes the first admin login |
| `BOOTSTRAP_ADMIN_NAME` | String | `System Administrator` |
| `ENVIRONMENT` | String | `production` |
| `ENABLE_DOCS` | String | `false` |
| `COOKIE_SECURE` | String | `true` |
| `DB_POOL_SIZE` | String | `5` |
| `SEED_DEMO_DATA` | String | `true` (loads sample data, useful for study) |
| `ALLOW_DEMO_RESET` | String | `false` |
| `ALLOW_SELF_REGISTRATION` | String | `true` |

**Check:** the Parameter Store list shows **11 parameters** under `/pharmacore/prod/`.

---

## Step 5: ECR image repository (3 min)

ECR stores the API's Docker images. The Backend workflow pushes them here, and EC2 pulls them.

1. Open **Elastic Container Registry**. Under **Private registry**, choose **Repositories**, then **Create repository**.
2. Fill in:
   - **Repository name:** `pharmacore-api`
   - **Image tag mutability:** **Mutable**. The workflow overwrites the `:latest` tag on every push, which needs this.
   - Click **Create**.
3. Open **pharmacore-api**. In the left menu, under **Repository**, choose **Lifecycle policy**, then **Create rule**:
   - **Rule priority:** `1`
   - **Description:** `keep last 3`
   - **Image status:** Any
   - **Match criteria:** Image count more than `3`
   - Click **Save**.

The lifecycle rule deletes older images automatically, so storage stays a few cents a month.

---

## Step 6: EC2 server (15 min)

### 6a. Create the server's IAM role
This role lets the server use Session Manager, pull from ECR and read its own settings. It never needs stored keys.

1. Open **IAM**. Choose **Roles**, then **Create role**.
2. **Trusted entity type:** AWS service. **Use case:** **EC2**. Click **Next**.
3. Search for and tick both of these, then click **Next**:
   - **AmazonSSMManagedInstanceCore**
   - **AmazonEC2ContainerRegistryReadOnly**
4. **Role name:** `pharmacore-ec2`. Click **Create role**.
5. Open the **pharmacore-ec2** role. Choose **Add permissions → Create inline policy**, then switch to the **JSON** tab.
6. Paste this policy. Replace `REGION` and `ACCOUNT_ID` with your values; there are three places:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": "ssm:GetParametersByPath",
         "Resource": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/pharmacore/prod*" },
       { "Effect": "Allow", "Action": "kms:Decrypt", "Resource": "*",
         "Condition": { "StringEquals": { "kms:ViaService": "ssm.REGION.amazonaws.com" } } }
     ]
   }
   ```
7. Click **Next**. **Policy name:** `app-params`. Click **Create policy**.

### 6b. Launch the server
1. Open **EC2**. Choose **Instances**, then **Launch instances**.
2. **Name:** `pharmacore-api`
3. **Application and OS Images:**
   - **Amazon Linux**
   - **Amazon Linux 2023 AMI**
   - **Architecture:** **64-bit (x86)**. This must be x86, because the workflow builds amd64 images.
4. **Instance type:** **t3.micro**
5. **Key pair:** **Proceed without a key pair**. You'll use Session Manager instead.
6. **Network settings:** click **Edit**, then set:
   - **VPC:** the default VPC
   - **Subnet:** No preference
   - **Auto-assign public IP:** **Enable**
   - **Firewall (security groups):** **Select existing security group**, then **pharmacore-ec2**
7. **Configure storage:** `10` GiB, **gp3**
8. **Advanced details:** expand it, then set:
   - **IAM instance profile:** **pharmacore-ec2**
   - **Credit specification:** **Standard**. ⚠️ The default "Unlimited" bills extra if the CPU stays busy.
   - **Metadata version:** V2 only (token required)
   - **User data:** open [deploy/user-data.sh](../deploy/user-data.sh) in VS Code, copy **all of it**, and paste it here. It installs Docker and adds 2 GB of swap on first boot.
9. Click **Launch instance**, then **View all instances**.
10. Wait until **Instance state** shows **Running** and **Status check** shows **3/3 checks passed** (some regions show 2/2). This takes about 3 minutes.
11. Click the instance and copy two values into your worksheet:
    - **Instance ID** (`i-...`)
    - **Public IPv4 DNS** (`ec2-13-...compute.amazonaws.com`)

### 6c. Check the server
1. Select the instance, then choose **Connect → Session Manager → Connect**. If it says the instance isn't connected, wait 2 minutes and refresh. If it still can't connect, check that the IAM role from 6a is attached: **Actions → Security → Modify IAM role**.
2. In the browser terminal, run:
   ```bash
   sudo docker --version
   sudo docker compose version
   free -h
   ```
   You should see a Docker version, a Compose version, and about **2.0Gi** on the `Swap:` line. If Docker isn't found yet, the first-boot script is still running; wait a minute and try again.
3. Click **Terminate session**. That ends the browser session only; the server keeps running.

---

## Step 7: S3 and CloudFront (20 min, mostly waiting)

### 7a. S3 bucket for the frontend
1. Open **S3** and choose **Create bucket**.
2. Fill in:
   - **Bucket type:** General purpose
   - **Bucket name:** `pharmacore-web-<your account ID>`. Bucket names must be globally unique, and the account ID makes yours unique.
   - **Region:** your region
   - **Block all public access:** leave **ticked**. Only CloudFront will read the bucket.
3. Click **Create bucket**. Leave it empty; the Frontend workflow uploads the files.

### 7b. CloudFront Function for page refreshes
This makes refreshing a page like `/billing` work. Without it, S3 returns an error for those paths.

1. Open **CloudFront**. In the left menu, choose **Functions**, then **Create function**.
2. **Name:** `pharmacore-spa-rewrite`. **Runtime:** **cloudfront-js-2.0**. Click **Create function**.
3. On the **Build** tab, delete the sample code and paste the contents of [deploy/cloudfront/spa-rewrite.js](../deploy/cloudfront/spa-rewrite.js). Click **Save changes**.
4. Open the **Publish** tab and click **Publish function**.

### 7c. CloudFront distribution (the wizard as of late 2026)

The wizard creates only the S3 part. You add the EC2 origin, the `/api/*` rule and the function afterwards, in 7d–7f.

**About pricing plans:** CloudFront now offers flat-rate plans (Free, Pro and higher) as well as pay-as-you-go.
- Accounts on the **AWS Free Tier / Free plan aren't eligible for flat-rate plans**, so you'll probably see **no plan choice** and get **pay-as-you-go**. That's fine: it includes 1 TB of transfer and 10 million requests a month free, and anything beyond that comes out of your credits.
- If you **do** see a plan choice:
  - pick **pay-as-you-go** if it's offered;
  - otherwise pick **Free**, but never **Pro** or higher, which cost $15+/month.
- On the **Free** plan, a WAF web ACL is attached automatically at no charge.
- The Free plan may not allow the `CachingDisabled` cache policy you set in 7e. If 7e refuses it, tell me and we'll switch the distribution to pay-as-you-go.

1. Open **CloudFront**, choose **Distributions**, then **Create distribution**.
2. **Page 1, name and type:**
   - **Distribution name:** `pharmacore`
   - Choose **Single website or app**, not Multi-tenant.
   - Click **Next**.
3. **Page 2, domain setup:**
   - Leave **Route 53 managed domain** empty. You'll use the free `*.cloudfront.net` address with HTTPS.
   - Click **Next**.
4. **Page 3, Specify origin:**
   - **Origin type:** **Amazon S3**
   - **Origin:** click **Browse S3** and pick your `pharmacore-web-...` bucket in **eu-north-1**.
   - **Origin path:** leave empty.
   - **Allow private S3 bucket access to CloudFront:** make sure it's **selected** (recommended). This creates the OAC and lets CloudFront update the bucket policy for you.
   - **Settings:** **Use recommended origin settings**. For S3 that means HTTPS redirect, GET/HEAD only, caching on and compression on, which is exactly what you want.
   - Click **Next**.
5. **Page 4, Enable security protections:**
   - On pay-as-you-go, choose ⚠️ **Do not enable security protections**. WAF costs $5+/month there.
   - On the Free plan, WAF is included and can't be turned off; leave it as offered.
   - Click **Next**.
6. **Page 5, Review:** check that it shows **Amazon S3** with **CloudFront access granted**, then click **Create distribution**.
7. **Bucket policy:** newer consoles update it automatically. If you see a banner saying **"The S3 bucket policy needs to be updated"**, do this:
   - Click **Copy policy**, then the bucket link.
   - In S3, open **Permissions → Bucket policy → Edit**, paste the policy, and click **Save changes**.

   Either way, check that **S3 → your bucket → Permissions → Bucket policy** now has a statement allowing `cloudfront.amazonaws.com` to `s3:GetObject`.
8. **Settings the wizard skips.** On the distribution's **General** tab, find **Settings** and click **Edit**:
   - **Default root object:** `index.html`
   - **Price class:** **Use North America, Europe, Asia, Middle East, and Africa**, if this field is shown. It's hidden on flat-rate plans.
   - **Standard logging:** Off
   - Click **Save changes**.

If the wizard shows **"Your account must be verified before you can add new CloudFront resources"**, your account is new and CloudFront is locked. Open a free **Account and billing** support case with that message and wait for AWS to unlock it, usually within 2 days. Steps 8 and 9 don't need CloudFront, so you can do them meanwhile. In the support case, say it's a personal study project with very low traffic. If the first reply doesn't fix it, reply on the same case and ask them to escalate it to the team that handles CloudFront account verification.

### 7d. Add the API origin (EC2)
1. In the distribution, open the **Origins** tab and click **Create origin**.
2. Fill in:
   - **Origin domain:** paste the **EC2 public IPv4 DNS** from step 6. Ignore any dropdown suggestions.
   - **Protocol:** **HTTP only**
   - **HTTP port:** 80
   - **Name:** **`ec2-api`**. ⚠️ Use exactly this. The Lab control workflow finds the origin by this name.
   - **Response timeout:** 60 seconds
3. Click **Create origin**.

### 7e. Send /api/* to EC2
1. Open the **Behaviors** tab and click **Create behavior**.
2. Fill in:
   - **Path pattern:** `/api/*`
   - **Origin and origin groups:** **ec2-api**
   - **Viewer protocol policy:** Redirect HTTP to HTTPS
   - **Allowed HTTP methods:** **GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE**
   - **Cache policy:** **CachingDisabled**. The API must never be cached.
   - **Origin request policy:** **AllViewerExceptHostHeader**. This forwards cookies, headers and query strings to the API.
3. Click **Create behavior**.

### 7f. Attach the page-refresh function to the S3 behavior
1. Still on **Behaviors**, select the **Default (\*)** row and click **Edit**.
2. Scroll to **Function associations**. For **Viewer request**, set:
   - **Function type:** CloudFront Functions
   - **Function:** **pharmacore-spa-rewrite**
3. Click **Save changes**.

Don't add anything under the **Error pages** tab. A custom error page would replace your API's JSON errors with the website's HTML.

### 7g. Record the IDs
On the distribution's **General** tab, copy the **Distribution ID** (`E...`) and the **Distribution domain name** (`d....cloudfront.net`) into your worksheet. Wait until **Last modified** shows a date instead of **Deploying** (about 5–10 minutes).

### 7h. Security headers
Locally, nginx adds security headers to every page ([frontend/nginx/security-headers.conf](../frontend/nginx/security-headers.conf)). On AWS, S3 serves the pages, so CloudFront has to add them instead. They apply to the browser → CloudFront leg, which is already HTTPS.

1. Go to **CloudFront → Policies → Response headers** and click **Create response headers policy**. Name it `pharmacore-security-headers`.
2. Under **Security headers**, set each of these and tick **Origin override** on each:
   - **Strict-Transport-Security:** max-age `31536000`. Leave includeSubDomains and Preload unticked.
   - **Content-Type-Options:** ticked (`nosniff`).
   - **Frame-Options:** `DENY`.
   - **Referrer-Policy:** `no-referrer`.
   - **Content-Security-Policy:** use the same value as nginx:
     ```
     default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data: blob: https:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
     ```
   - Leave **XSS-Protection** unticked.
3. Under **Custom headers**, add `Permissions-Policy` = `camera=(), microphone=(), geolocation=()` with **Origin override** ticked. Click **Create**.
4. In **Distribution → Behaviors**, edit **Default (\*)** and set **Response headers policy** to `pharmacore-security-headers`, then **Save changes**. Do the same for **`/api/*`**.
5. **Check it:** open the site, then **DevTools → Network**, and select the page request. **Response Headers** should list the headers above. Use the app and watch the **Console** for Content Security Policy errors.
6. **To undo:** set **Response headers policy** back to **None**.

---

## Step 8: Nightly auto-stop (10 min)

This stops EC2 and RDS every night in case you forget. It also handles RDS restarting itself after 7 days stopped.

### 8a. Role for the scheduler
1. Open **IAM**. Choose **Roles**, then **Create role**.
2. **Trusted entity type:** **Custom trust policy**. Paste:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{ "Effect": "Allow",
       "Principal": { "Service": "scheduler.amazonaws.com" },
       "Action": "sts:AssumeRole" }]
   }
   ```
3. Click **Next**, then **Next** again (skip managed permissions). **Role name:** `pharmacore-scheduler`. Click **Create role**.
4. Open the role. Choose **Add permissions → Create inline policy → JSON**, and paste this with your values filled in:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": "ec2:StopInstances",
         "Resource": "arn:aws:ec2:REGION:ACCOUNT_ID:instance/INSTANCE_ID" },
       { "Effect": "Allow", "Action": "rds:StopDBInstance",
         "Resource": "arn:aws:rds:REGION:ACCOUNT_ID:db:pharmacore-db" }
     ]
   }
   ```
5. **Policy name:** `stop-lab`. Click **Create policy**.

### 8b. Schedule to stop EC2
1. Open **Amazon EventBridge**. In the left menu, under **Scheduler**, choose **Schedules**, then **Create schedule**.
2. **Schedule name:** `pharmacore-stop-ec2`.
3. **Schedule pattern:** **Recurring schedule**, **Cron-based schedule**:
   - minutes `30`, hours `23`, day of month `*`, month `*`, day of the week `?`, year `*`
   - **Time zone:** yours, for example **Asia/Kolkata**
   - **Flexible time window:** **Off**
4. Click **Next**.
5. **Target:** **All APIs**. Search for **Amazon EC2** and choose **StopInstances**. Set the input to:
   ```json
   { "InstanceIds": ["i-your-instance-id"] }
   ```
6. Click **Next**.
7. **Settings:**
   - **Retry policy:** off
   - **Execution role:** **Use existing role**, then **pharmacore-scheduler**
8. Click **Next**, then **Create schedule**.

### 8c. Schedule to stop RDS
Repeat 8b with these changes:
- **Name:** `pharmacore-stop-rds`
- **Target:** **Amazon RDS**, then **StopDBInstance**
- **Input:**
  ```json
  { "DbInstanceIdentifier": "pharmacore-db" }
  ```

If the database is already stopped, the RDS schedule logs a harmless error that night.

---

## Step 9: Let GitHub Actions log in to AWS (10 min)

This uses OIDC: GitHub proves its identity to AWS, so you never store AWS keys in GitHub.

### 9a. Identity provider (once per AWS account)
1. Open **IAM**. Choose **Identity providers**, then **Add provider**.
2. Fill in:
   - **Provider type:** **OpenID Connect**
   - **Provider URL:** `https://token.actions.githubusercontent.com`
   - **Audience:** `sts.amazonaws.com`
3. Click **Add provider**.

### 9b. Deploy role
1. In IAM, choose **Roles**, then **Create role**.
2. **Trusted entity type:** **Web identity**. Fill in:
   - **Identity provider:** token.actions.githubusercontent.com
   - **Audience:** sts.amazonaws.com
   - **GitHub organization:** `Sreerajraveendran`
   - **GitHub repository:** `Pharma`
   - **GitHub branch:** `main`
3. Click **Next**, then **Next** again (skip managed permissions). **Role name:** `pharmacore-gha`. Click **Create role**.
4. **Fix the trust policy.** ⚠️ Don't skip this.
   - **Why:** GitHub now puts the owner's and repo's permanent numeric IDs in the token it sends, e.g. `repo:Sreerajraveendran@186459430/Pharma@1409210444:ref:refs/heads/main`. The wizard writes the old format without the IDs, so AWS refuses with *"Not authorized to perform sts:AssumeRoleWithWebIdentity"*.
   - **Find your two IDs:** open `https://api.github.com/repos/Sreerajraveendran/Pharma` in a browser. The top-level `"id"` is the **repo ID**; `"owner" → "id"` is the **owner ID**.
   - **Edit the policy:** open **Trust relationships → Edit trust policy** and replace everything with the policy below. Put in your account ID and both GitHub IDs. Listing both formats keeps it working if GitHub ever sends the old one.
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": { "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com" },
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": {
         "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
         "StringLike": { "token.actions.githubusercontent.com:sub": [
           "repo:Sreerajraveendran@OWNER_ID/Pharma@REPO_ID:ref:refs/heads/main",
           "repo:Sreerajraveendran/Pharma:ref:refs/heads/main"
         ] }
       }
     }]
   }
   ```
   - Click **Update policy**.
   - This is what stops anyone else's repo or fork from using the role: only `main` of this exact repo matches.
5. Open the **Permissions** tab and choose **Add permissions → Create inline policy → JSON**. Paste this policy. Replace `REGION`, `ACCOUNT_ID`, `BUCKET`, `DIST_ID` and `INSTANCE_ID` everywhere they appear:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": "s3:ListBucket", "Resource": "arn:aws:s3:::BUCKET" },
       { "Effect": "Allow", "Action": ["s3:PutObject", "s3:DeleteObject"], "Resource": "arn:aws:s3:::BUCKET/*" },
       { "Effect": "Allow",
         "Action": ["cloudfront:CreateInvalidation", "cloudfront:GetDistribution",
                    "cloudfront:GetDistributionConfig", "cloudfront:UpdateDistribution"],
         "Resource": "arn:aws:cloudfront::ACCOUNT_ID:distribution/DIST_ID" },
       { "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
       { "Effect": "Allow",
         "Action": ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
                    "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"],
         "Resource": "arn:aws:ecr:REGION:ACCOUNT_ID:repository/pharmacore-api" },
       { "Effect": "Allow", "Action": ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"], "Resource": "*" },
       { "Effect": "Allow", "Action": ["ec2:StartInstances", "ec2:StopInstances"],
         "Resource": "arn:aws:ec2:REGION:ACCOUNT_ID:instance/INSTANCE_ID" },
       { "Effect": "Allow", "Action": ["rds:DescribeDBInstances", "rds:StartDBInstance", "rds:StopDBInstance"],
         "Resource": "arn:aws:rds:REGION:ACCOUNT_ID:db:pharmacore-db" },
       { "Effect": "Allow", "Action": "ssm:SendCommand",
         "Resource": ["arn:aws:ec2:REGION:ACCOUNT_ID:instance/INSTANCE_ID",
                      "arn:aws:ssm:REGION::document/AWS-RunShellScript"] },
       { "Effect": "Allow", "Action": ["ssm:GetCommandInvocation", "ssm:DescribeInstanceInformation"], "Resource": "*" }
     ]
   }
   ```
6. **Policy name:** `deploy`. Click **Create policy**.
7. On the role's **Summary**, copy the **ARN** (`arn:aws:iam::123456789012:role/pharmacore-gha`) into your worksheet.

---

## Step 10: GitHub settings (5 min)

In GitHub, open **Pharma → Settings → Secrets and variables → Actions**. The values go on two different tabs. Names must match exactly, including upper case.

**Secrets tab → New repository secret.** These four contain your account ID or resource IDs, and the repo is public. As secrets, they show as `***` in the public Actions logs:

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | the role ARN from step 9 |
| `S3_BUCKET` | `pharmacore-web-<account ID>` |
| `CF_DISTRIBUTION_ID` | `E...` from step 7 |
| `EC2_INSTANCE_ID` | `i-...` from step 6 |

**Variables tab → New repository variable.** These are generic names, so they stay readable:

| Name | Value |
|---|---|
| `AWS_REGION` | your region, for example `eu-north-1` |
| `ECR_REPOSITORY` | `pharmacore-api` |
| `CF_API_ORIGIN_ID` | `ec2-api` |
| `RDS_INSTANCE_ID` | `pharmacore-db` |

The workflows read secrets with `${{ secrets.NAME }}` and variables with `${{ vars.NAME }}`. A value saved on the wrong tab arrives empty, and the job fails. They also set `mask-aws-account-id: true`, so the account ID is hidden in places like ECR image addresses too.

Then go to **Settings → Actions → General** and set **Fork pull request workflows** to **Require approval for all external contributors**.

---

## First deploy

1. Push the code to `main`.
2. In GitHub, open **Actions**. Choose **Frontend → Run workflow**, then **Backend → Run workflow**.
3. Wait for both to show green ✅. The Backend deploy log should end with `API is up`.
4. Open `https://<your CloudFront domain>/` and log in with your **admin email** and **admin password**. The app will ask you to set a new password.
5. When you finish, run **Actions → Lab control → stop**.

From then on, the daily routine is **Lab control → start**, study and push, then **Lab control → stop**.

## If something fails

| Symptom | Likely cause | Fix |
|---|---|---|
| Workflow fails at **Configure AWS credentials** | Trust policy or `AWS_ROLE_ARN` is wrong | Step 9b, point 4: the repo and branch must match exactly, and are case-sensitive |
| Backend fails with **SSM agent is not online** | The EC2 role is missing | Step 6c, point 1: attach `pharmacore-ec2` |
| Backend log shows **DATABASE_URL is missing** | Parameter name or role policy is wrong | Step 4: the name must be exactly `/pharmacore/prod/DATABASE_URL`. Step 6a: the region and account in the policy |
| Backend log shows a database connection timeout | The RDS security group is wrong | Step 3, point 9: RDS must use `pharmacore-rds`, and step 2 must allow `pharmacore-ec2` |
| The site works, but `/api/...` returns **502** or **504** | The CloudFront origin is wrong, or EC2 is stopped | Step 7d: use the EC2 public DNS with HTTP only on port 80. Run Lab control → start |
| Refreshing `/billing` shows **AccessDenied** | The function isn't attached | Step 7f |
| The home page shows **AccessDenied** | The bucket policy is missing, or nothing has been uploaded yet | Step 7c, point 8, and run the Frontend workflow |

---

## Step 11 (after the first deploy): Monitoring with CloudWatch (45 min, about $0.75/month)

So far, the only way to notice a problem is to open the site. This step adds four things:
- **email alerts** through SNS;
- **alarms** for the server, the database and the site;
- **central logs**, so the API's and nginx's logs are kept in AWS rather than only on the server.

Do the parts in order. In particular, 11d must be finished before 11e turns the logs on.

| Part | Region | Cost/month |
|---|---|---|
| 11a SNS topic (eu-north-1) | eu-north-1 | $0 |
| 11b Alarms for EC2 and RDS (6) | eu-north-1 | $0.60 |
| 11c SNS topic + CloudFront alarm (1) | **us-east-1** | $0.10 |
| 11d–11e Central logs | eu-north-1 | ~$0.02 |
| Dashboard | skipped: it may cost $3/month; the Alarms page and the Monitoring tabs show the same graphs | $0 |

### 11a. Where alerts go: an SNS topic
1. Switch the region to **eu-north-1**. Open **Simple Notification Service (SNS) → Topics → Create topic**.
2. **Type:** Standard. **Name:** `pharmacore-alerts`. Click **Create topic**.
3. On the topic, click **Create subscription**:
   - **Protocol:** Email
   - **Endpoint:** your email address
   - Click **Create subscription**.
4. Open the email from AWS and click **Confirm subscription**. Until you do, the subscription shows **Pending confirmation** and no alert reaches you.

### 11b. Alarms for EC2 and RDS (eu-north-1)
For each row in the table, do this:
1. Go to **CloudWatch → Alarms → All alarms → Create alarm → Select metric**.
2. Find the metric: choose the namespace, then search for the instance or DB ID.
3. Tick the metric, then click **Select metric**.
4. Set **Statistic** and **Period** as in the table.
5. **Conditions:** Static, and the threshold from the table.
6. Open **Additional configuration**:
   - **Datapoints to alarm:** as in the table, e.g. `2` out of `2`.
   - **Missing data treatment:** ⚠️ **Treat missing data as good (not breaching threshold)**. The lab is stopped most of the time, and this stops the alarms complaining about it.
7. Click **Next**. **Notification:** **In alarm**, then send to **pharmacore-alerts**. Click **Next**.
8. **Alarm name:** the name from the table. Click **Next**, then **Create alarm**.

| Alarm name | Namespace → metric | Statistic / Period | Condition | Datapoints |
|---|---|---|---|---|
| `pharmacore-ec2-status-check` | EC2 → Per-Instance Metrics → `StatusCheckFailed` | Maximum / 1 minute | ≥ `1` | 2 out of 2 |
| `pharmacore-ec2-cpu-high` | EC2 → Per-Instance Metrics → `CPUUtilization` | Average / 5 minutes | > `80` | 3 out of 3 |
| `pharmacore-ec2-cpu-credits-low` | EC2 → Per-Instance Metrics → `CPUCreditBalance` | Minimum / 5 minutes | < `20` | 1 out of 1 |
| `pharmacore-rds-cpu-high` | RDS → Per-Database Metrics → `CPUUtilization` (pharmacore-db) | Average / 5 minutes | > `80` | 3 out of 3 |
| `pharmacore-rds-storage-low` | RDS → Per-Database Metrics → `FreeStorageSpace` | Minimum / 5 minutes | < `2000000000` (2 GB, in bytes) | 1 out of 1 |
| `pharmacore-rds-memory-low` | RDS → Per-Database Metrics → `FreeableMemory` | Minimum / 5 minutes | < `100000000` (100 MB, in bytes) | 3 out of 3 |

**If you only want two alarms ($0.20/month),** make `pharmacore-ec2-status-check` and `pharmacore-rds-storage-low`.

### 11c. Site error alarm for CloudFront (us-east-1)
CloudFront's metrics only exist in **US East (N. Virginia) us-east-1**. An alarm can only notify an SNS topic in its own region, so this one needs its own topic.
1. Switch the region to **us-east-1** and repeat **11a** there: create the topic `pharmacore-alerts-global`, subscribe your email, and confirm it.
2. Go to **CloudWatch → Alarms → Create alarm → Select metric → CloudFront → Per-Distribution Metrics**. Pick `5xxErrorRate` for your distribution ID, with Region **Global**.
3. Set:
   - **Statistic:** Average. **Period:** 5 minutes.
   - **Condition:** > `5` (percent).
   - **Datapoints:** 2 out of 2.
   - **Missing data:** treat as good.
4. **Notification:** **pharmacore-alerts-global**. **Name:** `pharmacore-cloudfront-5xx`. Create it.
5. Switch the region back to **eu-north-1**.

### 11d. Prepare central logs (do this before 11e)
**Create two log groups.**
1. Go to **CloudWatch → Logs → Log groups → Create log group**.
2. Create the first group:
   - **Name:** `/pharmacore/api`
   - **Retention setting:** ⚠️ **1 week**. The default, "Never expire", keeps every log forever.
   - **Log class:** Standard
   - Click **Create**.
3. Create a second group, **`/pharmacore/proxy`**, with the same settings.

**Let the server write to them.**
4. Go to **IAM → Roles → pharmacore-ec2 → Add permissions → Create inline policy → JSON** and paste this, with your account ID in place of `ACCOUNT_ID`:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow",
         "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": "arn:aws:logs:eu-north-1:ACCOUNT_ID:log-group:/pharmacore/*:*" }
     ]
   }
   ```
5. Click **Next**. **Policy name:** `cloudwatch-logs`. Click **Create policy**.
6. Check it was **saved**: the role's **Permissions** tab should now list `app-params` **and** `cloudwatch-logs`.

### 11e. Turn central logs on
The deploy script switches Docker's logs to CloudWatch only when this setting is `true`. If it's on before 11d is done, the containers refuse to start.

1. Go to **Systems Manager → Parameter Store → Create parameter**:
   - **Name:** `/pharmacore/prod/CLOUDWATCH_LOGS`
   - **Type:** String
   - **Value:** `true`
2. Run **Lab control → start**. If the lab is already running, run **Backend → Run workflow** instead. The deploy log should show:
   ```
   Logging to CloudWatch Logs (/pharmacore/api, /pharmacore/proxy)
   API is up: ...
   ```
3. Use the site for a minute: log in and open a few pages.
4. Go to **CloudWatch → Log groups → /pharmacore/api** and open the newest **log stream**. The API's log lines are there.

**To turn it off:** set the parameter to `false` and deploy again. The logs then go back to local files on the server.

### 11f. Searching logs (Logs Insights)
Go to **CloudWatch → Logs → Logs Insights**, select `/pharmacore/api` (or both groups), and run a query.

Last 50 errors:
```
fields @timestamp, @message
| filter @message like /ERROR|Traceback| 500 /
| sort @timestamp desc
| limit 50
```

Requests that got a 401 or 429 at the proxy (in `/pharmacore/proxy`):
```
fields @timestamp, @message
| filter @message like / 401 | 429 /
| sort @timestamp desc
| limit 50
```

Queries cost $0.005 per GB scanned, so a few cents at most for study use.

### 11g. Check the alarms
1. Go to **CloudWatch → Alarms**. With the lab stopped, every alarm should show **OK**, thanks to "missing data = good".
2. **Test that email works:** select `pharmacore-ec2-cpu-high` and choose **Actions → Edit**. Temporarily change the threshold to `> 0`, run **Lab control → start**, and within about 15 minutes you should get an email. Then set the threshold back to `80`.

### Costs to avoid
- **Dashboards:** may cost $3/month each.
- **EC2 detailed monitoring:** about $2+/month.
- **CloudFront additional metrics:** about $1+/month.
- **Synthetics canaries:** about $10/month.
- **Log retention "Never expire".**
