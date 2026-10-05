### Phase 1: Local Repository Setup

* [ ] **Create Directory Layout:** Set up the folders matching the project structure:
```text
├── .github/workflows/deploy.yml
├── bootstrap/main.tf
├── infra/ (main.tf, variables.tf, outputs.tf)
├── src/ (index.py, requirements.txt)
└── .gitignore

```


* [ ] **Add `.gitignore`:** Copy the `.gitignore` file to the root directory to avoid committing `.tfstate`, `.terraform/`, and local virtual environments.
* [ ] **Place Scraper Code (`src/index.py`):** Ensure your scraper implementation is wrapped inside a `lambda_handler(event, context)` function that:
* Reads `SCRAPER_USERNAME` and `SCRAPER_PASSWORD` from `os.environ`.
* Connects to DynamoDB using `os.environ['TABLE_NAME']`.
* Compares the output with the previous report using `difflib.unified_diff`.
* Writes the updated report back to DynamoDB when a diff is detected.
* Publishes the diff message to `os.environ['SNS_TOPIC_ARN']`.


* [ ] **Define Python Dependencies (`src/requirements.txt`):** List all required packages with pinned versions (e.g., `requests==2.32.3`, `beautifulsoup4==4.12.3`).

---

### Phase 2: One-Time AWS Bootstrap (Local Terminal)

* [ ] **Configure AWS CLI Credentials:** Ensure your local terminal has administrative AWS credentials set up (`aws configure`).
* [ ] **Initialize and Apply Bootstrap:**
```bash
cd bootstrap
tofu init
tofu apply -var="github_repo=<github-user-or-org>/<repo-name>"

```


* [ ] **Record Outputs:** Copy the two terminal outputs:
* `role_arn` (IAM Role ARN for GitHub Actions)
* `state_bucket_name` (S3 Bucket name for OpenTofu state storage)



---

### Phase 3: Configuration & Secrets

* [ ] **Configure Remote State in `infra/main.tf`:** Paste the `state_bucket_name` into the `backend "s3"` block:
```hcl
backend "s3" {
  bucket = "tofu-state-<your-repo-name>-xxxx"
  key    = "pipeline/terraform.tfstate"
  region = "us-east-1"
}

```


* [ ] **Add GitHub Actions Secrets:** In GitHub (`Settings > Secrets and variables > Actions > New repository secret`), create:
* `AWS_ROLE_ARN`: Value of `role_arn` from Phase 2.
* `NOTIFICATION_EMAIL`: Email address where alerts should be sent.
* `SCRAPER_USERNAME`: Your scraper portal login.
* `SCRAPER_PASSWORD`: Your scraper portal password.



---

### Phase 4: Deployment & Verification

* [ ] **Commit and Push:** Push your repository to GitHub's `main` branch to trigger `.github/workflows/deploy.yml`:
```bash
git add .
git commit -m "Initial pipeline setup"
git push origin main

```


* [ ] **Confirm SNS Subscription (Mandatory):** Open the inbox of the email provided in `NOTIFICATION_EMAIL`, locate the message from `AWS Notifications`, and click **Confirm subscription**.
* [ ] **Run Manual Smoke Test:** Trigger the Lambda function directly once to verify permissions, DynamoDB writes, and dependency imports:
```bash
aws lambda invoke \
  --function-name json-change-monitor-reporter \
  response.json && cat response.json

```


*(Run 1 should return `initial_run_recorded`; Run 2 should return `unchanged`).*

---

### Phase 5: Scraper Hardening Checks

* [ ] **Strip Non-Deterministic Fields:** Check that dynamic tokens, timestamps, nonces, and session IDs are excluded from the scraped dictionary before comparison to prevent false-positive alert emails.
* [ ] **Set Network Timeouts:** Ensure all HTTP calls inside `src/index.py` specify explicit timeouts (e.g., `requests.get(url, timeout=(5, 15))`) so the Lambda does not hang until execution timeout.
* [ ] **Verify User-Agent:** Include standard browser request headers in the scraper to avoid bot blocking on AWS IP ranges.
