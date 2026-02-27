# Phase 7 — Executive Dashboard

## Goal

Build the Executive Dashboard with all KPIs from scope §10, powered by the `summary_cases_daily` mini data warehouse. Dashboard auto-refreshes every 1 minute.

## Prerequisites

- [ ] Phase 5 complete (`summary_cases_daily` populated by ETL)
- [ ] Phase 4 complete (frontend routing in place)
- [ ] At least one day of ETL data ingested (or seeded test data)

---

## 7.1 Dashboard API Endpoints

All dashboard endpoints read from `summary_cases_daily` (fast, pre-aggregated). Internal IMS metrics (< 1 min lag) may additionally query `cases` directly.

```
GET /api/v1/dashboard/summary
    ?period=today|week|month|year|custom
    &date_from=YYYY-MM-DD
    &date_to=YYYY-MM-DD
    &province=<str>
    &source_channel=<str>
```

### Response Structure

```json
{
  "period": { "from": "2026-02-01", "to": "2026-02-27" },
  "total_cases": 4080,
  "by_status": {
    "WAITING_VERIFY": 120,
    "IN_PROGRESS": 850,
    "FOLLOWING_UP": 210,
    "PENDING": 95,
    "DONE": 2650,
    "CLOSE": 100,
    "REJECTED": 35,
    "CANCELLED": 20
  },
  "by_priority": {
    "CRITICAL": 45,
    "HIGH": 320,
    "MEDIUM": 2100,
    "LOW": 1615
  },
  "by_source_channel": {
    "CALL_1146": 2942,
    "LINE": 1138
  },
  "top5_complaint_types": [
    { "code": "CT02", "label": "ถนนชำรุด", "count": 1240 },
    ...
  ],
  "top5_provinces": [
    { "province": "นครสวรรค์", "count": 320 },
    ...
  ],
  "top5_district_offices": [
    { "district_office": "แขวงทางหลวงชนบทนครสวรรค์", "count": 180 },
    ...
  ],
  "overdue_by_tier": {
    "tier_1": 42,
    "tier_2": 18,
    "tier_3": 5,
    "tier_4": 1
  },
  "sla_metrics": {
    "temp_fix_within_sla_pct": 78.5,
    "permanent_fix_within_sla_pct": 65.2,
    "tier4_closures": 1
  },
  "generated_at": "2026-02-27T10:00:00Z"
}
```

### Additional Endpoints

```
GET /api/v1/dashboard/trend
    ?metric=case_count|overdue_count|closed_within_sla
    &granularity=day|week|month
    &period=month|quarter|year

GET /api/v1/dashboard/cases
    (same as /cases endpoint — used for drilldown)
```

### Steps

1. Create `app/api/v1/dashboard.py`
2. All reads from `summary_cases_daily` aggregated by SELECT + GROUP BY
3. For period = `today` or near-real-time metrics: query `cases` table directly
4. Role restriction: `EXECUTIVE` and `ADMIN` only

---

## 7.2 Dashboard Page Layout

**Route:** `/dashboard`
**Access:** EXECUTIVE + ADMIN

```
┌──────────────────────────────────────────────────────────┐
│  Period selector: Today | This Week | This Month | Custom │
│  Filters: Province | Source Channel                       │
│  [Auto-refresh: ON] Last updated: 10:00:05                │
├────────────────────┬─────────────────────────────────────┤
│  Total Cases       │  By Status (bar or pie chart)        │
│  [4,080]           │                                      │
├────────────────────┴─────────────────────────────────────┤
│  By Priority (donut chart)  │  By Source Channel (donut) │
├─────────────────────────────┴──────────────────────────  │
│  Top 5 Complaint Types (horizontal bar)                   │
├──────────────────────────────────────────────────────────┤
│  Top 5 Provinces (horizontal bar)                        │
├──────────────────────────────────────────────────────────┤
│  Top 5 District Offices (horizontal bar)                 │
├──────────────────────────────────────────────────────────┤
│  SLA Metrics                                              │
│  Temp Fix Within SLA: 78.5%  |  Overdue Tier 1: 42       │
│  Perm Fix Within SLA: 65.2%  |  Overdue Tier 2: 18       │
│                              |  Overdue Tier 3: 5         │
│                              |  Overdue Tier 4: 1 ⚠️      │
├──────────────────────────────────────────────────────────┤
│  Case Trend (line chart — cases over time)               │
└──────────────────────────────────────────────────────────┘
```

### Steps

1. Create `src/pages/dashboard/DashboardPage.tsx`
2. Chart library: `recharts` (lightweight, React-native) or `Chart.js` via `react-chartjs-2`
3. Install: `npm install recharts`
4. Auto-refresh: use `setInterval(refetch, 60_000)` inside `useQuery`'s `refetchInterval` option
5. Period selector updates query params and re-fetches all dashboard queries
6. Show "Last updated" timestamp from API response `generated_at`

---

## 7.3 KPI Cards

Each KPI card is a standalone component that can be clicked to drilldown to the case list.

```tsx
// src/components/dashboard/KpiCard.tsx
interface KpiCardProps {
  label: string
  value: number | string
  subLabel?: string
  color?: "default" | "warning" | "danger"
  onClick?: () => void  // navigate to /cases with pre-filters
}
```

### Drilldown Behavior

Clicking a KPI card navigates to `/cases?<pre-filled-filters>`:
- "Overdue Tier 1" card → `/cases?overdue_tier=1`
- "CRITICAL priority" → `/cases?priority=CRITICAL`
- "Top complaint type CT02" → `/cases?complaint_type_code=CT02`

---

## 7.4 Chart Components

### BarChart: Top 5 Complaint Types / Provinces / District Offices

```tsx
// src/components/dashboard/TopFiveChart.tsx
// Horizontal bar chart
// Color scale from green (low) to red (high)
// Labels in Thai from ref_complaint_type / province
// Click bar → drilldown to /cases
```

### DonutChart: Status / Priority / Source Channel

```tsx
// src/components/dashboard/DonutChart.tsx
// Status colors match the badge colors from Phase 4
// Show legend + total in center
```

### LineChart: Case Trend Over Time

```tsx
// src/components/dashboard/TrendChart.tsx
// X-axis: date
// Y-axis: case_count
// Toggle: total / by_status / by_source
```

### SLA Progress Bars

```tsx
// src/components/dashboard/SlaMetrics.tsx
// Progress bar: Temp Fix SLA %
// Progress bar: Permanent Fix SLA %
// Overdue tier count table (Tier 1–4 with visual severity)
// Tier 4 count in RED with warning if > 0
```

---

## 7.5 Overdue Tier 4 Alert Banner

If `overdue_by_tier.tier_4 > 0`, show a sticky red banner at top of dashboard:

```
⚠️ มีเรื่องร้องเรียน {N} เรื่อง อยู่ในระดับเกิน SLA ชั้น 4 (เกิน 1 ปี) — กรุณาดำเนินการ
[ดูรายละเอียด]  →  navigates to /cases?overdue_tier=4
```

---

## 7.6 Export Button on Dashboard

Add "Export PDF" button to dashboard (triggers Phase 8 async PDF export).

```
[Export PDF ▼]
  → Export CSV
  → Export Excel
  → Export PDF (Dashboard Snapshot)
```

Links to Phase 8 implementation.

---

## Testing Plan

### Unit Tests

| Test | What to verify |
| --- | --- |
| `GET /dashboard/summary` — empty DB | Returns zeros, no 500 error |
| Period filter: `period=today` | `date_from = date_to = today` |
| Period filter: `period=month` | Correct date range for current month |
| Role guard: OFFICER cannot access | 403 returned |
| Drilldown link generation | Correct query params for each KPI |

### Visual / Integration Tests

| Test | Method | Pass Criteria |
| --- | --- | --- |
| Dashboard loads with data | Seed `summary_cases_daily` → load page | All charts render, no blank panels |
| Auto-refresh | Wait 60s | `generated_at` timestamp updates |
| Tier 4 banner | Seed 1 Tier-4 case | Red banner visible |
| Drilldown click | Click "Overdue Tier 1" card | Navigates to `/cases?overdue_tier=1` |
| Province filter | Select province → dashboard updates | All charts filtered to that province |
| Chart tooltip | Hover bar in chart | Tooltip shows count + label |

### Performance Test

| Metric | Target |
| --- | --- |
| Dashboard API response time | < 500ms with 3 months of data |
| Frontend paint time | < 2s (LCP) |

### Deliverables

- [ ] Dashboard accessible to EXECUTIVE and ADMIN roles
- [ ] All 7 KPI sections rendered
- [ ] Auto-refresh every 60s
- [ ] Drilldown to case list from every chart
- [ ] Tier-4 alert banner visible when applicable
- [ ] Export button wired to Phase 8
