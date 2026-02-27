# Phase 3 — IMS Case Management APIs

## Goal

Implement the full case lifecycle API: create, read, search/filter, status transitions, assignment, attachments, and SLA calculation. At the end of this phase, all workflow rules from scope §3–5 are enforced server-side.

## Prerequisites

- [ ] Phase 2 complete (auth, RBAC, DB models working)
- [ ] Reference data seeded (service types, complaint types, SLA config)

---

## 3.1 Case Number Generation

Auto-generates `RRD-YYYY-NNNNNN` using Buddhist Era year, resetting to 1 each year.

### Logic

```python
async def generate_case_id(db: AsyncSession) -> str:
    be_year = datetime.utcnow().year + 543  # Convert CE to BE
    # Atomic increment using SELECT ... FOR UPDATE on case_sequence
    result = await db.execute(
        select(CaseSequence).where(CaseSequence.year == be_year).with_for_update()
    )
    seq_row = result.scalar_one_or_none()
    if seq_row is None:
        seq_row = CaseSequence(year=be_year, last_seq=1)
        db.add(seq_row)
    else:
        seq_row.last_seq += 1
    await db.flush()
    return f"RRD-{be_year}-{seq_row.last_seq:06d}"
```

### Steps

1. Implement `generate_case_id()` in `app/services/case_service.py`
2. Use `SELECT ... FOR UPDATE` inside a transaction to prevent race conditions
3. Unit test: concurrent generation produces no duplicates

---

## 3.2 Case CRUD Endpoints

### Endpoints

```
POST   /api/v1/cases                    ← create case (Dispatcher / Admin)
GET    /api/v1/cases                    ← list + search + filter (paginated)
GET    /api/v1/cases/{case_id}          ← get single case with history
PUT    /api/v1/cases/{case_id}          ← update editable fields
```

### Create Case Rules

- `source_channel` = `IMS_DIRECT` (for UI-created cases)
- `status` starts as `WAITING_VERIFY`
- `case_id` auto-generated
- `source_schema_version` = `ims_v1`
- `priority` defaults to `MEDIUM` if not provided
- If `service_type_code = 6`: require `province`, `district_office` — enforce server-side
- If `service_type_code ≠ 6`: set `province`, `district_office`, `road_number`, `complaint_type_code` = NULL

### Editable Fields by Role

| Field | DISPATCHER | OFFICER | ADMIN |
| --- | --- | --- | --- |
| description | ✓ | ✓ | ✓ |
| priority | ✓ | — | ✓ |
| province / district / road | ✓ | — | ✓ |
| gps_lat / gps_lng | ✓ (WAITING_VERIFY only) | — | ✓ |
| notes | ✓ | ✓ | ✓ |
| expected_fix_date | — | ✓ | ✓ |

### Pydantic Schemas

```python
class CaseCreate(BaseModel):
    source_channel: Literal["IMS_DIRECT"] = "IMS_DIRECT"
    priority: Literal["CRITICAL","HIGH","MEDIUM","LOW"] = "MEDIUM"
    service_type_code: str
    complaint_type_code: str | None = None
    reporter_name: str | None = None
    contact_number: str | None = None
    description: str
    province: str | None = None
    district_office: str | None = None
    road_number: str | None = None

class CaseResponse(BaseModel):
    case_id: str
    status: str
    priority: str
    source_channel: str
    service_type_code: str
    complaint_type_code: str | None
    reporter_name: str | None
    contact_number: str | None
    description: str
    province: str | None
    district_office: str | None
    road_number: str | None
    gps_lat: float | None
    gps_lng: float | None
    reported_at: datetime
    closed_at: datetime | None
    expected_fix_date: date | None
    assigned_officer_id: UUID | None
    assigned_officer_name: str | None   # join from users
    overdue_tier: int | None
    closure_reason_code: str | None
    duplicate_of_case_id: str | None
    created_at: datetime
    updated_at: datetime
```

---

## 3.3 Case Search & Filter

Implement the full filter set from scope §3.3 with cursor-based or offset pagination.

### Query Parameters

```
GET /api/v1/cases?
  q=<keyword>               ← full-text on description (PostgreSQL tsvector)
  case_id=<partial>         ← ILIKE match
  status=<CSV>              ← e.g. IN_PROGRESS,PENDING
  priority=<CSV>
  source_channel=<CSV>
  service_type_code=<CSV>
  complaint_type_code=<CSV>
  province=<str>
  district_office=<str>
  road_number=<str>
  assigned_officer_id=<UUID>
  overdue_tier=<int>
  date_from=<YYYY-MM-DD>    ← filters on reported_at
  date_to=<YYYY-MM-DD>
  page=1&page_size=20       ← max page_size = 100
```

### Officer Scope Restriction

Officers can only see cases where:
- `province = user.responsible_province` OR `assigned_officer_id = user.id`

### Steps

1. Build dynamic `WHERE` clause in `app/services/case_service.py` using SQLAlchemy `and_()`
2. Add `tsvector` index on `description` for full-text search:
   ```sql
   ALTER TABLE cases ADD COLUMN description_tsv tsvector
     GENERATED ALWAYS AS (to_tsvector('simple', description)) STORED;
   CREATE INDEX ON cases USING GIN(description_tsv);
   ```
3. Add GIN index migration in Alembic
4. Return `total_count`, `page`, `page_size`, `items` in response

---

## 3.4 Status Transition API

Enforces the state machine from scope §4.2.

```
POST /api/v1/cases/{case_id}/transition
Body: { "new_status": "IN_PROGRESS", "notes": "...", "assigned_officer_id": "UUID" }
```

### Transition Table (enforced server-side)

```python
ALLOWED_TRANSITIONS = {
    "WAITING_VERIFY": ["IN_PROGRESS", "REJECTED", "CANCELLED", "DUPLICATE"],
    "IN_PROGRESS":    ["FOLLOWING_UP", "PENDING", "DONE"],
    "FOLLOWING_UP":   ["IN_PROGRESS", "DONE"],
    "PENDING":        ["IN_PROGRESS", "DONE"],
    "DONE":           ["CLOSE", "WAITING_VERIFY"],   # WAITING_VERIFY = Admin reopen only
}
```

### Business Rules

- `WAITING_VERIFY → IN_PROGRESS`: requires `assigned_officer_id`; set `sla_started_at = NOW()`
- `IN_PROGRESS → PENDING`: requires `expected_fix_date`
- `WAITING_VERIFY → DUPLICATE`: requires `duplicate_of_case_id` in body
- `DONE → WAITING_VERIFY`: Admin only
- `DONE → CLOSE`: no extra fields needed; sets `closed_at = NOW()`
- SLA clock (`sla_started_at`) added as a computed/stored column

### Steps

1. Add `sla_started_at TIMESTAMP` column to `cases` (Alembic migration)
2. Implement `transition_case()` service function
3. On every transition: append row to `case_history`
4. On `WAITING_VERIFY → IN_PROGRESS`: trigger notification (Phase 6) — use SQS message for now
5. Validate role permissions per transition:
   - Only Admin can do `DONE → WAITING_VERIFY`
   - Officers cannot do `WAITING_VERIFY` transitions

---

## 3.5 SLA Calculation

Compute whether a case is overdue and at which tier.

```python
def compute_overdue_tier(
    status: str,
    sla_started_at: datetime | None,
    sla_config: SlaConfig,
) -> int | None:
    if status in ("DONE", "CLOSE", "CANCELLED", "REJECTED", "DUPLICATE"):
        return None
    if sla_started_at is None:
        return None
    days_since_sla = (datetime.utcnow() - sla_started_at).days
    temp_fix_deadline = sla_config.temp_fix_hours / 24
    if days_since_sla <= temp_fix_deadline:
        return None
    breach_days = days_since_sla - temp_fix_deadline
    if breach_days >= sla_config.overdue_t4_days:  return 4
    if breach_days >= sla_config.overdue_t3_days:  return 3
    if breach_days >= sla_config.overdue_t2_days:  return 2
    if breach_days >= sla_config.overdue_t1_days:  return 1
    return None
```

### Steps

1. Implement `compute_overdue_tier()` in `app/services/sla_service.py`
2. Call on every case read (lazy recalculate) — do NOT persist in API path
3. ETL also recalculates and persists `overdue_tier` in bulk (Phase 5)
4. Load `sla_config` from DB once per request (or cache with short TTL)

---

## 3.6 Case History Endpoint

```
GET /api/v1/cases/{case_id}/history
```

Returns append-only history of all status and assignment changes.

Response includes: `changed_at`, `changed_by` (user name), `prev_status`, `new_status`, `prev_assigned_officer`, `new_assigned_officer`, `change_notes`.

---

## 3.7 Attachment Upload/Download

### Upload

```
POST /api/v1/cases/{case_id}/attachments
Content-Type: multipart/form-data
Body: file (max 1 MB, image/* only)
```

1. Validate: file type `image/*`, size ≤ 1 MB
2. Server-side re-compress if needed (use `Pillow` — max dimension 1920px)
3. Generate S3 key: `attachments/{case_id}/{uuid}.{ext}`
4. Upload to `s3-attachments` bucket
5. Insert row into `case_attachments`
6. Enforce max 20 attachments per case

### Download

```
GET /api/v1/cases/{case_id}/attachments/{attachment_id}/url
```

Returns a pre-signed S3 URL (expiry: 1 hour). Never expose the S3 key directly.

### Steps

1. Install `Pillow` for image re-compression
2. Use `boto3.client('s3').generate_presigned_url()` for download
3. Use `boto3.client('s3').upload_fileobj()` for upload

---

## 3.8 Tier-4 Closure

```
POST /api/v1/cases/{case_id}/close-tier4
Body: { "closure_reason_code": "BUDGET_NOT_ALLOCATED", "notes": "..." }
```

- Admin only
- `overdue_tier` must be `4`
- Sets `status = CLOSE`, `closure_reason_code`, `closed_at = NOW()`
- If `closure_reason_code = OTHER`: `notes` is required
- This closure does NOT count as resolved in SLA metrics (filtered by `closure_reason_code IS NOT NULL`)

---

## Testing Plan

### Unit Tests

| Test | What to verify |
| --- | --- |
| `generate_case_id()` concurrent | 100 concurrent calls → 100 unique IDs, no gaps |
| `generate_case_id()` year rollover | Year changes → sequence resets to 000001 |
| `compute_overdue_tier()` — all tiers | Correct tier returned for each threshold |
| `compute_overdue_tier()` — closed case | Returns `None` |
| Transition: valid path | Status changes, history row inserted |
| Transition: invalid path | 422 validation error |
| Transition: role guard | OFFICER cannot do WAITING_VERIFY transition |
| Create case: service_type=6 missing province | 422 error |
| Create case: service_type≠6, location fields stripped | Fields set to NULL |
| Attachment: >20 files | 400 error |
| Attachment: >1MB file | 400 error |
| Attachment: non-image file | 400 error |
| Tier-4 closure: OTHER without notes | 422 error |

### Integration Tests

| Test | Pass Criteria |
| --- | --- |
| Full case lifecycle (WAITING_VERIFY → IN_PROGRESS → DONE → CLOSE) | All transitions succeed, history has 3 rows |
| Officer filter scope | Officer only sees cases in their province |
| Full-text search `q=ถนนชำรุด` | Returns relevant cases |
| Attachment pre-signed URL | URL accessible for < 1h, then expired |
| SLA: create case, advance time, check overdue_tier | Tier 1 after 3 days past SLA breach |

### Deliverables

- [ ] All CRUD endpoints tested and documented (FastAPI `/docs`)
- [ ] Status machine enforced with test coverage
- [ ] Case numbering working (no duplicates under load)
- [ ] Attachment upload/download working end-to-end
- [ ] SLA calculation correct for all 4 priorities
