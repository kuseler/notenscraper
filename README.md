# Notenscraper (DHBW Dualis Grade Monitor)

An automated, serverless pipeline that monitors DHBW Dualis for grade changes, calculates diffs against previous snapshots in DynamoDB, and sends email alerts via AWS SNS.

---

## Architecture Overview

```text
EventBridge Scheduler
       │ (Every 2h Mon-Fri)
       ▼
  AWS Lambda ──(Scrapes)──► DHBW Dualis Portal
       │
       ├── Reads/Writes ──► AWS DynamoDB (Grade snapshot storage)
       │
       └── On Diff ───────► AWS SNS Topic ──► Email Alert Subscriber
```

* **AWS Lambda (`src/index.py`)**: Executes the Dualis scraper session, normalizes data deterministically, compares with the last checkpoint in DynamoDB, and alerts on changes (capped at concurrency = 1 and 30s timeout).
* **AWS DynamoDB**: Stores the latest grades report (`id = "latest_report"`) for stateful diffing across invocations (fixed at 1 RCU / 1 WCU Always Free).
* **AWS SNS**: Delivers formatted unified diff alerts to your email.
* **EventBridge Scheduler**: Triggers the Lambda during business hours (`cron(0 9,11,13,15,17 ? * MON-FRI *)` in `Europe/Berlin`).
* **AWS Budgets ($0.01 Cap)**: Active monthly cost budget that immediately emails alerts if actual or forecasted spend exceeds $0.01.
* **OpenTofu & GitHub Actions**: Full Infrastructure-as-Code pipeline authenticated via keyless AWS OIDC.

---

## Free Tier & Zero-Spend Cost Protection

This architecture is strictly designed to remain **100% free forever** within AWS Always-Free allowances:

| Component | Architecture Setting | AWS Free Tier Allowance | Monthly Cost |
| :--- | :--- | :--- | :--- |
| **DynamoDB** | 1 RCU / 1 WCU Provisioned | 25 RCU / 25 WCU Always Free | **0.00 €** |
| **Lambda** | 128 MB, ~110 runs/mo, 1 max concurrency | 1,000,000 invocations + 3.2M sec/mo | **0.00 €** |
| **SNS** | Diff notification emails | 1,000 emails/mo Always Free | **0.00 €** |
| **EventBridge** | 5 invocations / weekday | 14,000,000 events/mo Always Free | **0.00 €** |
| **CloudWatch** | 14-day log retention | 5 GB ingestion / storage Always Free | **0.00 €** |
| **AWS Budgets** | $0.01 hard alert threshold | 2 Free Budgets per account | **0.00 €** |

---

## Prerequisites

* AWS Account with administrative access.
* GitHub repository (`kuseler/notenscraper`).
* Dualis credentials (username & password).
* OpenTofu (`>= 1.6`) or Terraform installed locally (for bootstrap).

---

## Setup & Deployment

### 1. One-Time AWS Bootstrap (IAM OIDC & State Bucket)

From the project root:

```bash
cd bootstrap
tofu init
tofu apply -var="github_repo=kuseler/notenscraper"
```

Outputs provided:
* `role_arn`: IAM Role ARN for GitHub Actions OIDC (`arn:aws:iam::<account-id>:role/github-actions-infra-deployer`).
* `state_bucket_name`: S3 bucket name created for OpenTofu remote state.

> [!NOTE]
> The bootstrap role trust policy supports GitHub's 2026 immutable subject claim format (`repo:<org>@<org_id>/<repo>@<repo_id>:*`).

---

### 2. Configure GitHub Actions Secrets & Variables

In your repository on GitHub (**Settings > Secrets and variables > Actions**):

#### Repository Variables (**Variables tab**)
| Name | Description | Example |
| :--- | :--- | :--- |
| `AWS_ROLE_ARN` | IAM Role ARN from bootstrap | `arn:aws:iam::521881990509:role/github-actions-infra-deployer` |
| `STATE_BUCKET_NAME` | S3 bucket name from bootstrap | `tofu-state-kuseler-notenscraper-xxxx` |
| `NOTIFICATION_EMAIL` | Email address for change alerts | `kimi-mueller@proton.me` |
| `SCRAPER_USERNAME` | Dualis login username | `s123456` |

#### Repository Secrets (**Secrets tab**)
| Name | Description |
| :--- | :--- |
| `SCRAPER_PASSWORD` | Dualis login password |

---

### 3. Deploy via GitHub Actions

Push any changes to the `main` branch:

```bash
git add .
git commit -m "Deploy pipeline"
git push origin main
```

The GitHub Actions workflow (`.github/workflows/deploy.yml`) will:
1. Authenticate with AWS via OIDC using `AWS_ROLE_ARN`.
2. Initialize OpenTofu using remote state bucket `STATE_BUCKET_NAME`.
3. Build the Python Lambda layer with dependencies (`requests`, `beautifulsoup4`).
4. Package and deploy Lambda, DynamoDB, SNS, CloudWatch Alarms, and EventBridge Schedule.

---

### 4. Confirm SNS Subscription

After the first deployment:
1. Open the inbox of the email configured in `NOTIFICATION_EMAIL`.
2. Open the confirmation email from **AWS Notifications**.
3. Click **Confirm subscription**.

---

### 5. Manual Smoke Test

You can manually trigger the Lambda function via AWS CLI to verify operation:

```bash
aws lambda invoke \
  --function-name json-change-monitor-reporter \
  --region eu-central-1 \
  response.json && cat response.json
```

* **Run 1:** Returns `"initial_run_recorded"` (snapshots initial grades in DynamoDB).
* **Run 2:** Returns `"unchanged"` (no new grades posted).
* **When grades change:** Returns `"diff_detected"` and sends an SNS alert email with the unified diff.

---

## Local Development & Testing

You can run the scraper locally without AWS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt

# Run directly (reads SCRAPER_USERNAME/SCRAPER_PASSWORD or USER/PASS from .env)
python3 src/index.py
```
