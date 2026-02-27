# Phase 10 — Security, Monitoring & Go-live

## Goal

Harden security (WAF rules, RBAC audit), set up CloudWatch alarms, run load testing (≤5 concurrent users), complete UAT with the client, and execute go-live checklist.

## Prerequisites

- [ ] All Phases 1–9 complete and verified
- [ ] All **User Inputs (UI-01 to UI-11)** resolved
- [ ] Handler master table fully mapped (Phase 9)
- [ ] Client UAT sign-off obtained

---

## 10.1 Security Hardening

### WAF Rules (CloudFront)

| Rule Group | Purpose |
| --- | --- |
| AWS-AWSManagedRulesCommonRuleSet | OWASP Top 10 protection |
| AWS-AWSManagedRulesSQLiRuleSet | SQL injection protection |
| AWS-AWSManagedRulesKnownBadInputsRuleSet | Known attack patterns |
| Custom: Rate limit | Max 500 requests/5 min per IP |
| Custom: LINE webhook IP allowlist | Only LINE platform IPs allowed on `/webhook/line` |

### Steps

1. Enable WAF Web ACL in CDK and attach to CloudFront distribution
2. Add rate limiting rule (protect against scraping/abuse)
3. Fetch LINE IP ranges and add to IP allowlist rule for webhook endpoint
4. Enable WAF logging to S3 for review

### RBAC Audit

Run through every API endpoint and verify:

| Check | Method |
| --- | --- |
| Every endpoint has `get_current_user` dependency | Code review |
| Role checks use `require_role()` not custom `if` statements | Code review |
| Officers cannot see other provinces' cases | Integration test |
| Executive cannot mutate any data | Integration test |
| Unauthenticated request on all endpoints → 401 | Automated test run |

### HTTPS Enforcement

- [ ] HTTP → HTTPS redirect on ALB listener (port 80 → 301 redirect)
- [ ] HSTS header via CloudFront response headers policy
- [ ] TLS minimum version: TLS 1.2 on CloudFront

### Pre-signed URL Security

- [ ] Verify pre-signed URLs expire after 1 hour (attachments)
- [ ] Verify pre-signed URLs expire after 1 hour (exports)
- [ ] Verify S3 bucket policy blocks direct public access

---

## 10.2 CloudWatch Monitoring & Alarms

### Key Alarms

| Alarm | Threshold | Action |
| --- | --- | --- |
| EC2 CPU > 80% for 5 min | 80% | SNS → email alert |
| Aurora CPU > 70% for 5 min | 70% | SNS → email alert |
| Aurora connections > 80% of max | 80% | SNS alert |
| ALB 5xx error rate > 1% | 1% | SNS alert |
| SQS `notification-dlq` depth > 0 | 1 message | SNS alert |
| SQS `export-dlq` depth > 0 | 1 message | SNS alert |
| SQS `line-webhook-dlq` depth > 0 | 1 message | SNS alert |
| Airflow DAG failure | CloudWatch Log filter | SNS alert |
| Lambda error rate > 0 | Any error | SNS alert |

### Dashboard

Create a CloudWatch dashboard:
- EC2 CPU, memory (via CloudWatch agent)
- Aurora read/write IOPS, connection count
- ALB request count, 4xx/5xx rates, latency P99
- SQS queue depths for all 3 queues

### Steps

1. Install CloudWatch agent on EC2 for memory + disk metrics
2. Create CloudWatch dashboard in CDK
3. Create SNS topic `one-system-alerts` with admin email subscription
4. Create all alarms attached to SNS topic
5. Create Log Metric Filters for Airflow DAG failure patterns

---

## 10.3 Application Logging

### FastAPI Structured Logging

```python
import logging, json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "extra": getattr(record, "extra", {}),
        })
```

Log every request with: method, path, status_code, duration_ms, user_id (from JWT).

### CloudWatch Log Groups

| Service | Log Group |
| --- | --- |
| FastAPI app | `/one-system/app` |
| Airflow | `/one-system/airflow` |
| Lambda notification worker | `/aws/lambda/notification-worker` |
| Lambda export worker | `/aws/lambda/export-worker` |
| WAF | `/aws/waf/one-system` |

### Log Retention

Set all log groups to 90-day retention (cost control).

---

## 10.4 Load Testing

Target: ≤5 concurrent users (scope §17). Verify the system is stable at this load.

### Tool: `locust`

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class ImsUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        self.token = login(self.client)

    @task(3)
    def list_cases(self):
        self.client.get("/api/v1/cases", headers=auth(self.token))

    @task(2)
    def get_case_detail(self):
        self.client.get("/api/v1/cases/RRD-2568-000001", headers=auth(self.token))

    @task(1)
    def get_dashboard(self):
        self.client.get("/api/v1/dashboard/summary", headers=auth(self.token))
```

### Load Test Scenarios

| Scenario | Users | Duration | Pass Criteria |
| --- | --- | --- | --- |
| Normal load | 3 | 5 min | P99 < 2s, 0 errors |
| Peak load | 5 | 5 min | P99 < 3s, < 0.1% error rate |
| Sustained peak | 5 | 30 min | No memory leak, stable response time |

### Steps

1. Run load tests against staging environment (separate stack)
2. Monitor CloudWatch during test
3. If P99 > 3s: tune Aurora ACU max, EC2 instance type, or add query caching
4. Document results in test report

---

## 10.5 Data Migration (Historical Cases)

Import historical cases from `data_sample.xlsx` into production Aurora before go-live.

### Steps

1. Create `scripts/migrate_historical.py`:
   - Read `data/data_sample.xlsx` using `openpyxl`
   - Parse LINE sheet + CALL_1146 sheet
   - Apply same ETL transformations as Phase 5
   - Bulk insert into `cases` table using `ON CONFLICT DO NOTHING`
2. Run dry-run first: count rows, check nullability violations
3. Run migration in a transaction; rollback if any insert fails
4. Verify: `SELECT COUNT(*) FROM cases` matches expected row count
5. Generate case IDs for historical cases (use BE year from `reported_at`, not current year)

---

## 10.6 User Acceptance Testing (UAT)

Conduct UAT with client stakeholders covering all roles.

### UAT Scenarios

| Role | Scenario | Expected Result |
| --- | --- | --- |
| Dispatcher | Log in, view WAITING_VERIFY queue, assign case to officer | Case moves to IN_PROGRESS |
| Dispatcher | Mark case as duplicate (provide original case ID) | Status = DUPLICATE |
| Officer | Log in, view assigned cases only | Only own province visible |
| Officer | Update status to PENDING with expected fix date | Status = PENDING, date saved |
| Officer | Upload photo attachment | Image visible in case gallery |
| Executive | View dashboard for current month | All KPIs correct |
| Executive | Export Excel | File downloads with 2 sheets, Thai text correct |
| Admin | Create new OFFICER user | User receives email, can log in |
| Admin | Map handler to user account | ETL assigns officer correctly |
| Admin | Change SLA threshold | Effective next ETL run |
| Admin | Reopen DONE case | Status returns to WAITING_VERIFY |
| Admin | Close Tier-4 case with reason | Appears separately in dashboard |

### UAT Sign-off Checklist

- [ ] All scenarios passed by client
- [ ] Thai language correct throughout (labels, dates, messages)
- [ ] Buddhist Era dates display correctly
- [ ] No broken pages or 500 errors during testing
- [ ] Notification emails received
- [ ] LINE messages received (for assigned cases from LINE source)

---

## 10.7 Go-live Checklist

### Pre-go-live (1 week before)

- [ ] All Phase 1–9 deliverables complete
- [ ] Historical data migration complete and verified
- [ ] All 14 handlers mapped to user accounts
- [ ] At least 1 Admin, 1 Dispatcher, 1 Officer, 1 Executive user created in Cognito
- [ ] SES out of sandbox (production access requested and approved)
- [ ] LINE webhook URL registered in LINE Developers Console
- [ ] 1146 API connection tested in production environment
- [ ] CloudWatch alarms live and SNS email subscription confirmed
- [ ] SSL certificate valid (check expiry date)
- [ ] Load test passed

### Go-live Day

- [ ] Announce maintenance window (if any)
- [ ] Run `alembic upgrade head` on production DB
- [ ] Run seed scripts (if any new reference data)
- [ ] Deploy latest backend image
- [ ] Deploy latest frontend build to S3 + CloudFront invalidation
- [ ] Verify ALB health check passing
- [ ] Verify `GET /health` returns 200
- [ ] Trigger Airflow DAGs manually to confirm connectivity to LINE + 1146
- [ ] Create first live case via UI
- [ ] Confirm notification received by assigned officer

### Post-go-live (first week)

- [ ] Monitor CloudWatch dashboard daily
- [ ] Check DLQ depths daily
- [ ] Verify Airflow DAGs running on schedule
- [ ] Collect first-week user feedback
- [ ] Fix any critical bugs within 1 business day

---

## Testing Plan Summary (Phase 10)

| Test | Tool | Pass Criteria |
| --- | --- | --- |
| OWASP Top 10 scan | OWASP ZAP (passive scan) | No HIGH/CRITICAL findings |
| SQL injection | WAF test + app test | WAF blocks, no DB error leaks |
| Unauthenticated access (all endpoints) | `pytest` auth tests | 100% return 401 |
| RBAC: every role × every endpoint | `pytest` RBAC matrix | Correct 200/403 per role |
| Load test: 5 users | `locust` | P99 < 3s, < 0.1% error |
| Historical data migration | Row count check | 0 import errors |
| SSL certificate | `curl -v` + browser | TLS 1.2+, valid cert |
| HTTPS redirect | `curl http://DOMAIN` | 301 to HTTPS |

### Deliverables

- [ ] WAF rules active and tested
- [ ] CloudWatch alarms live
- [ ] Load test report complete (P99, error rate)
- [ ] Historical data migrated to production
- [ ] UAT sign-off from client
- [ ] Go-live executed successfully
- [ ] All post-go-live checks green
