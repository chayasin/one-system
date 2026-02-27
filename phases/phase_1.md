# Phase 1 — Infrastructure & Foundation

## Goal

Provision all AWS infrastructure required by the project, create the PostgreSQL schema, seed reference data, and verify connectivity. At the end of this phase, the database is live and accessible to the application tier.

## Prerequisites

- [ ] **UI-01** AWS Account ID and target region confirmed
- [ ] **UI-02** AWS IAM credentials configured locally (`aws configure` or SSO)
- [ ] **UI-03** Domain name confirmed
- [ ] **UI-11** ACM SSL certificate issued (or confirm auto-creation via CDK)

---

## 1.1 Repository & Project Structure

Set up the monorepo layout used by all subsequent phases.

```
one-system/
  infra/              ← AWS CDK (Python)
  backend/            ← FastAPI application
  frontend/           ← React + TypeScript
  pipeline/           ← Airflow DAGs + ETL scripts
  migrations/         ← Alembic database migrations
  phases/             ← this folder
  todo.md
  scope.md
```

### Steps

1. Initialize Python virtualenv at repo root for CDK: `python -m venv .venv`
2. Install CDK CLI: `npm install -g aws-cdk`
3. Bootstrap CDK in target account/region: `cdk bootstrap aws://ACCOUNT_ID/REGION`
4. Create `infra/` as a CDK Python app (`cdk init app --language python`)
5. Commit baseline project skeleton

---

## 1.2 Networking (VPC)

Create an isolated VPC for the application.

| Resource | Config |
| --- | --- |
| VPC CIDR | `10.0.0.0/16` |
| Public subnets | 2 AZs — for ALB and NAT Gateway |
| Private subnets | 2 AZs — for EC2 app servers, Aurora |
| NAT Gateway | 1 per AZ (or single NAT for cost) |
| Internet Gateway | Attached to VPC |

### Steps

1. Create `infra/stacks/network_stack.py` — VPC, subnets, IGW, NAT
2. Create security groups:
   - `sg-alb`: inbound 443 from 0.0.0.0/0
   - `sg-app`: inbound 8000 from `sg-alb` only
   - `sg-db`: inbound 5432 from `sg-app` only
   - `sg-pipeline`: inbound SSH (admin IP only), egress all

---

## 1.3 Aurora Serverless v2 (PostgreSQL 15)

| Setting | Value |
| --- | --- |
| Engine | Aurora PostgreSQL 15 |
| Mode | Serverless v2 |
| Min ACU | 0.5 |
| Max ACU | 4 |
| DB name | `one_system` |
| Subnet | Private subnets |
| Multi-AZ | Writer only (no DR this phase) |

### Steps

1. Create `infra/stacks/database_stack.py` — Aurora cluster, parameter group
2. Store DB credentials in AWS Secrets Manager (`/one-system/db/credentials`)
3. Enable automated backups (7-day retention)
4. Output cluster endpoint to CDK outputs

---

## 1.4 S3 Buckets

Create all S3 buckets with lifecycle policies.

| Bucket logical name | Purpose | Retention |
| --- | --- | --- |
| `s3-raw-landing` | LINE/1146 raw JSON | 3 years |
| `s3-processed-zone` | ETL processed output | 3 years |
| `s3-attachments` | Case image attachments | 3 years |
| `s3-exports` | CSV/Excel/PDF exports | 7 days (lifecycle expire) |
| `s3-audit-logs` | Immutable audit log | 3 years + Object Lock |

### Steps

1. Create `infra/stacks/storage_stack.py`
2. Configure S3 Object Lock (Compliance mode) on audit bucket
3. Block public access on all buckets
4. Add lifecycle rule: `s3-exports` objects expire after 7 days
5. Enable S3 server-side encryption (SSE-S3 or SSE-KMS) on all buckets

---

## 1.5 AWS Cognito User Pool

| Setting | Value |
| --- | --- |
| Pool name | `one-system-users` |
| Sign-in | Email |
| Password policy | Cognito defaults |
| MFA | Optional (admin decides) |
| App client | `one-system-web` (no client secret — SPA) |
| Token expiry | Access: 1h, Refresh: 30d |

### Steps

1. Create `infra/stacks/auth_stack.py` — Cognito User Pool + App Client
2. Create Cognito groups matching roles: `ADMIN`, `DISPATCHER`, `OFFICER`, `EXECUTIVE`
3. Disable self-registration (admin creates users only)
4. Output User Pool ID and App Client ID

---

## 1.6 SQS Queues

| Queue | Purpose | DLQ |
| --- | --- | --- |
| `line-webhook-queue` | Buffer LINE OA webhook events | `line-webhook-dlq` |
| `notification-queue` | Async in-app + email + LINE notifications | `notification-dlq` |
| `export-queue` | Async CSV/Excel/PDF export jobs | `export-dlq` |

### Steps

1. Add queues to `infra/stacks/messaging_stack.py`
2. Configure DLQs with max receive count = 3
3. Set visibility timeout: `line-webhook-queue` = 300s, `notification-queue` = 60s
4. Enable SSE on all queues

---

## 1.7 EC2 Application Server

| Setting | Value |
| --- | --- |
| Instance type | `t3.small` (scale up as needed) |
| AMI | Amazon Linux 2023 |
| Subnet | Private (behind ALB) |
| IAM role | Access S3, SQS, Secrets Manager, SES, Cognito |
| User data | Install Docker, Docker Compose |

### Steps

1. Create `infra/stacks/compute_stack.py` — EC2, IAM role, instance profile
2. IAM role permissions: `s3:*` on project buckets, `sqs:*` on project queues, `secretsmanager:GetSecretValue`, `ses:SendEmail`, `cognito-idp:AdminCreateUser`, `cognito-idp:AdminSetUserPassword`
3. Attach to private subnet, `sg-app` security group

---

## 1.8 Application Load Balancer + CloudFront

| Resource | Config |
| --- | --- |
| ALB | HTTPS:443 → EC2:8000, HTTP:80 redirect |
| CloudFront | Origin = ALB, HTTPS only, cache disabled for API |
| WAF | AWS managed rules attached to CloudFront |

### Steps

1. Create ALB in public subnets with `sg-alb`
2. Create target group → EC2 instance, health check `GET /health`
3. Add HTTPS listener (ACM cert from UI-11)
4. Create CloudFront distribution — two origins: ALB (for `/api/*`) and S3 (for frontend static files)
5. Attach WAF Web ACL with AWS managed rule groups

---

## 1.9 Database Schema Migrations

Apply the full schema from `scope.md §8`.

### Steps

1. Install Alembic in `migrations/`
2. Create `migrations/env.py` — connect to Aurora via Secrets Manager
3. Create initial migration with all tables from scope §8.1 and §8.2:
   - `users`
   - `cases`
   - `case_history`
   - `case_attachments`
   - `notifications`
   - `case_sequence`
   - `ref_service_type`
   - `ref_complaint_type`
   - `ref_handler`
   - `ref_closure_reason`
   - `sla_config`
   - `summary_cases_daily`
4. Create indexes:
   - `cases`: `(status)`, `(priority)`, `(reported_at)`, `(province)`, `(district_office)`, `(assigned_officer_id)`, `(overdue_tier)`, `(source_channel, source_seq_no, reported_at)` UNIQUE
   - `case_history`: `(case_id)`, `(changed_at)`
   - `notifications`: `(user_id, is_read)`
5. Run migration: `alembic upgrade head`

---

## 1.10 Seed Reference Data

Populate lookup tables before any testing.

### ref_service_type (12 rows from scope §7.3)

Insert codes 1–12 with Thai labels.

### ref_complaint_type (12 rows CT01–CT12)

Insert all complaint types.

### ref_closure_reason (5 rows from scope §5.3)

Insert closure reason codes with `requires_note = TRUE` for `OTHER`.

### sla_config (4 rows — one per priority)

| Priority | temp_fix_hours | permanent_fix_days |
| --- | --- | --- |
| CRITICAL | 12 | 7 |
| HIGH | 24 | 7 |
| MEDIUM | 72 | 7 |
| LOW | 168 | 7 |

### ref_handler (14 rows)

Pre-load the 14 handler display names observed in `data_sample.xlsx`. Leave `user_id = NULL` until Admin maps them (Phase 9).

### Steps

1. Create `migrations/seeds/` directory
2. Write seed SQL scripts for each reference table
3. Create a `seed.py` runner script
4. Run seeds and verify row counts

---

## Testing Plan

### Infrastructure Tests

| Test | Method | Pass Criteria |
| --- | --- | --- |
| VPC connectivity | EC2 → Aurora ping | Connection successful on port 5432 |
| Security group isolation | Attempt direct Aurora access from outside VPC | Connection refused |
| S3 bucket access | Upload/download test file from EC2 IAM role | Success |
| SQS send/receive | Send test message, receive and delete from queue | Message delivered |
| Cognito user creation | `aws cognito-idp admin-create-user` | User created, email received |
| ALB health check | `GET /health` returns 200 | Target in service |
| HTTPS redirect | `curl http://DOMAIN` | Redirects to HTTPS |
| WAF | OWASP test request (e.g., SQL injection in query param) | Request blocked (403) |

### Schema Tests

| Test | Method | Pass Criteria |
| --- | --- | --- |
| All tables created | `\dt` in psql | 12 tables present |
| Reference data seeded | `SELECT COUNT(*) FROM ref_service_type` | 12 rows |
| SLA config seeded | `SELECT COUNT(*) FROM sla_config` | 4 rows |
| Case sequence init | `SELECT * FROM case_sequence` | Empty (first insert test) |
| Index creation | `\di` in psql | All 8+ indexes present |
| Constraint: FK cases→users | Insert case with invalid officer_id | FK violation error |
| UNIQUE dedup index | Insert duplicate (channel, seq, timestamp) | Unique violation error |

### Deliverables

- [ ] CDK stacks deployable with `cdk deploy --all`
- [ ] All AWS resources provisioned and healthy
- [ ] Database schema applied via Alembic
- [ ] Reference data seeded and verified
- [ ] `cdk destroy` teardown tested (for dev environment cost management)
