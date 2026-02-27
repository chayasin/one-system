# Rural Roads One System
## Software Requirements Specification (SRS)
### Incident Management System & Executive Dashboard

| Field | Value |
|---|---|
| Document Version | 1.3 |
| Status | Draft – Pending Final Review |
| Project | proj-one-system |
| Client | Rural Roads Department (กรมทางหลวงชนบท) |
| Prepared by | NexMind / Harmony |
| Last Updated | February 2026 |
| Classification | Confidential |

### Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | Feb 14, 2026 | Initial draft |
| 1.1 | Feb 27, 2026 | Updated SLA tiers, overdue escalation, case number, pipeline spec, export formats |
| 1.2 | Feb 27, 2026 | Added real data schema from data_sample analysis (1146 + LINE OA field mapping, master tables, nullability rules, canonical IMS schema) |
| 1.3 | Feb 27, 2026 | Resolved all open items: 1146=REST pull, LINE=Webhook→SQS buffer, complaint types finalized CT01–CT12, Tier-4 closure codes added, Excel export schema defined, handler master table added, GPS entered by dispatcher |

---

## 1. Overview

### 1.1 Purpose

This document defines the software requirements for the Rural Roads One System, comprising two integrated modules:

- **Incident Management System (IMS)** – for receiving, managing, assigning, tracking, and closing public complaint cases.
- **Executive Dashboard** – for leadership to monitor case statistics and track operational performance in near-real-time.

### 1.2 Project Background

The Rural Roads Department requires a centralized digital platform to replace fragmented manual processes for handling citizen road complaints. Complaints arrive through two primary external channels — the **1146 call center** and **LINE OA** — plus cases created directly in the IMS. The platform must provide transparency, accountability, and timely SLA-driven resolution tracking.

### 1.3 Stakeholders

| Role | Description |
|---|---|
| Citizen / Reporter | Submits road complaints via supported channels |
| Dispatcher (ผู้รับเรื่อง) | Verifies and assigns incoming cases to Officers |
| Officer | Handles assigned cases in their responsible area |
| Executive | Monitors KPIs, statistics, and exports reports |
| Admin | Manages users, roles, and system configuration |

---

## 2. System Scope

### 2.1 In Scope

| Feature | Description |
|---|---|
| Incident Creation & Management | Full lifecycle from creation to closure with mandatory fields |
| Workflow & Assignment | Status transitions, case assignment with history tracking |
| Executive Dashboard | KPIs, drilldowns, near-real-time metrics |
| CSV / Excel / PDF Export | Filtered data export (CSV + Excel) and Dashboard PDF snapshot |
| User & Role Management | Admin-controlled user accounts and role assignment |
| Audit Logging | All user and system actions stored to S3 |
| In-App Notifications | Bell icon notifications for key workflow events |
| SLA Enforcement | 4-tier priority SLA with temp-fix and permanent-fix deadlines |
| Overdue Escalation | 4-tier overdue escalation with distinct meanings per tier |
| Data Pipeline | Hourly ingestion from 1146 and LINE OA; configurable to 5-min sync |
| Running Case Number | Auto-generated `RRD-YYYY-NNNNNN`, reset yearly |
| HTTPS & Basic Security | TLS, Cognito authentication, login required for all roles |

### 2.2 Out of Scope

- Disaster Recovery (DR) / multi-region failover
- Advanced password policies beyond basic Cognito configuration
- Audit Log Download UI (logs accessible directly from S3)

---

## 3. Incident Management System

### 3.1 Canonical Incident Fields

These are the unified fields for every incident regardless of source channel:

| Field | Column Name | Type | Nullable | Notes |
|---|---|---|---|---|
| Case ID | `case_id` | VARCHAR(20) | No | Format: `RRD-YYYY-NNNNNN` |
| Source Channel | `source_channel` | ENUM | No | `LINE`, `CALL_1146`, `IMS_DIRECT` |
| Source Sequence No. | `source_seq_no` | INT | Yes | ลำดับ from original source |
| Status | `status` | ENUM | No | See §4.1 |
| Priority | `priority` | ENUM | No | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| Service Type | `service_type_code` | VARCHAR(5) | No | FK → `ref_service_type` |
| Complaint Type | `complaint_type_code` | VARCHAR(10) | Yes | FK → `ref_complaint_type` — only when service_type = 6 |
| Reporter Name | `reporter_name` | VARCHAR(200) | Yes | ชื่อผู้ติดต่อ — "ไม่ระบุ" stored as NULL |
| Phone / Contact | `contact_number` | VARCHAR(50) | Yes | หมายเลขที่ติดต่อเข้ามา (call) or LINE ID |
| LINE User ID | `line_user_id` | VARCHAR(100) | Yes | ID Line — only for LINE source |
| Handler Name | `handler_name` | VARCHAR(200) | Yes | ผู้รับเรื่อง — LINE source only; call has no handler |
| Description | `description` | TEXT | No | รายละเอียด |
| Province | `province` | VARCHAR(100) | Yes | จังหวัด — required only when service_type = 6 (ร้องเรียน) |
| District Office | `district_office` | VARCHAR(200) | Yes | แขวงทางหลวงชนบท |
| Road Number | `road_number` | VARCHAR(50) | Yes | หมายเลขถนน e.g. `นว.1001` |
| GPS Lat | `gps_lat` | DECIMAL(10,7) | Yes | Entered by Dispatcher during WAITING_VERIFY review, before assignment |
| GPS Long | `gps_lng` | DECIMAL(10,7) | Yes | Entered by Dispatcher during WAITING_VERIFY review, before assignment |
| Reported At | `reported_at` | TIMESTAMP | No | Combined date + time from source |
| Received At | `received_at` | TIMESTAMP | Yes | เวลารับแจ้ง — LINE only |
| Closed At | `closed_at` | TIMESTAMP | Yes | เวลาปิดเรื่อง |
| Notes | `notes` | TEXT | Yes | หมายเหตุ — currently always NULL in source data |
| Duplicate Of | `duplicate_of_case_id` | VARCHAR(20) | Yes | FK → cases.case_id — set when status = เรื่องซ้ำ |
| Assigned Officer | `assigned_officer_id` | UUID | Yes | FK → users |
| Expected Fix Date | `expected_fix_date` | DATE | Yes | Required when status = PENDING |
| Overdue Tier | `overdue_tier` | SMALLINT | Yes | 1–4, computed by ETL |
| Closure Reason | `closure_reason_code` | VARCHAR(50) | Yes | e.g. `BUDGET_NOT_ALLOCATED` for Tier-4 closure |
| Raw Extra | `raw_extra` | JSONB | Yes | Unmapped source fields — never discarded |
| Source Schema Version | `source_schema_version` | VARCHAR(20) | No | e.g. `line_v1`, `call_v1` |
| Created At | `created_at` | TIMESTAMP | No | System insert time |
| Updated At | `updated_at` | TIMESTAMP | No | System last update time |

### 3.2 Attachment Rules

- Maximum 20 images per case
- Maximum 1 MB per image file
- Client-side compression applied before upload; server re-validates
- Files stored in Amazon S3 with retention ≥ 3 years
- Served via pre-signed URL with expiry

### 3.3 Search & Filter

Supported filters: case number, keyword (full-text on description), province, district office, road number, status, priority, complaint type, service type, source channel, date range, assigned officer, overdue tier.

---

## 4. Workflow & Status Management

### 4.1 Status Definitions

The source data uses Thai status values. These map to canonical IMS statuses as follows:

| IMS Status | Thai (Source) | Description | Can Cancel? |
|---|---|---|---|
| `WAITING_VERIFY` | — | Awaiting dispatcher review (new entry) | Yes |
| `IN_PROGRESS` | อยู่ระหว่างดำเนินการ | Assigned and being worked on | No |
| `FOLLOWING_UP` | ตามเรื่อง | Follow-up required | No |
| `DUPLICATE` | เรื่องซ้ำ | Duplicate of existing case | — |
| `DONE` | ปิดเรื่อง | Case closed | No |
| `PENDING` | — | On hold, requires expected date | No |
| `REJECTED` | — | Out of scope or insufficient info | No |
| `CANCELLED` | — | Cancelled by reporter | — |
| `CLOSE` | — | Final permanent closed state | — |

> **Note on source statuses:** The `data_sample` shows 4 source statuses (ปิดเรื่อง, อยู่ระหว่างดำเนินการ, ตามเรื่อง, เรื่องซ้ำ). These are migrated and mapped to IMS statuses on ingestion. Going forward, all status transitions are managed within IMS.

### 4.2 Transition Rules

| From | To | Trigger / Condition |
|---|---|---|
| (New) | `WAITING_VERIFY` | Case created or ingested |
| `WAITING_VERIFY` | `IN_PROGRESS` | Dispatcher assigns to officer |
| `WAITING_VERIFY` | `REJECTED` | Dispatcher rejects (out of scope) |
| `WAITING_VERIFY` | `CANCELLED` | Reporter requests cancellation |
| `WAITING_VERIFY` | `DUPLICATE` | Dispatcher marks as duplicate |
| `IN_PROGRESS` | `FOLLOWING_UP` | Officer escalates to follow-up |
| `IN_PROGRESS` | `PENDING` | Officer sets on hold with expected date |
| `IN_PROGRESS` | `DONE` | Officer marks complete |
| `FOLLOWING_UP` | `IN_PROGRESS` | Officer resumes work |
| `FOLLOWING_UP` | `DONE` | Officer marks complete |
| `PENDING` | `IN_PROGRESS` | Officer resumes |
| `PENDING` | `DONE` | Officer marks complete |
| `DONE` | `CLOSE` | Final closure |
| `DONE` | `WAITING_VERIFY` | Admin reopens (only) |

### 4.3 Assignment Rules

- One case assigned to exactly one officer at a time.
- Full assignment + status history retained (append-only `case_history` table).

### 4.4 Expected Completion Date

- Date format: DD-MM-YYYY (Buddhist Era year, พ.ศ.)
- Time format: HH:MM น.
- If current datetime exceeds expected date → case flagged Overdue

---

## 5. SLA (Service Level Agreement)

### 5.1 SLA by Priority

| Priority | Temp Fix Deadline | Permanent Fix Deadline |
|---|---|---|
| Critical | 12 hours | 7 days |
| High | 1 day | 7 days |
| Medium | 3 days | 7 days |
| Low | 1 week (7 days) | 7 days |

Both deadlines tracked independently. SLA clock starts when status moves to `IN_PROGRESS`.

### 5.2 Overdue Escalation Tiers

Tiers measured from SLA breach date (not case creation):

| Tier | Threshold Past SLA | Typical Reason | System Action |
|---|---|---|---|
| 1 | 3 days | Officer forgot / waiting for materials | In-app notification to officer + admin |
| 2 | 7 days | Resource bottleneck or awaiting approval | Escalation alert to supervisor + admin |
| 3 | 1 month | Underlying problem, pending investigation | High-visibility dashboard flag |
| 4 | 1 year | Fix too large, budget not yet allocated | Admin can formally close with reason code `BUDGET_NOT_ALLOCATED` |

Tier 4 cases can be closed without implying resolution. The budget-closure reason must be preserved in `closure_reason_code`.

### 5.3 SLA Configuration

All thresholds configurable at runtime by Admin — no code deployment required. SLA check runs on the same cadence as the ETL refresh.

### 5.4 Tier-4 Closure Reason Codes

When an Admin closes a Tier-4 case, they must select a reason code. The following codes are confirmed:

| Code | Label | Description |
|---|---|---|
| `BUDGET_NOT_ALLOCATED` | งบประมาณยังไม่ได้รับการจัดสรร | Fix requires budget that has not been approved |
| `BUDGET_INSUFFICIENT` | งบประมาณไม่เพียงพอ | Budget exists but is insufficient for the scope of work |
| `SCOPE_TOO_LARGE` | ขอบเขตงานใหญ่เกินไป | Project scope exceeds departmental authority — requires escalation to a higher body |
| `PENDING_EXTERNAL_AGENCY` | รอหน่วยงานอื่น | Responsibility transferred to another agency; case cannot progress without their action |
| `OTHER` | อื่น ๆ | Other reason — free-text note required |

All Tier-4 closures are flagged distinctly in the dashboard and audit log — they are **not** counted as resolved cases in SLA metrics.

---

## 6. Case Numbering

```
RRD-YYYY-NNNNNN
```

- `RRD` = Rural Roads Department prefix
- `YYYY` = Buddhist Era year (พ.ศ.), e.g., 2568
- `NNNNNN` = 6-digit zero-padded sequence, resets to `000001` each new year

---

## 7. Data Sources & Input Channels

### 7.1 Source Channels Confirmed

| Channel ID | Channel | Input Format | Volume (sample month) |
|---|---|---|---|
| `CALL_1146` | 1146 Call Center | JSON (API pull) | ~2,942 cases/month |
| `LINE` | LINE OA | JSON (Webhook/API pull) | ~1,138 cases/month |
| `IMS_DIRECT` | IMS Web UI | Form submit | Manual |

### 7.2 Source Field Mapping

#### LINE OA → IMS Canonical

| Source Field (TH) | Source Column | IMS Field | Notes |
|---|---|---|---|
| ลำดับ | `ลำดับ` | `source_seq_no` | Sequential number in source |
| สถานะ | `สถานะ` | `status` (mapped) | 4 values → IMS statuses |
| วันที่ | `วันที่` | `reported_at` (date part) | Date only, combine with เวลาแจ้ง |
| เวลาแจ้ง | `เวลาแจ้ง` | `reported_at` (time part) | Format: `HH.MM น.` → parse to time |
| เวลารับแจ้ง | `เวลารับแจ้ง` | `received_at` | Format: `HH.MM น.` |
| เวลาปิดเรื่อง | `เวลาปิดเรื่อง` | `closed_at` | Format: `HH.MM น.` |
| ผู้รับเรื่อง | `ผู้รับเรื่อง` | `handler_name` | 14 distinct handlers in sample |
| ชื่อผู้ติดต่อ | `ชื่อผู้ติดต่อ` | `reporter_name` | "ไม่ระบุ" → store as NULL |
| ID Line | `ID Line` | `line_user_id` | Display name / LINE ID (not UID) |
| เรื่องที่ขอรับบริการ | `เรื่องที่ขอรับบริการ` | `service_type_code` | Parse prefix number e.g. `6` from `6.ร้องเรียน` |
| เรื่องร้องเรียน | `เรื่องร้องเรียน` | `complaint_type_code` | Only populated when service_type = 6 |
| รายละเอียด | `รายละเอียด` | `description` | Always present |
| จังหวัด | `จังหวัด` | `province` | Only filled when service_type = 6 |
| แขวงทางหลวงชนบท | `แขวงทางหลวงชนบท` | `district_office` | Only filled when service_type = 6 |
| หมายเลขถนน | `หมายเลขถนน` | `road_number` | Only filled when service_type = 6 |
| หมายเหตุ | `หมายเหตุ` | `notes` | Currently always NULL in source |

#### 1146 Call Center → IMS Canonical

| Source Field (TH) | Source Column | IMS Field | Notes |
|---|---|---|---|
| ลำดับ | `ลำดับ` | `source_seq_no` | |
| สถานะ | `สถานะ` | `status` (mapped) | Same 4 statuses as LINE |
| วันที่ | `วันที่` | `reported_at` (date part) | |
| เวลา | `เวลา` | `reported_at` (time part) | Format: `HH:MM:SS` (Python `time` object — different from LINE!) |
| ชื่อผู้ติดต่อ | `ชื่อผู้ติดต่อ` | `reporter_name` | Includes org names e.g. "กรมป้องกันและบรรเทาสาธารณภัย" |
| หมายเลขที่ติดต่อเข้ามา | `หมายเลขที่ติดต่อเข้ามา` | `contact_number` | Phone number or short code (e.g. `1784`) |
| เรื่องที่ขอรับบริการ | `เรื่องที่ขอรับบริการ` | `service_type_code` | 11 distinct values (wider than LINE) |
| เรื่องร้องเรียน | `เรื่องร้องเรียน` | `complaint_type_code` | Only populated when service_type = 6 |
| รายละเอียด | `รายละเอียด` | `description` | Very detailed, often includes coordination notes |
| จังหวัด | `จังหวัด` | `province` | **100% filled** when service_type = 6, NULL otherwise |
| แขวงทางหลวงชนบท | `แขวงทางหลวงชนบท` | `district_office` | Near 100% filled for complaints |
| หมายเลขถนน | `หมายเลขถนน` | `road_number` | ~99.6% filled for complaints |
| หมายเหตุ | `หมายเหตุ` | `notes` | Always NULL in source data |

> **Important parsing note:** LINE uses time format `HH.MM น.` while 1146 uses `HH:MM:SS`. ETL must handle both formats separately per source schema version.

### 7.3 Master / Reference Tables

#### ref_service_type (เรื่องที่ขอรับบริการ)

| Code | Label (TH) |
|---|---|
| 1 | สอบถามสภาพการจราจร |
| 2 | สอบถามเส้นทาง |
| 3 | แจ้งอุบัติเหตุ |
| 4 | ขอความช่วยเหลือรถเสีย |
| 5 | ภัยพิบัติ |
| 6 | ร้องเรียน |
| 7 | สอบถามข้อมูลหน่วยงานกรมทางหลวงชนบท |
| 8 | สอบถามข้อมูลหน่วยงานอื่นๆ |
| 9 | อื่น ๆ |
| 10 | เบอร์รบกวน *(call only)* |
| 11 | ข่าวประชาสัมพันธ์/รูปภาพสวัสดี *(LINE only)* |
| 12 | กดประเมินปรับปรุง *(call only)* |

#### ref_complaint_type (เรื่องร้องเรียน_ถนน)

Populated only when `service_type_code = 6`:

| Code | Label (TH) |
|---|---|
| CT01 | ไฟฟ้าส่องสว่างดับ/ชำรุด/ติดตั้ง |
| CT02 | ถนนชำรุด |
| CT03 | ป้ายจราจร ชำรุด/สูญหาย/ติดตั้ง/ย้าย |
| CT04 | สัญญาณไฟจราจร ชำรุด/เสียหาย/ติดตั้ง |
| CT05 | วัชพืช/ต้นไม้/ขยะ |
| CT06 | สะพานลอย ชำรุด/เสียหาย/ติดตั้ง |
| CT07 | ทางเท้า ชำรุด/เสียหาย/ติดตั้ง |
| CT08 | ขอเชื่อมทาง เปิด/ปิด ทางเข้าออก |
| CT09 | รถบรรทุกน้ำหนักเกิน/ด่านชั่งน้ำหนัก |
| CT10 | รุกล้ำเขตทาง /ขายของริมทาง/ป้ายโฆษณา |
| CT11 | เหตุเดือดร้อน (เสียง/กลิ่น/ฝุ่น/น้ำท่วม) |
| CT12 | อื่น ๆ |

> **Data quality note:** Source data contains minor variants (e.g. `ป้ายจราจรชำรุด/สูญหาย/ติดตั้ง/ย้าย` vs `ป้ายจราจร ชำรุด/สูญหาย/ติดตั้ง/ย้าย`). ETL must normalize these to canonical codes on load.

#### ref_handler (ผู้รับเรื่อง — Handler Master)

The LINE source data carries handler names as free-text strings (`ผู้รับเรื่อง`). These do **not** automatically map to IMS user accounts. A handler master table is required to bridge the two:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `display_name` | VARCHAR(200) | Exact string as it appears in source data (e.g. `ธนนันท์ จันที`) |
| `user_id` | UUID | FK → `users` — nullable until mapped |
| `is_active` | BOOLEAN | Whether this handler is currently active |
| `created_at` | TIMESTAMP | |

The 14 handlers observed in the data_sample must be pre-loaded into `ref_handler` and mapped to their corresponding `users` accounts by Admin before go-live. ETL links `cases.assigned_officer_id` via this table on ingestion. Unmapped handlers store `NULL` in `assigned_officer_id` and log a warning.

### 7.4 Nullability Rules Observed from Data

| Condition | Province | District Office | Road Number | Complaint Type |
|---|---|---|---|---|
| service_type = 6 (ร้องเรียน) | **Required** (100% filled) | Required | Required (~99%) | Required |
| service_type ≠ 6 | NULL | NULL | NULL | NULL |

This means the ETL and IMS validation layer must enforce: **location fields + complaint_type are only required when service_type = 6.**

### 7.5 Input Schema Flexibility

- **Schema-on-read:** Raw JSON stored as-is in S3 Landing Zone; parsing in ETL layer.
- **Field mapping config:** YAML-based mapping file per source (e.g. `mapping_line_v1.yaml`, `mapping_call_v1.yaml`). Changing a mapping requires no code deployment.
- **Unknown fields:** Stored in `raw_extra` (JSONB) — never discarded.
- **Version tagging:** Every record carries `source_schema_version` (e.g. `line_v1`, `call_v1`).
- **Null tolerance:** All non-critical fields nullable at landing; validation applied in processed zone.

---

## 8. Database Schema (Operational — Aurora PostgreSQL)

### 8.1 Core Tables

```sql
-- Incidents
cases (
  case_id               VARCHAR(20)     PRIMARY KEY,   -- RRD-YYYY-NNNNNN
  source_channel        VARCHAR(20)     NOT NULL,      -- LINE | CALL_1146 | IMS_DIRECT
  source_seq_no         INT,
  source_schema_version VARCHAR(20)     NOT NULL,
  status                VARCHAR(30)     NOT NULL,
  priority              VARCHAR(10)     NOT NULL,      -- CRITICAL | HIGH | MEDIUM | LOW
  service_type_code     VARCHAR(5)      NOT NULL,      -- FK ref_service_type
  complaint_type_code   VARCHAR(10),                   -- FK ref_complaint_type (nullable)
  reporter_name         VARCHAR(200),
  contact_number        VARCHAR(50),
  line_user_id          VARCHAR(100),
  handler_name          VARCHAR(200),
  description           TEXT            NOT NULL,
  province              VARCHAR(100),
  district_office       VARCHAR(200),
  road_number           VARCHAR(50),
  gps_lat               DECIMAL(10,7),
  gps_lng               DECIMAL(10,7),
  reported_at           TIMESTAMP       NOT NULL,
  received_at           TIMESTAMP,
  closed_at             TIMESTAMP,
  expected_fix_date     DATE,
  assigned_officer_id   UUID,                          -- FK users
  overdue_tier          SMALLINT,                      -- 1-4, NULL if not overdue
  closure_reason_code   VARCHAR(50),
  notes                 TEXT,
  duplicate_of_case_id  VARCHAR(20),                   -- FK cases (self)
  raw_extra             JSONB,
  created_at            TIMESTAMP       NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMP       NOT NULL DEFAULT NOW()
)

-- Case history (append-only audit trail)
case_history (
  id                    UUID            PRIMARY KEY,
  case_id               VARCHAR(20)     NOT NULL,      -- FK cases
  changed_by_user_id    UUID,
  changed_at            TIMESTAMP       NOT NULL DEFAULT NOW(),
  prev_status           VARCHAR(30),
  new_status            VARCHAR(30),
  prev_assigned_officer UUID,
  new_assigned_officer  UUID,
  change_notes          TEXT
)

-- Attachments
case_attachments (
  id                    UUID            PRIMARY KEY,
  case_id               VARCHAR(20)     NOT NULL,
  s3_key                VARCHAR(500)    NOT NULL,
  file_name             VARCHAR(255),
  file_size_bytes       INT,
  uploaded_by_user_id   UUID,
  uploaded_at           TIMESTAMP       NOT NULL DEFAULT NOW()
)

-- Users
users (
  id                    UUID            PRIMARY KEY,
  cognito_user_id       VARCHAR(200)    NOT NULL UNIQUE,
  full_name             VARCHAR(200)    NOT NULL,
  email                 VARCHAR(200),
  role                  VARCHAR(20)     NOT NULL,      -- ADMIN | DISPATCHER | OFFICER | EXECUTIVE
  responsible_province  VARCHAR(100),                  -- For officers: area scope
  is_active             BOOLEAN         NOT NULL DEFAULT TRUE,
  created_at            TIMESTAMP       NOT NULL DEFAULT NOW()
)

-- Reference: Service Types
ref_service_type (
  code    VARCHAR(5)    PRIMARY KEY,
  label   VARCHAR(200)  NOT NULL,
  channel VARCHAR(20)   -- LINE | CALL_1146 | ALL (null = available for all)
)

-- Reference: Complaint Types
ref_complaint_type (
  code    VARCHAR(10)   PRIMARY KEY,
  label   VARCHAR(200)  NOT NULL
)

-- Notifications
notifications (
  id                UUID        PRIMARY KEY,
  user_id           UUID        NOT NULL,  -- FK users
  case_id           VARCHAR(20),
  type              VARCHAR(50) NOT NULL,  -- ASSIGNED | CLOSED | OVERDUE_T1 | OVERDUE_T2 etc.
  message           TEXT,
  is_read           BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMP   NOT NULL DEFAULT NOW()
)

-- Case sequence counter
case_sequence (
  year    SMALLINT    PRIMARY KEY,   -- Buddhist Era year e.g. 2568
  last_seq INT        NOT NULL DEFAULT 0
)

-- Handler master (bridges LINE source handler names → IMS users)
ref_handler (
  id            UUID          PRIMARY KEY,
  display_name  VARCHAR(200)  NOT NULL UNIQUE,  -- exact string from source
  user_id       UUID,                            -- FK users (nullable until mapped)
  is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMP     NOT NULL DEFAULT NOW()
)

-- Tier-4 closure reason codes (reference)
ref_closure_reason (
  code    VARCHAR(50)   PRIMARY KEY,
  label   VARCHAR(200)  NOT NULL,
  label_th VARCHAR(200) NOT NULL,
  requires_note BOOLEAN NOT NULL DEFAULT FALSE
)

-- SLA configuration
sla_config (
  id                  UUID        PRIMARY KEY,
  priority            VARCHAR(10) NOT NULL,
  temp_fix_hours      INT         NOT NULL,
  permanent_fix_days  INT         NOT NULL,
  overdue_t1_days     INT         NOT NULL DEFAULT 3,
  overdue_t2_days     INT         NOT NULL DEFAULT 7,
  overdue_t3_days     INT         NOT NULL DEFAULT 30,
  overdue_t4_days     INT         NOT NULL DEFAULT 365,
  updated_by          UUID,
  updated_at          TIMESTAMP   NOT NULL DEFAULT NOW()
)
```

### 8.2 Mini Data Warehouse (Summary Tables — for Dashboard)

```sql
-- Refreshed by Airflow; used only for dashboard reads
summary_cases_daily (
  summary_date          DATE,
  source_channel        VARCHAR(20),
  province              VARCHAR(100),
  district_office       VARCHAR(200),
  service_type_code     VARCHAR(5),
  complaint_type_code   VARCHAR(10),
  priority              VARCHAR(10),
  status                VARCHAR(30),
  case_count            INT,
  overdue_count         INT,
  closed_within_sla     INT,
  avg_close_hours       DECIMAL(10,2),
  PRIMARY KEY (summary_date, source_channel, province, service_type_code, complaint_type_code, priority, status)
)
```

---

## 9. Data Pipeline

### 9.1 Architecture

```
[LINE OA]  ──webhook──► [Our Webhook Endpoint] ──► [SQS Queue] ──┐
                                                                   ├──► [Airflow ETL] ──► [S3 Landing Zone (Raw JSON)]
[1146 API] ──REST pull (hourly)────────────────────────────────────┘              └──► [S3 Processed Zone]
                                                                                  ├──► [Aurora: cases]
                                                                                  └──► [Aurora: summary_cases_daily]
```

**LINE OA flow:** LINE platform pushes message events to our webhook URL via the Messaging API (standard LINE architecture). The webhook endpoint immediately writes each event to SQS and returns HTTP 200 to LINE (fast, no data loss). Airflow drains the SQS queue on schedule and processes into the landing zone. This is the canonical pattern for LINE Messaging API integrations and avoids the need for a polling/pull API (which LINE does not natively support for message history).

**1146 flow:** Airflow DAG calls the 1146 REST endpoint on schedule and pulls new records since the last watermark timestamp.

### 9.2 Ingestion Schedule

| Source | Access Method | Current Frequency | Min Supported | Change Requires |
|---|---|---|---|---|
| LINE OA | Webhook → SQS → Airflow drain | Hourly | 5 minutes | Airflow schedule param only |
| 1146 Call Center | REST pull (watermark-based) | Hourly | 5 minutes | Airflow schedule param only |

### 9.3 ETL Rules

- **Idempotent:** Re-running a DAG for the same time window must not create duplicates (deduplicate on `source_channel + source_seq_no + reported_at`).
- **Normalization:** Complaint type string variants normalized to canonical codes via lookup table.
- **Time parsing:** LINE format `HH.MM น.` and CALL format `HH:MM:SS` handled per `source_schema_version`.
- **NULL normalization:** "ไม่ระบุ" in reporter_name → stored as NULL.
- **raw_extra:** Unmapped source fields always preserved in JSONB column.
- **Failure handling:** Failed DAG runs must alert via CloudWatch; visible in Airflow UI.
- **Overdue computation:** `overdue_tier` recalculated on every ETL run based on SLA config.

### 9.4 Pipeline Zones

| Zone | Technology | Bucket / Table | Retention |
|---|---|---|---|
| Landing Zone | S3 | `s3-raw-landing` | 3 years |
| Processed Zone | S3 | `s3-processed-zone` | 3 years |
| IMS Operational | Aurora PostgreSQL | `cases`, `case_history` | 3 years |
| Mini DWH | Aurora PostgreSQL | `summary_cases_daily` | Rolling |
| Attachments | S3 | `s3-attachments` | 3 years |
| Exports | S3 | `s3-exports` | 7 days (pre-signed URL) |

---

## 10. Executive Dashboard

### 10.1 Summary KPIs

- Top 5 complaint types (`ref_complaint_type`)
- Top 5 most complained agencies (`district_office`)
- Top 5 most complained provinces
- Total case count (by period)
- Case breakdown by status and by priority
- % cases closed within SLA (temp fix & permanent fix)
- Overdue count by tier (1–4)

### 10.2 Drilldown

- By province / district office / road number
- By service type and complaint type
- By source channel (LINE vs 1146 vs IMS)
- Full paginated case list with all filters from §3.3

### 10.3 Refresh Intervals

| Data | Interval |
|---|---|
| Internal (IMS) | ≤ 1 minute |
| External (LINE, 1146) | Hourly (configurable to 5 min) |
| Dashboard UI auto-refresh | Every 1 minute |

---

## 11. Export Functionality

| Format | Content | Filters |
|---|---|---|
| CSV | Raw case list (flat, UTF-8 with BOM for Thai) | Date range, status, priority, province, complaint type, channel |
| Excel (.xlsx) | Sheet 1: Case list · Sheet 2: Summary stats | Same as CSV |
| PDF | Dashboard snapshot | Date/month/year watermark on every page |

Exports generated async → stored in S3 → served via pre-signed URL (1-hour expiry). Summary statistics panel shown to user before download is triggered.

#### Excel Export — Sheet Definitions

**Sheet 1: รายการเรื่องร้องเรียน (Case List)**

| # | Column | Source Field |
|---|---|---|
| 1 | เลขที่เรื่อง | `case_id` |
| 2 | ช่องทาง | `source_channel` |
| 3 | วันที่แจ้ง | `reported_at` (date) |
| 4 | เวลาแจ้ง | `reported_at` (time) |
| 5 | สถานะ | `status` (Thai label) |
| 6 | ระดับความสำคัญ | `priority` (Thai label) |
| 7 | เรื่องที่ขอรับบริการ | `service_type_code` → label |
| 8 | เรื่องร้องเรียน | `complaint_type_code` → label |
| 9 | ชื่อผู้แจ้ง | `reporter_name` |
| 10 | เบอร์โทร/ติดต่อ | `contact_number` |
| 11 | รายละเอียด | `description` |
| 12 | จังหวัด | `province` |
| 13 | แขวงทางหลวงชนบท | `district_office` |
| 14 | หมายเลขถนน | `road_number` |
| 15 | เจ้าหน้าที่รับผิดชอบ | `assigned_officer_id` → full_name |
| 16 | วันที่ปิดเรื่อง | `closed_at` |
| 17 | เกิน SLA | `overdue_tier` (label: ปกติ / เกินชั้น 1–4) |
| 18 | หมายเหตุ | `notes` |

**Sheet 2: สรุปสถิติ (Summary)**

Pivot-style summary showing: total case count, breakdown by status, breakdown by priority, breakdown by complaint type (top 10), breakdown by province (top 10), % within SLA, overdue count by tier. Pre-formatted with conditional color coding (red = overdue, green = within SLA).

---

## 12. Notifications

### In-App (Bell Icon)

| Trigger | Recipients |
|---|---|
| Case assigned | Officer + All Admins |
| Status changed | Officer + All Admins |
| Case closed (DONE) | Officer + All Admins |
| Overdue Tier 1 (3 days) | Officer + Dispatcher + Admins |
| Overdue Tier 2 (7 days) | Officer + Dispatcher + Admins |
| Overdue Tier 3 (1 month) | All Admins |
| Overdue Tier 4 (1 year) | All Admins — budget closure decision |

External notifications (LINE API + SES email) via SQS → Lambda worker — in scope for Phase 1.

---

## 13. User & Role Management

| Role | Key Permissions |
|---|---|
| Admin | Full access; manage users/roles; reopen cases; close Tier-4 with reason code; password reset |
| Dispatcher | Review WAITING_VERIFY; assign; reject; mark duplicate |
| Officer | View cases in assigned area only; update status; edit fields |
| Executive | Dashboard read-only; export CSV/Excel/PDF |

Authentication via AWS Cognito. Admin-only password reset. No anonymous access.

---

## 14. Audit Logging

All events written to S3 (immutable). Retention ≥ 3 years. No download UI.

| Category | Events |
|---|---|
| Authentication | Login, Logout |
| Cases | Create, Update, Status change |
| Assignment | Assign, Reassign |
| Export | CSV/Excel/PDF triggered |
| Users | Create, Update, Delete, Role change |
| Admin | Password reset, Case reopen, Tier-4 closure |
| SLA | Overdue tier escalation events |

---

## 15. Security

| Requirement | Details |
|---|---|
| Transport | HTTPS; CloudFront + WAF |
| Auth | AWS Cognito; mandatory login |
| Password | Cognito defaults; Admin-only reset |
| Authorization | RBAC at API level |
| Audit | Immutable S3 log |
| Files | Pre-signed URLs with expiry |

---

## 16. Infrastructure (AWS)

| Service | Purpose |
|---|---|
| EC2 | App server |
| Aurora Serverless v2 (PostgreSQL) | IMS operational DB + Mini DWH |
| S3 | Raw/processed data, attachments, exports, audit logs |
| CloudFront + WAF | CDN + HTTPS + DDoS protection |
| ALB | HTTPS routing |
| SQS | Async notification queue |
| Lambda / EC2 Worker | Notification dispatcher |
| Cognito | Auth & user management |
| SES | Email notifications |
| LINE API | LINE OA ingestion + notifications |
| CloudWatch | Monitoring + alerts |
| Airflow (self-hosted / MWAA) | ETL orchestration |

---

## 17. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Concurrent Users | ≤ 5 (load test required before go-live) |
| Availability | Up to 1 business day acceptable downtime |
| DR | Not required this phase |
| Data Retention | ≥ 3 years all data |
| Scalability | Single-region; scale on demand |
| Cost | Aurora Serverless v2 scales to zero when idle |
| Pipeline Config | Sync frequency via config change only, no deployment |

---

## 18. External References

| Reference | Location |
|---|---|
| Figma UI Design | https://www.figma.com/proto/grM0zbn6CWdMbcDz8HilPn/DRR-WEB-DESiGN?node-id=42-27 |
| Kickoff Presentation | https://www.canva.com/design/DAHBLddpjCU/0BINGMl-xU3fFywcO6235g/edit |
| Slide Deck (Alt) | https://www.canva.com/design/DAG_-4UiN4w/BgkUZ__5E5aCvewEIOgqBw/edit |
| Data Flow & Swimlanes | Google Drive: proj-one-system / system_architecture / data-flow-and-swimlanes.md |
| Data Sample (source) | Google Drive: proj-one-system / data / data_sample.xlsx |

---

## 19. Resolved Items (Previously Open)

| # | Item | Resolution |
|---|---|---|
| 1 | 1146 API access method | **REST pull** — Airflow DAG calls 1146 REST endpoint hourly |
| 2 | LINE OA API access | **Webhook → SQS buffer** — LINE pushes events to our webhook endpoint; messages land in SQS; Airflow drains SQS hourly (configurable to 5 min). Standard LINE Messaging API pattern. |
| 3 | Complaint type additions | **None** — CT01–CT12 is final |
| 4 | Tier-4 closure reason codes | **Additional codes confirmed** — see §5.3 |
| 5 | Excel export column list | **Defined** — see §11 |
| 6 | `ผู้รับเรื่อง` mapping | **New master table required** — `ref_handler` maps handler display names to user accounts; see §8.3 |
| 7 | GPS coordinate input | **Entered by Dispatcher** — at case review stage (WAITING_VERIFY), before assignment |

---

*— End of Document — SRS v1.3*