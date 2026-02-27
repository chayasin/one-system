# Rural Roads One System — Implementation Tracker

## ⚠️ User Inputs Required Before Starting

These must be provided before implementation can proceed. Work through them before Phase 1.

| # | Item | Description | Needed For |
|---|---|---|---|
| UI-01 | AWS Account & Region | AWS account ID, default region (e.g. `ap-southeast-1`) | Phase 1 |
| UI-02 | AWS IAM credentials | Access key + secret (or AWS SSO profile) for infrastructure provisioning | Phase 1 |
| UI-03 | Domain Name | Production domain for ALB + CloudFront (e.g. `one-system.rrd.go.th`) | Phase 1 |
| UI-04 | LINE Channel Access Token | Long-lived token for LINE Messaging API (for webhook + sending notifications) | Phase 5, 6 |
| UI-05 | LINE Channel Secret | Used to verify webhook signature from LINE platform | Phase 5 |
| UI-06 | LINE OA Channel ID | LINE OA channel ID | Phase 5 |
| UI-07 | 1146 API Endpoint URL | Base URL of the 1146 call center REST API | Phase 5 |
| UI-08 | 1146 API Credentials | API key / username+password for 1146 REST endpoint | Phase 5 |
| UI-09 | SES Sender Email | Verified email address in AWS SES for outbound notifications | Phase 6 |
| UI-10 | Airflow Preference | Self-hosted on EC2 vs AWS MWAA (managed) | Phase 5 |
| UI-11 | SSL Certificate ARN | ACM certificate ARN for the domain (or confirm we create it) | Phase 1 |

---

## Implementation Phases

| Phase | Name | Status | Detail |
|---|---|---|---|
| 1 | Infrastructure & Foundation | ☐ Not started | [phases/phase_1.md](phases/phase_1.md) |
| 2 | Backend API Core | ☐ Not started | [phases/phase_2.md](phases/phase_2.md) |
| 3 | IMS Case Management APIs | ☐ Not started | [phases/phase_3.md](phases/phase_3.md) |
| 4 | IMS Frontend — Case Management | ☐ Not started | [phases/phase_4.md](phases/phase_4.md) |
| 5 | Data Pipeline (ETL) | ☐ Not started | [phases/phase_5.md](phases/phase_5.md) |
| 6 | Notification System | ☐ Not started | [phases/phase_6.md](phases/phase_6.md) |
| 7 | Executive Dashboard | ☐ Not started | [phases/phase_7.md](phases/phase_7.md) |
| 8 | Export Functionality | ☐ Not started | [phases/phase_8.md](phases/phase_8.md) |
| 9 | Admin Features | ☐ Not started | [phases/phase_9.md](phases/phase_9.md) |
| 10 | Security, Monitoring & Go-live | ☐ Not started | [phases/phase_10.md](phases/phase_10.md) |

---

## Status Key

- `☐ Not started`
- `🔄 In progress`
- `✅ Done`
- `🚧 Blocked`

---

## Tech Stack Decisions

| Layer | Technology | Rationale |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Async, auto OpenAPI docs, clean for Thai-language payloads |
| Frontend | React 18 + TypeScript + Vite | Modern, fast builds, strong ecosystem |
| Database | Aurora Serverless v2 (PostgreSQL 15) | Scales to zero, cost-efficient |
| IaC | AWS CDK (Python) | Infrastructure as code, same language as backend |
| Pipeline | Apache Airflow (EC2 self-hosted) | Unless user prefers MWAA |
| Auth | AWS Cognito User Pool | Managed, integrates with ALB |
| File Storage | Amazon S3 | Pre-signed URLs, lifecycle policies |
| Queue | Amazon SQS | LINE webhook buffer + notification queue |
| Notifications | Lambda + SES + LINE Messaging API | Async, decoupled |
| Export | Celery worker on EC2 | Async job queue for heavy exports |
| Monitoring | CloudWatch + Alarm | Native AWS, minimal ops overhead |
