# Phase 9 — Admin Features

## Goal

Implement all Admin-only capabilities: user management UI, handler master table mapping, SLA configuration (runtime, no deployment), case reopen, and Tier-4 closure. Admin is the only role that can configure system behavior.

## Prerequisites

- [ ] Phase 2 complete (user management API)
- [ ] Phase 3 complete (case transition API)
- [ ] Phase 4 complete (frontend routing)
- [ ] Phase 5 complete (`ref_handler` pre-loaded from data_sample)

---

## 9.1 Admin Section Layout

**Route:** `/admin/*`
**Access:** ADMIN role only

```
/admin/users          ← User management
/admin/handlers       ← Handler → User mapping (ref_handler)
/admin/sla            ← SLA configuration
/admin/reference      ← View reference tables (read-only)
```

Left sidebar navigation visible only to ADMIN role.

---

## 9.2 User Management UI

Built on Phase 2 user API. Complete the frontend components.

### User List Page (`/admin/users`)

| Column | Notes |
| --- | --- |
| Name | Full name |
| Email | |
| Role | Badge color per role |
| Province | Officers only |
| Status | Active / Inactive |
| Created | Date |
| Actions | Edit, Deactivate/Activate, Reset Password |

### Create User Modal

Form fields:
- Full name (required)
- Email (required, valid email)
- Role (select: ADMIN / DISPATCHER / OFFICER / EXECUTIVE)
- Responsible Province (show only if role = OFFICER)

On submit: `POST /api/v1/users` → Cognito sends temporary password email to user.

### Edit User Modal

Editable: full_name, role, responsible_province, is_active.

Not editable: email, cognito_user_id.

### Reset Password

Button → confirm dialog → `POST /api/v1/users/{id}/reset-password`.
Cognito sends a new temporary password to the user's email.

### Deactivate User

Toggle switch → `PUT /api/v1/users/{id}` with `is_active: false`.
Also calls Cognito `AdminDisableUser`. Disabled users cannot log in.

---

## 9.3 Handler Master Table UI (`/admin/handlers`)

Map the 14 LINE OA handler display names to IMS user accounts. This is required before go-live to correctly assign incoming LINE cases.

### Handler List

| Column | Notes |
| --- | --- |
| Handler Display Name | Exact string from LINE source data |
| Mapped User | Dropdown of OFFICER/DISPATCHER users |
| Status | Mapped / Unmapped |
| Active | Toggle |

### API Endpoints (new — add to Phase 2 user API)

```
GET    /api/v1/admin/handlers          ← list all ref_handler rows
PUT    /api/v1/admin/handlers/{id}     ← update user_id mapping + is_active
```

### Business Rules

- Only ADMIN can map handlers
- Mapping is optional before ETL runs — unmapped handlers log a warning and set `assigned_officer_id = NULL`
- Must map all 14 handlers before go-live (show warning banner if any unmapped)

### Steps

1. Create `app/api/v1/admin/handlers.py`
2. Create `src/pages/admin/HandlersPage.tsx`
3. Show unmapped count badge in admin sidebar nav

---

## 9.4 SLA Configuration UI (`/admin/sla`)

Runtime-configurable SLA thresholds. No code deployment required.

### Current Config Table

| Priority | Temp Fix (hours) | Permanent Fix (days) | Tier 1 (days) | Tier 2 (days) | Tier 3 (days) | Tier 4 (days) |
| --- | --- | --- | --- | --- | --- | --- |
| CRITICAL | 12 | 7 | 3 | 7 | 30 | 365 |
| HIGH | 24 | 7 | 3 | 7 | 30 | 365 |
| MEDIUM | 72 | 7 | 3 | 7 | 30 | 365 |
| LOW | 168 | 7 | 3 | 7 | 30 | 365 |

Admin can edit any cell inline. On save: `PUT /api/v1/admin/sla-config/{priority}`.

### API Endpoints

```
GET  /api/v1/admin/sla-config
PUT  /api/v1/admin/sla-config/{priority}
Body: { "temp_fix_hours": 12, "permanent_fix_days": 7, "overdue_t1_days": 3, ... }
```

### Validation Rules

- `temp_fix_hours` > 0
- All `overdue_t{n}_days` must be strictly increasing: t1 < t2 < t3 < t4
- Changes take effect on the next ETL overdue_tier_refresh DAG run

### Steps

1. Create `app/api/v1/admin/sla.py`
2. Create `src/pages/admin/SlaConfigPage.tsx`
3. Show note: "การเปลี่ยนแปลงจะมีผลในรอบ ETL ถัดไป (ภายใน 1 ชั่วโมง)"

---

## 9.5 Case Reopen (Admin Only)

Admin can reopen a `DONE` case back to `WAITING_VERIFY`.

### Flow

1. Admin views a case with `status = DONE`
2. "Reopen Case" button visible only to ADMIN
3. Confirm modal: "ยืนยันการเปิดเรื่องใหม่? เรื่องนี้จะกลับไปยังสถานะ รอตรวจสอบ"
4. `POST /api/v1/cases/{id}/transition` with `{ "new_status": "WAITING_VERIFY", "notes": "Reopened by Admin" }`
5. History row appended
6. Notification emitted to Dispatcher

Already implemented in Phase 3 transition logic — this phase adds the UI button and ensures it's visible only to ADMIN.

---

## 9.6 Tier-4 Closure UI (Admin Only)

Admin can formally close a Tier-4 overdue case with a reason code.

### Location

Case detail page — when `overdue_tier = 4`, ADMIN sees an additional button: "ปิดเรื่อง (เกิน SLA ชั้น 4)"

### Modal Fields

- **Reason code** (required dropdown):
  - งบประมาณยังไม่ได้รับการจัดสรร
  - งบประมาณไม่เพียงพอ
  - ขอบเขตงานใหญ่เกินไป
  - รอหน่วยงานอื่น
  - อื่น ๆ (requires additional notes field)
- **Notes** (required if reason = OTHER, optional otherwise)

On submit: `POST /api/v1/cases/{id}/close-tier4`

### Visual Distinction

Tier-4 closures must appear differently from normal CLOSE in:
- Case list status badge: "ปิด (เกิน SLA)" in dark red
- Dashboard: counted separately from normal CLOSE in SLA metrics

---

## 9.7 Audit Log (Admin View)

No download UI required (scope §2.2). Add an informational note in admin panel:

```
📁 บันทึกการตรวจสอบ (Audit Log)
ข้อมูล audit log ทั้งหมดถูกบันทึกไปยัง Amazon S3
ที่อยู่: s3://[bucket-name]/audit/
หากต้องการเข้าถึง กรุณาติดต่อผู้ดูแลระบบ AWS
```

The audit log write logic (to S3) is implemented across all other phases as a cross-cutting concern:

### Audit Events to Write

In `app/services/audit_service.py`:

```python
async def log_audit(
    category: str,
    action: str,
    user_id: UUID,
    resource_id: str | None,
    details: dict,
):
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "category": category,
        "action": action,
        "user_id": str(user_id),
        "resource_id": resource_id,
        "details": details,
    }
    s3.put_object(
        Bucket=settings.s3_audit_bucket,
        Key=f"audit/{datetime.utcnow().strftime('%Y/%m/%d')}/{uuid4()}.json",
        Body=json.dumps(event, ensure_ascii=False),
    )
```

### Integration Points (add to existing phases)

| Phase | Where to call `log_audit()` |
| --- | --- |
| 2 | User create, update, deactivate, password reset |
| 3 | Case create, update, status transition, Tier-4 close |
| 4 | Login, logout (via Cognito event → Lambda → S3, or client call) |
| 8 | Export triggered |
| 9 | SLA config updated, handler mapping updated |

---

## Testing Plan

### Unit Tests

| Test | What to verify |
| --- | --- |
| SLA config validation — t1 > t2 | Rejected with 422 |
| SLA config validation — valid | Saved to DB |
| Handler mapping — valid user_id | FK constraint passes |
| Handler mapping — null user_id | Allowed (unmapped state) |
| Tier-4 closure — OTHER without notes | 422 returned |
| Tier-4 closure — overdue_tier ≠ 4 | 422 returned |

### Integration Tests

| Test | Method | Pass Criteria |
| --- | --- | --- |
| Create user flow | POST /users → check Cognito + DB | User exists in both |
| Deactivate user | PUT is_active=false → login attempt | 401 from Cognito |
| Handler mapping | PUT handler → trigger ETL with that handler | `assigned_officer_id` populated |
| SLA config change | Update CRITICAL to 6 hours → run overdue calc | Cases recalculated with new threshold |
| Case reopen | DONE → WAITING_VERIFY | Status changed, history appended, notification sent |
| Tier-4 closure | Close with reason → dashboard metric | Not counted as resolved |
| Audit log | Perform action → check S3 | JSON file created with correct fields |

### Deliverables

- [ ] All 4 admin pages working (/users, /handlers, /sla, /reference)
- [ ] Handler master table fully mapped before go-live
- [ ] SLA thresholds editable without deployment
- [ ] Audit log writing to S3 for all categories
- [ ] Tier-4 closure with reason code working
- [ ] User deactivation synced to Cognito
