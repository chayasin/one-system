# Phase 5 — Data Pipeline (ETL)

## Goal

Implement the full data ingestion pipeline: LINE OA webhook receiver → SQS, and 1146 REST pull → Airflow DAGs → S3 Landing Zone → Transform → Aurora. Overdue tier computation runs on the same cadence.

## Prerequisites

- [ ] **UI-04** LINE Channel Access Token
- [ ] **UI-05** LINE Channel Secret
- [ ] **UI-06** LINE OA Channel ID
- [ ] **UI-07** 1146 API Endpoint URL
- [ ] **UI-08** 1146 API Credentials
- [ ] **UI-10** Airflow preference (self-hosted EC2 or MWAA)
- [ ] Phase 1 complete (S3, SQS, Aurora provisioned)
- [ ] Phase 3 complete (case API + case_id generation working)

---

## 5.1 Pipeline Architecture

```
LINE OA  ──webhook──► [Webhook Endpoint (FastAPI /webhook/line)]
                              │
                              ▼
                        [SQS: line-webhook-queue]
                              │
                         (Airflow drain DAG, hourly)
                              │
1146 API ──REST pull──────────┤
                              │
                              ▼
                   [S3: s3-raw-landing/]
                   {source}/YYYY/MM/DD/HH/{uuid}.json
                              │
                   [Airflow: ETL Transform DAG]
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
          [S3: s3-processed-zone/]  [Aurora: cases + case_history]
                                         │
                              [Aurora: summary_cases_daily]
```

---

## 5.2 LINE OA Webhook Endpoint

A dedicated FastAPI route (or separate Lambda — same EC2 is simplest) that:
1. Validates LINE signature
2. Writes raw event JSON to SQS immediately
3. Returns HTTP 200 within 1 second

### Endpoint

```
POST /webhook/line
Headers: X-Line-Signature: <base64-HMAC-SHA256>
```

### Signature Validation

```python
import hmac, hashlib, base64

def verify_line_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    digest = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)
```

### Steps

1. Add `POST /webhook/line` route in FastAPI (no auth — public endpoint, only LINE can call it)
2. Validate `X-Line-Signature` header; reject with 400 if invalid
3. Send raw body to SQS `line-webhook-queue` with `MessageGroupId = channel_id`
4. Return `{"status": "ok"}` immediately
5. Store `LINE_CHANNEL_SECRET` in Secrets Manager
6. **Security**: add IP allowlist (LINE IPs only) at WAF or Nginx level

---

## 5.3 Field Mapping Configuration (YAML)

Per-source YAML-based mapping files avoid hardcoding field names.

```yaml
# pipeline/config/mapping_line_v1.yaml
source: LINE
version: line_v1
fields:
  source_seq_no:       ลำดับ
  status_raw:          สถานะ
  date_raw:            วันที่
  time_raw:            เวลาแจ้ง
  received_time_raw:   เวลารับแจ้ง
  closed_time_raw:     เวลาปิดเรื่อง
  handler_name:        ผู้รับเรื่อง
  reporter_name:       ชื่อผู้ติดต่อ
  line_user_id:        ID Line
  service_type_raw:    เรื่องที่ขอรับบริการ
  complaint_type_raw:  เรื่องร้องเรียน
  description:         รายละเอียด
  province:            จังหวัด
  district_office:     แขวงทางหลวงชนบท
  road_number:         หมายเลขถนน
  notes:               หมายเหตุ
time_format: "HH.MM น."
null_values: ["ไม่ระบุ", ""]
```

```yaml
# pipeline/config/mapping_call_v1.yaml
source: CALL_1146
version: call_v1
fields:
  source_seq_no:       ลำดับ
  status_raw:          สถานะ
  date_raw:            วันที่
  time_raw:            เวลา
  reporter_name:       ชื่อผู้ติดต่อ
  contact_number:      หมายเลขที่ติดต่อเข้ามา
  service_type_raw:    เรื่องที่ขอรับบริการ
  complaint_type_raw:  เรื่องร้องเรียน
  description:         รายละเอียด
  province:            จังหวัด
  district_office:     แขวงทางหลวงชนบท
  road_number:         หมายเลขถนน
  notes:               หมายเหตุ
time_format: "HH:MM:SS"
null_values: [""]
```

---

## 5.4 ETL Transform Logic

Core transformation functions, implemented in `pipeline/etl/transform.py`.

### Status Mapping (Thai → IMS)

```python
STATUS_MAP = {
    "อยู่ระหว่างดำเนินการ": "IN_PROGRESS",
    "ตามเรื่อง":             "FOLLOWING_UP",
    "เรื่องซ้ำ":             "DUPLICATE",
    "ปิดเรื่อง":             "DONE",
}
```

### Service Type Normalization

```python
def parse_service_type(raw: str) -> str:
    # "6.ร้องเรียน" → "6"
    return raw.split(".")[0].strip()
```

### Complaint Type Normalization

```python
COMPLAINT_TYPE_ALIAS = {
    "ป้ายจราจรชำรุด/สูญหาย/ติดตั้ง/ย้าย": "CT03",
    "ป้ายจราจร ชำรุด/สูญหาย/ติดตั้ง/ย้าย": "CT03",
    # ... all variants from data_sample.xlsx
}
```

### Time Parsing

```python
from datetime import datetime, date, time

def parse_line_time(date_str: str, time_str: str) -> datetime:
    # date_str: "14/02/68" (BE short year)
    # time_str: "09.30 น."
    be_year_short = int(date_str.split("/")[2])
    ce_year = be_year_short + 2500
    d = date(ce_year, ...)
    t_clean = time_str.replace(" น.", "").replace(".", ":")
    return datetime.combine(d, time.fromisoformat(t_clean))

def parse_call_time(date_str: str, time_str: str) -> datetime:
    # time_str: "09:30:00" (HH:MM:SS Python time object from pickle)
    ...
```

### Null Normalization

```python
def normalize_null(value: str | None, null_values: list[str]) -> str | None:
    if value is None or value.strip() in null_values:
        return None
    return value.strip()
```

### Handler Resolution

```python
async def resolve_handler(handler_name: str | None, db) -> UUID | None:
    if not handler_name:
        return None
    result = await db.execute(
        select(RefHandler.user_id).where(RefHandler.display_name == handler_name)
    )
    return result.scalar_one_or_none()  # None if not mapped yet
```

### Idempotency Check

```python
# Deduplicate on (source_channel, source_seq_no, reported_at)
INSERT INTO cases (...) VALUES (...)
ON CONFLICT (source_channel, source_seq_no, reported_at) DO NOTHING
```

---

## 5.5 Airflow DAG: LINE Webhook Drain

**DAG ID:** `line_webhook_drain`
**Schedule:** `@hourly` (or `*/5 * * * *` — configurable)

```
[SQS Receive Messages]
       ↓
[Write to S3 Landing: s3-raw-landing/LINE/YYYY/MM/DD/HH/]
       ↓
[Transform → canonical format]
       ↓
[Write to S3 Processed: s3-processed-zone/LINE/YYYY/MM/DD/HH/]
       ↓
[Upsert to Aurora: cases table]
       ↓
[Delete SQS messages]
       ↓
[Update summary_cases_daily]
```

### Tasks

1. `drain_sqs`: receive up to 10 msgs at a time, loop until queue empty
2. `save_to_landing`: write each raw JSON to S3 under structured path
3. `transform_and_upsert`: apply YAML mapping, normalize, upsert to cases
4. `refresh_summary`: `REFRESH MATERIALIZED VIEW` or INSERT/UPDATE `summary_cases_daily`

---

## 5.6 Airflow DAG: 1146 REST Pull

**DAG ID:** `call_1146_pull`
**Schedule:** `@hourly`

```
[Read last watermark from Airflow Variable or DB]
       ↓
[GET 1146 API: ?since=<watermark>]
       ↓
[Write raw JSON to S3 Landing: s3-raw-landing/CALL_1146/...]
       ↓
[Transform → canonical format]
       ↓
[Write to S3 Processed]
       ↓
[Upsert to Aurora]
       ↓
[Update watermark]
       ↓
[Update summary_cases_daily]
```

### Steps

1. Store watermark in Airflow Variable: `call_1146_last_watermark`
2. On first run: watermark = 30 days ago (backfill)
3. Handle paginated API response if 1146 API uses pagination
4. Store API credentials in Airflow Connections (`aws_secrets_manager` backend)

---

## 5.7 Airflow DAG: Overdue Tier Recalculation

**DAG ID:** `overdue_tier_refresh`
**Schedule:** same cadence as ETL (hourly)

```sql
-- Run after ETL completes
UPDATE cases c
SET overdue_tier = (
  CASE
    WHEN status IN ('DONE','CLOSE','CANCELLED','REJECTED','DUPLICATE') THEN NULL
    WHEN sla_started_at IS NULL THEN NULL
    WHEN EXTRACT(EPOCH FROM (NOW() - sla_started_at)) / 3600
         <= sc.temp_fix_hours THEN NULL
    ELSE (compute tier based on breach days vs overdue thresholds)
  END
)
FROM sla_config sc
WHERE sc.priority = c.priority;
```

### Steps

1. Create Python function that runs the UPDATE as a single DB statement
2. Chain as the final task in both `line_webhook_drain` and `call_1146_pull` DAGs (or as separate DAG with sensor)

---

## 5.8 Airflow DAG: Summary Table Refresh

**DAG ID:** `summary_refresh`
**Schedule:** `@hourly` (runs after ETL)

Inserts/updates `summary_cases_daily` by aggregating `cases` table:

```sql
INSERT INTO summary_cases_daily (
  summary_date, source_channel, province, district_office,
  service_type_code, complaint_type_code, priority, status,
  case_count, overdue_count, closed_within_sla, avg_close_hours
)
SELECT
  DATE(reported_at) as summary_date,
  source_channel, province, district_office,
  service_type_code, complaint_type_code, priority, status,
  COUNT(*),
  COUNT(*) FILTER (WHERE overdue_tier IS NOT NULL),
  COUNT(*) FILTER (WHERE closed_at IS NOT NULL AND ...),
  AVG(EXTRACT(EPOCH FROM (closed_at - sla_started_at))/3600)
FROM cases
WHERE DATE(reported_at) = CURRENT_DATE - INTERVAL '1 day'
GROUP BY 1,2,3,4,5,6,7,8
ON CONFLICT (...) DO UPDATE SET ...;
```

---

## 5.9 Airflow Setup

### Self-hosted on EC2 (if UI-10 = self-hosted)

1. Install Airflow 2.8+ via Docker Compose on a dedicated `t3.medium` EC2 instance
2. Use `LocalExecutor` with PostgreSQL metadata DB (separate from Aurora app DB — can use same Aurora cluster, different DB)
3. Configure `aws_secrets_manager` as Airflow secrets backend
4. Expose Airflow UI on private subnet only (admin VPN access)

### MWAA (if UI-10 = MWAA)

1. Create MWAA environment in CDK `infra/stacks/pipeline_stack.py`
2. Upload DAG files to MWAA S3 bucket
3. Set min/max workers to 1/2

---

## Testing Plan

### Unit Tests

| Test | What to verify |
| --- | --- |
| `parse_line_time()` | Correct datetime from "14/02/68" + "09.30 น." |
| `parse_call_time()` | Correct datetime from "14/02/2025" + "09:30:00" |
| `normalize_null("ไม่ระบุ", ...)` | Returns `None` |
| `normalize_null("สมชาย", ...)` | Returns `"สมชาย"` |
| `parse_service_type("6.ร้องเรียน")` | Returns `"6"` |
| Complaint type alias normalization | Minor variants → canonical CT code |
| LINE signature validation — valid | Returns `True` |
| LINE signature validation — tampered | Returns `False` |
| Idempotent upsert | Insert same record twice → 1 row in DB |
| Overdue tier: 4 days past Tier-1 threshold | Returns `1` |
| Overdue tier: 8 days past threshold | Returns `2` |

### Integration Tests (DAG-level)

| Test | Method | Pass Criteria |
| --- | --- | --- |
| Webhook → SQS → DB | POST mock LINE event → trigger drain DAG | Case row in `cases` with `source_channel=LINE` |
| 1146 pull | Trigger DAG with mock 1146 response | Case row in `cases` with `source_channel=CALL_1146` |
| Idempotent re-run | Run same DAG twice for same time window | No duplicate cases |
| Schema migration: handler unmapped | `handler_name` in source but no `ref_handler` match | `assigned_officer_id = NULL`, warning logged |
| Overdue tier recalc | Set `sla_started_at` to 4 days ago, run DAG | `overdue_tier = 1` in `cases` |
| Summary refresh | Run after ETL | `summary_cases_daily` row count > 0 |
| LINE signature rejection | POST with wrong signature | 400 returned, SQS not written |

### Deliverables

- [ ] LINE webhook validated, events landing in SQS and then Aurora
- [ ] 1146 pull DAG running hourly
- [ ] Overdue tier recalculated on each DAG run
- [ ] Summary table refreshed hourly
- [ ] All field transformations unit-tested
- [ ] Idempotency verified (no duplicates on re-run)
