# Phase 4 — IMS Frontend (Case Management)

## Goal

Build the React web application covering authentication, the case list, case detail, case create/edit, status transitions, assignment, and file attachments. Matches the Figma design at scope §18.

## Prerequisites

- [ ] Phase 3 complete (all case APIs working)
- [ ] Figma design accessible (link in scope §18)
- [ ] Cognito App Client ID available

---

## 4.1 Frontend Project Setup

```
frontend/
  src/
    api/           ← axios/fetch wrappers per resource
    components/    ← shared UI components
    pages/         ← route-level pages
      auth/        ← login, redirect
      cases/       ← list, detail, create
      dashboard/   ← (Phase 7)
      admin/       ← (Phase 9)
    hooks/         ← custom React hooks
    stores/        ← Zustand global state
    utils/         ← date formatting, SLA helpers
    types/         ← TypeScript interfaces matching API schemas
  index.html
  vite.config.ts
  tailwind.config.ts
```

### Steps

1. Bootstrap: `npm create vite@latest frontend -- --template react-ts`
2. Install dependencies:
   - `react-router-dom` — routing
   - `@tanstack/react-query` — server state + cache
   - `axios` — HTTP client
   - `zustand` — auth/global state
   - `tailwindcss` + `@headlessui/react` — styling
   - `react-hook-form` + `zod` — form validation
   - `dayjs` — date formatting (Buddhist Era support)
   - `amazon-cognito-identity-js` — Cognito auth
   - `react-hot-toast` — notifications
   - `@tanstack/react-table` — table with sort/filter
3. Configure Vite proxy: `/api → http://ALB_URL` in dev

---

## 4.2 Authentication Flow

### Cognito Integration (Custom UI — no Hosted UI)

1. User lands on `/login` → email + password form
2. Submit calls `CognitoUserPool.authenticateUser()` → returns tokens
3. Tokens stored in memory (`zustand`) + refresh token in `httpOnly` cookie (via backend `/auth/session` endpoint)
4. Axios interceptor attaches `Authorization: Bearer <access_token>` to every request
5. On 401 → auto-refresh using refresh token; if refresh fails → redirect to `/login`
6. First login (temp password) → redirect to `/change-password` screen

### Steps

1. Create `src/stores/authStore.ts` — user, tokens, login/logout actions
2. Create `src/pages/auth/LoginPage.tsx`
3. Create `src/pages/auth/ChangePasswordPage.tsx` (NEW_PASSWORD_REQUIRED challenge)
4. Create `ProtectedRoute` component — redirects unauthenticated users to `/login`
5. Add role-based redirect: EXECUTIVE → `/dashboard`, others → `/cases`

---

## 4.3 Case List Page

**Route:** `/cases`

### Layout

- Top bar: filters (collapsible panel) + search input + "New Case" button (Dispatcher/Admin only)
- Table columns: Case ID | Status | Priority | Reported At | Province | District | Assigned Officer | Overdue Tier | Actions
- Pagination: page size selector (20/50/100), prev/next
- Status badge colors: `WAITING_VERIFY`=yellow, `IN_PROGRESS`=blue, `DONE`=green, `PENDING`=orange, `DUPLICATE`=gray, etc.
- Overdue tier badge: Tier 1=yellow, 2=orange, 3=red, 4=dark red

### Filters Panel

All filters from scope §3.3:
- Date range picker (reported_at)
- Multi-select: status, priority, source channel, service type, complaint type
- Text: province, district office, road number, case ID, keyword
- Dropdown: assigned officer (users list)
- Number: overdue tier

### Steps

1. Create `src/pages/cases/CaseListPage.tsx`
2. Use `@tanstack/react-query` `useQuery` for `/api/v1/cases` with filter params
3. Use `@tanstack/react-table` for sortable, paginated table
4. Filters stored in URL query params (shareable links)
5. Officer role: province filter pre-filled + locked to `user.responsible_province`

---

## 4.4 Case Detail Page

**Route:** `/cases/:caseId`

### Sections

1. **Header**: Case ID, status badge, priority badge, source channel, created date
2. **Case Info**: all fields from scope §3.1, editable based on role + status
3. **GPS Map**: show pin if `gps_lat/gps_lng` set (use Leaflet.js or Google Maps embed)
4. **Attachments**: image gallery, upload button (if editable), 20-image limit indicator
5. **Assignment**: current officer, reassign button (Dispatcher/Admin)
6. **Status Actions**: action buttons based on current status + role (see §4.5)
7. **History Timeline**: all `case_history` entries in chronological order

### Steps

1. Create `src/pages/cases/CaseDetailPage.tsx`
2. Inline editing: fields become inputs on click (or "Edit" button mode)
3. Auto-save debounce: 1s after last keystroke → `PUT /api/v1/cases/:id`
4. Attach `react-query` `invalidateQueries` after any mutation to refresh data

---

## 4.5 Status Action Buttons

Rendered contextually based on `(current_status, user_role)`:

| Current Status | Role | Available Actions |
| --- | --- | --- |
| WAITING_VERIFY | Dispatcher / Admin | Assign → IN_PROGRESS, Reject, Cancel, Mark Duplicate |
| IN_PROGRESS | Officer / Admin | Follow-up, Set Pending, Mark Done |
| FOLLOWING_UP | Officer / Admin | Resume (→ IN_PROGRESS), Mark Done |
| PENDING | Officer / Admin | Resume (→ IN_PROGRESS), Mark Done |
| DONE | Admin only | Reopen (→ WAITING_VERIFY), Final Close (→ CLOSE) |

Each action opens a **modal dialog** with:
- Confirmation message
- Required fields (e.g., assign officer dropdown, expected date picker, duplicate case ID input)
- Submit → `POST /api/v1/cases/:id/transition`

---

## 4.6 Case Create Form

**Route:** `/cases/new`

**Access:** Dispatcher + Admin only

### Form Fields

1. Service Type (dropdown) — dynamic: complaint-type fields appear only when = 6
2. Priority (radio/select)
3. Reporter Name (optional)
4. Contact Number (optional)
5. Description (textarea, required)
6. Province / District Office / Road Number (show only when service_type = 6)
7. Notes (optional)

### Steps

1. Create `src/pages/cases/CaseCreatePage.tsx`
2. Use `react-hook-form` + `zod` for schema validation matching API rules
3. On submit: `POST /api/v1/cases` → redirect to `/cases/:newId`

---

## 4.7 Attachment Upload

### Upload Flow

1. File input (accept `image/*`, max 1MB per file, max 20 total)
2. Client-side size check before upload
3. Show progress spinner per file
4. On success: refresh attachment gallery

### Download

Click thumbnail → open pre-signed URL in new tab (call `GET /attachments/:id/url` first)

### Steps

1. Create `src/components/AttachmentGallery.tsx`
2. Validate file count + size client-side before posting
3. Use `FormData` + axios for multipart upload

---

## 4.8 Notification Bell (UI Shell)

Render the notification bell icon in the top nav. Actual notification data is Phase 6 — for now, show the bell with badge count = 0 as a placeholder.

---

## 4.9 Thai Language & Date Formatting

All dates displayed in Buddhist Era format:

```typescript
// src/utils/date.ts
import dayjs from 'dayjs'
import buddhistEra from 'dayjs/plugin/buddhistEra'
dayjs.extend(buddhistEra)

export const formatThaiDate = (d: string | Date) =>
  dayjs(d).format('DD-MM-BBBB HH:mm น.')  // e.g. 15-02-2568 09.30 น.
```

All Thai-language labels use the canonical values from `ref_service_type` and `ref_complaint_type` fetched from the API.

---

## 4.10 Static File Deployment

React build output (`dist/`) served via S3 + CloudFront.

### Steps

1. Add `vite.config.ts` base URL config for CloudFront path
2. Create `scripts/deploy_frontend.sh`:
   - `npm run build`
   - `aws s3 sync dist/ s3://FRONTEND_BUCKET/ --delete`
   - `aws cloudfront create-invalidation --distribution-id ID --paths "/*"`
3. Configure CloudFront to serve `index.html` for 404s (SPA routing)

---

## Testing Plan

### Component Tests (Vitest + Testing Library)

| Test | What to verify |
| --- | --- |
| Login form — empty submit | Validation errors shown |
| Login form — wrong password | Error message displayed |
| CaseList — renders table | Columns visible, data from mock API |
| CaseList — filter apply | URL params update, API called with params |
| CaseDetail — status actions for each role | Correct buttons shown per role |
| Status transition modal — required fields | Cannot submit without required fields |
| Case create — service_type ≠ 6 | Location fields hidden |
| Case create — service_type = 6 | Location fields shown and required |
| Attachment upload — >1MB file | Error shown, file not uploaded |
| Attachment upload — 21st file | Error shown |
| Thai date format | `formatThaiDate()` returns correct BE string |

### E2E Tests (Playwright)

| Scenario | Steps | Pass Criteria |
| --- | --- | --- |
| Dispatcher full workflow | Login → Create case → Assign officer → Verify status IN_PROGRESS | All steps complete, DB updated |
| Officer views only own cases | Login as Officer → Case list | Only own province/assigned cases visible |
| File upload | Open case → Upload image → See thumbnail | Image in gallery, S3 key in DB |
| Admin reopen | Login as Admin → DONE case → Reopen | Status = WAITING_VERIFY |

### Deliverables

- [ ] Login, case list, case detail, case create all working in production
- [ ] Role-based UI logic verified for all 4 roles
- [ ] Thai date formatting throughout
- [ ] Responsive layout (desktop-first, min 1280px)
- [ ] All Vitest + Playwright tests passing
