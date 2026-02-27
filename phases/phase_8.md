# Phase 8 — Export Functionality

## Goal

Implement async CSV, Excel (.xlsx), and PDF exports. Exports are generated as background jobs, stored in S3, and served via pre-signed URL (1-hour expiry). A summary statistics panel is shown to the user before download starts.

## Prerequisites

- [ ] Phase 3 complete (case data available)
- [ ] Phase 7 complete (dashboard summary endpoint for stats panel)
- [ ] `s3-exports` bucket provisioned (Phase 1 — with 7-day lifecycle expiry)
- [ ] `export-queue` SQS queue provisioned (Phase 1)

---

## 8.1 Export Architecture

```
User clicks "Export" → POST /api/v1/exports
                              │
                        [Enqueue to SQS: export-queue]
                              │
                    [Export Worker (EC2 background process)]
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          CSV file       Excel file       PDF file
              └───────────────┼───────────────┘
                              ▼
                    [Upload to s3-exports/]
                              │
                    [Update export_jobs table]
                              │
                    GET /api/v1/exports/{job_id}/status
                              │
                    On DONE: return pre-signed URL (1-hour expiry)
```

---

## 8.2 Export Job Database Table

Add to schema (Alembic migration):

```sql
export_jobs (
  id              UUID          PRIMARY KEY,
  requested_by    UUID          NOT NULL,    -- FK users
  format          VARCHAR(10)   NOT NULL,    -- CSV | EXCEL | PDF
  filters         JSONB         NOT NULL,    -- snapshot of applied filters
  status          VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
                                            -- PENDING | RUNNING | DONE | FAILED
  row_count       INT,                      -- filled when DONE
  s3_key          VARCHAR(500),             -- filled when DONE
  error_message   TEXT,                     -- filled when FAILED
  created_at      TIMESTAMP     NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMP
)
```

---

## 8.3 Export Request API

```
POST /api/v1/exports
Body:
{
  "format": "CSV" | "EXCEL" | "PDF",
  "filters": {
    "date_from": "2026-01-01",
    "date_to": "2026-02-27",
    "status": ["IN_PROGRESS", "PENDING"],
    "priority": ["CRITICAL"],
    "province": "นครสวรรค์",
    ...
  }
}

Response: 202 Accepted
{
  "job_id": "uuid",
  "status": "PENDING",
  "summary": {
    "total_cases": 342,
    "by_status": {...},
    "by_priority": {...}
  }
}
```

### Steps

1. Show summary stats **before** starting export (query with filters, no file generation yet)
2. Create `export_jobs` row with `status = PENDING`
3. Send SQS message with `job_id` and `filters`
4. Return 202 with `job_id` + pre-computed stats summary

---

## 8.4 Export Status Polling

```
GET /api/v1/exports/{job_id}/status

Response (PENDING/RUNNING):
{ "job_id": "uuid", "status": "RUNNING", "format": "EXCEL" }

Response (DONE):
{
  "job_id": "uuid",
  "status": "DONE",
  "format": "EXCEL",
  "row_count": 342,
  "download_url": "https://s3.presigned.url...",  ← 1-hour expiry
  "expires_at": "2026-02-27T11:00:00Z"
}

Response (FAILED):
{ "job_id": "uuid", "status": "FAILED", "error_message": "..." }
```

Frontend polls this endpoint every 5 seconds while status is PENDING or RUNNING.

---

## 8.5 Export Worker

A Celery worker or simple `while True` polling loop on EC2.

```python
# pipeline/workers/export_worker.py

def process_export_job(job_id: str):
    job = get_export_job(job_id)
    update_job_status(job_id, "RUNNING")

    cases = query_cases_with_filters(job.filters)  # fetch all matching rows

    if job.format == "CSV":
        content = generate_csv(cases)
        s3_key = f"exports/{job_id}/export.csv"
        content_type = "text/csv"

    elif job.format == "EXCEL":
        content = generate_excel(cases)
        s3_key = f"exports/{job_id}/export.xlsx"
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    elif job.format == "PDF":
        content = generate_pdf_dashboard(job.filters)
        s3_key = f"exports/{job_id}/dashboard.pdf"
        content_type = "application/pdf"

    s3.put_object(Bucket=EXPORTS_BUCKET, Key=s3_key, Body=content, ContentType=content_type)
    update_job_status(job_id, "DONE", s3_key=s3_key, row_count=len(cases))
```

---

## 8.6 CSV Export

**Encoding:** UTF-8 with BOM (`\ufeff`) so Excel on Windows reads Thai correctly.

```python
import csv, io

def generate_csv(cases: list[CaseRow]) -> bytes:
    output = io.StringIO()
    output.write('\ufeff')  # BOM
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for case in cases:
        writer.writerow(map_case_to_csv_row(case))
    return output.getvalue().encode("utf-8")
```

### CSV Columns (18 columns matching scope §11)

1. เลขที่เรื่อง (`case_id`)
2. ช่องทาง (`source_channel` — Thai label)
3. วันที่แจ้ง (`reported_at` date — DD-MM-YYYY BE)
4. เวลาแจ้ง (`reported_at` time — HH:MM น.)
5. สถานะ (`status` — Thai label)
6. ระดับความสำคัญ (`priority` — Thai label)
7. เรื่องที่ขอรับบริการ (`service_type_code` → label)
8. เรื่องร้องเรียน (`complaint_type_code` → label)
9. ชื่อผู้แจ้ง (`reporter_name`)
10. เบอร์โทร/ติดต่อ (`contact_number`)
11. รายละเอียด (`description`)
12. จังหวัด (`province`)
13. แขวงทางหลวงชนบท (`district_office`)
14. หมายเลขถนน (`road_number`)
15. เจ้าหน้าที่รับผิดชอบ (`assigned_officer_id` → `full_name`)
16. วันที่ปิดเรื่อง (`closed_at` — DD-MM-YYYY BE)
17. เกิน SLA (`overdue_tier` → Thai label: ปกติ / เกินชั้น 1–4)
18. หมายเหตุ (`notes`)

---

## 8.7 Excel Export (Two Sheets)

Use `openpyxl` library.

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
import io

def generate_excel(cases: list[CaseRow]) -> bytes:
    wb = Workbook()

    # Sheet 1: รายการเรื่องร้องเรียน
    ws1 = wb.active
    ws1.title = "รายการเรื่องร้องเรียน"
    write_case_list_sheet(ws1, cases)

    # Sheet 2: สรุปสถิติ
    ws2 = wb.create_sheet("สรุปสถิติ")
    write_summary_sheet(ws2, cases)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
```

### Sheet 1: Case List

- Same 18 columns as CSV
- Header row: bold, blue background, white text
- Freeze top row
- Column widths auto-fitted
- Overdue rows: red fill (`FFCCCC`)
- Within-SLA closed rows: green fill (`CCFFCC`)

### Sheet 2: สรุปสถิติ (Summary)

Pivot-style layout:

```
แถวที่ 1: จำนวนเรื่องทั้งหมด: 342
แถวที่ 3: จำแนกตามสถานะ
  สถานะ          จำนวน
  IN_PROGRESS    120
  PENDING        45
  ...
แถวที่ X: จำแนกตามระดับความสำคัญ
  ...
แถวที่ X: Top 10 เรื่องร้องเรียน
  ...
แถวที่ X: Top 10 จังหวัด
  ...
แถวที่ X: สถิติ SLA
  ปิดภายใน SLA (Temp Fix): 78.5%
  เกิน SLA ชั้น 1: 42
  ...
```

---

## 8.8 PDF Export (Dashboard Snapshot)

Use `WeasyPrint` (HTML/CSS → PDF) or `reportlab`.

**Recommended: WeasyPrint** — render the dashboard as HTML with Thai font (Sarabun), then convert to PDF.

```python
from weasyprint import HTML, CSS

def generate_pdf_dashboard(filters: dict) -> bytes:
    # Fetch dashboard summary data
    summary = fetch_dashboard_summary(filters)

    # Render HTML template with data
    html_content = render_template("pdf_dashboard.html", summary=summary, filters=filters)

    # Convert to PDF with Thai font
    css = CSS(string="""
        @font-face {
            font-family: 'Sarabun';
            src: url('/fonts/Sarabun-Regular.ttf');
        }
        body { font-family: 'Sarabun', sans-serif; }
    """)
    pdf_bytes = HTML(string=html_content).write_pdf(stylesheets=[css])
    return pdf_bytes
```

### PDF Content

- Header: ระบบงานหนึ่งระบบ — กรมทางหลวงชนบท
- Date/month/year watermark on every page (scope §11)
- Page 1: All KPI summary cards
- Page 2: Top 5 charts (as static HTML tables — no JS charts needed)
- Page 3: SLA metrics + overdue breakdown
- Footer: "สร้างโดยระบบ ณ วันที่ DD/MM/YYYY HH:MM น."

### Steps

1. Install `WeasyPrint` + `Sarabun` Thai font
2. Create `templates/pdf_dashboard.html` Jinja2 template
3. Ensure Sarabun font is bundled in the Docker image

---

## 8.9 Frontend: Export UI

### Export Modal

Triggered from:
- Case list page: "Export" button in top bar
- Dashboard page: "Export PDF" button

```
┌─────────────────────────────────────────┐
│  ส่งออกข้อมูล                             │
│                                         │
│  รูปแบบ: ○ CSV  ● Excel  ○ PDF          │
│                                         │
│  สรุปข้อมูล (ตามตัวกรองที่เลือก):         │
│  ├─ จำนวนเรื่องทั้งหมด: 342              │
│  ├─ สถานะ IN_PROGRESS: 120              │
│  └─ ...                                 │
│                                         │
│  [ยกเลิก]  [ดาวน์โหลด → สร้างไฟล์]      │
└─────────────────────────────────────────┘
```

### Loading State

After clicking download:
```
กำลังสร้างไฟล์... ⟳
(Polls /exports/{job_id}/status every 5s)
```

### Download Trigger

When status = DONE:
- Show "ดาวน์โหลด" button with pre-signed URL
- Or auto-trigger `window.open(download_url)` in new tab

---

## Testing Plan

### Unit Tests

| Test | What to verify |
| --- | --- |
| `generate_csv([])` | Empty CSV with header only, UTF-8 BOM present |
| `generate_csv(cases)` | All 18 columns present, Thai labels resolved |
| `generate_excel(cases)` | 2 sheets, header row styled, row count correct |
| BE date formatting | `reported_at` shows in DD-MM-YYYY+543 format |
| Overdue label | `overdue_tier=1` → "เกินชั้น 1" |
| `generate_pdf_dashboard(filters)` | PDF bytes, > 0 size, Thai characters present |

### Integration Tests

| Test | Method | Pass Criteria |
| --- | --- | --- |
| CSV export end-to-end | POST → poll → download | File downloaded, 18 columns, Thai text OK |
| Excel export — Thai in Excel | Open in Excel | No encoding errors, Thai readable |
| PDF export — watermark | Check PDF content | Date watermark on every page |
| Pre-signed URL expiry | Wait 61 minutes → access URL | 403 from S3 |
| Concurrent exports | Submit 3 export jobs simultaneously | All 3 complete independently |
| Large export (1,000 rows) | Export 1K cases | < 30 second generation time |
| Failed job | Kill worker mid-export | Status = FAILED, error message set |

### Deliverables

- [ ] CSV export downloads correctly with Thai characters (Excel-readable)
- [ ] Excel export has 2 sheets with correct formatting
- [ ] PDF dashboard export with Thai font and watermark
- [ ] Pre-signed URL expires after 1 hour
- [ ] s3-exports bucket lifecycle deletes files after 7 days
- [ ] Export UI shows summary stats before generating file
