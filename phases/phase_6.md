# Phase 6 — Notification System

## Goal

Implement in-app bell notifications, SQS-based async dispatch, email (SES), and LINE message notifications. At the end of this phase, users receive real-time in-app alerts and outbound messages for all workflow events.

## Prerequisites

- [ ] **UI-04** LINE Channel Access Token (for outbound notifications)
- [ ] **UI-09** SES sender email verified in AWS SES
- [ ] Phase 3 complete (case transitions trigger SQS messages)
- [ ] Phase 4 complete (frontend notification bell shell in place)
- [ ] `notification-queue` SQS queue provisioned (Phase 1)

---

## 6.1 Notification Event Model

Every notification event is a JSON message on `notification-queue`:

```json
{
  "event_type": "CASE_ASSIGNED",
  "case_id": "RRD-2568-000042",
  "triggered_by_user_id": "uuid",
  "target_user_ids": ["uuid1", "uuid2"],
  "metadata": {
    "officer_name": "สมชาย ใจดี",
    "status": "IN_PROGRESS"
  },
  "timestamp": "2026-02-27T10:00:00Z"
}
```

### Event Types

| Event Type | In-App | Email | LINE Message |
| --- | --- | --- | --- |
| `CASE_ASSIGNED` | ✓ | ✓ | ✓ |
| `STATUS_CHANGED` | ✓ | ✓ | — |
| `CASE_CLOSED` | ✓ | ✓ | — |
| `OVERDUE_TIER_1` | ✓ | ✓ | — |
| `OVERDUE_TIER_2` | ✓ | ✓ | — |
| `OVERDUE_TIER_3` | ✓ | — | — |
| `OVERDUE_TIER_4` | ✓ | ✓ | — |

---

## 6.2 Notification Producer (API Side)

After each case transition, the FastAPI route enqueues a notification event to SQS.

```python
# app/services/notification_service.py
async def emit_notification(
    event_type: str,
    case_id: str,
    triggered_by: UUID,
    target_user_ids: list[UUID],
    metadata: dict,
) -> None:
    message = {
        "event_type": event_type,
        "case_id": case_id,
        "triggered_by_user_id": str(triggered_by),
        "target_user_ids": [str(uid) for uid in target_user_ids],
        "metadata": metadata,
        "timestamp": datetime.utcnow().isoformat(),
    }
    sqs.send_message(
        QueueUrl=settings.sqs_notification_queue_url,
        MessageBody=json.dumps(message),
    )
```

### Target Resolution

```python
def resolve_targets(event_type: str, case: Case, all_admins: list[User]) -> list[UUID]:
    targets = set(all_admins_ids)
    if event_type in ("CASE_ASSIGNED", "STATUS_CHANGED", "CASE_CLOSED"):
        if case.assigned_officer_id:
            targets.add(case.assigned_officer_id)
    if event_type in ("OVERDUE_TIER_1", "OVERDUE_TIER_2"):
        targets.add(case.assigned_officer_id)
        # add dispatchers
    return list(targets)
```

### Trigger Points

Add `emit_notification()` calls after these operations in Phase 3:

| Trigger | Event Type |
| --- | --- |
| `WAITING_VERIFY → IN_PROGRESS` | `CASE_ASSIGNED` |
| Any status change | `STATUS_CHANGED` |
| `→ DONE` or `→ CLOSE` | `CASE_CLOSED` |
| ETL overdue tier escalation | `OVERDUE_TIER_1/2/3/4` |

---

## 6.3 Notification Worker (Lambda or EC2 Worker)

A worker polls `notification-queue` and dispatches to all channels.

**Options:** Lambda (triggered by SQS event source mapping) OR long-running process on EC2. Lambda is recommended for decoupled scaling.

### Lambda Handler

```python
def handler(event, context):
    for record in event["Records"]:
        msg = json.loads(record["body"])
        event_type = msg["event_type"]

        # 1. Write in-app notifications to DB
        write_in_app_notifications(msg)

        # 2. Send email via SES (if applicable for this event type)
        if event_type in EMAIL_EVENTS:
            send_ses_email(msg)

        # 3. Send LINE message (if CASE_ASSIGNED and reporter has LINE ID)
        if event_type == "CASE_ASSIGNED":
            send_line_message(msg)
```

### Steps

1. Create `pipeline/lambda/notification_worker/handler.py`
2. Configure SQS event source mapping for Lambda (batch size = 10)
3. Package with `requirements.txt` and deploy via CDK `lambda.Function`
4. IAM: Lambda role needs SES:SendEmail, SQS:ReceiveMessage/DeleteMessage, RDS access (via Secrets Manager)

---

## 6.4 In-App Notifications (DB + API)

### Write to DB

For each target user, insert a `notifications` row:

```python
async def write_in_app_notifications(msg: dict, db: AsyncSession):
    case_id = msg["case_id"]
    for user_id in msg["target_user_ids"]:
        notification = Notification(
            user_id=UUID(user_id),
            case_id=case_id,
            type=msg["event_type"],
            message=build_message(msg["event_type"], msg["metadata"]),
        )
        db.add(notification)
    await db.commit()
```

### API Endpoints

```
GET  /api/v1/notifications              ← unread notifications for current user
POST /api/v1/notifications/mark-read    ← mark list of IDs as read
     Body: { "ids": ["uuid1", "uuid2"] } or { "all": true }
GET  /api/v1/notifications/count        ← unread count (for bell badge)
```

### Frontend Polling

Frontend polls `GET /api/v1/notifications/count` every 60 seconds to update the bell badge. On click, fetch `GET /api/v1/notifications` and render dropdown.

> Note: WebSocket upgrade is a future enhancement. Polling at 60s is sufficient for ≤5 concurrent users.

### Message Templates

```python
MESSAGE_TEMPLATES = {
    "CASE_ASSIGNED": "เรื่อง {case_id} ถูกมอบหมายให้ {officer_name}",
    "STATUS_CHANGED": "เรื่อง {case_id} เปลี่ยนสถานะเป็น {status}",
    "CASE_CLOSED": "เรื่อง {case_id} ปิดแล้ว",
    "OVERDUE_TIER_1": "เรื่อง {case_id} เกิน SLA ระดับ 1 (3 วัน)",
    "OVERDUE_TIER_2": "เรื่อง {case_id} เกิน SLA ระดับ 2 (7 วัน)",
    "OVERDUE_TIER_3": "เรื่อง {case_id} เกิน SLA ระดับ 3 (1 เดือน)",
    "OVERDUE_TIER_4": "เรื่อง {case_id} เกิน SLA ระดับ 4 (1 ปี) — ต้องการการตัดสินใจงบประมาณ",
}
```

---

## 6.5 Email Notifications (SES)

### Setup

1. Verify sender email (`UI-09`) in SES console
2. If account is in SES sandbox: verify all recipient emails too (or request production access)
3. Store sender email in `Settings.ses_sender_email`

### Implementation

```python
import boto3

ses = boto3.client("ses", region_name=settings.aws_region)

def send_ses_email(msg: dict, recipient_emails: list[str]):
    subject = EMAIL_SUBJECTS[msg["event_type"]]
    body = build_email_body(msg)
    ses.send_email(
        Source=settings.ses_sender_email,
        Destination={"ToAddresses": recipient_emails},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Html": {"Data": body, "Charset": "UTF-8"}},
        },
    )
```

### Steps

1. Create email HTML templates (Thai language) for each event type
2. Fetch recipient emails from `users` table using `target_user_ids`
3. Handle SES throttling (max 14 emails/sec on sandbox, 200/sec production)

---

## 6.6 LINE Message Notifications

For `CASE_ASSIGNED` events only: notify the original reporter via LINE if they have a `line_user_id`.

### Implementation

```python
import httpx

async def send_line_message(case_id: str, line_user_id: str, officer_name: str):
    message = f"เรื่องร้องเรียน {case_id} ของท่านได้รับการดำเนินการแล้ว โดย {officer_name}"
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
            json={
                "to": line_user_id,
                "messages": [{"type": "text", "text": message}],
            },
        )
```

### Steps

1. Fetch `line_user_id` from `cases` table using `case_id`
2. Only send if `line_user_id IS NOT NULL` and `source_channel = LINE`
3. Store `LINE_CHANNEL_ACCESS_TOKEN` in Secrets Manager

---

## 6.7 Frontend: Notification Bell

Complete the notification UI shell from Phase 4.

### Components

```
<NotificationBell>
  - Badge showing unread count
  - On click → <NotificationDropdown>
      - Scrollable list of recent notifications
      - Each item: icon, message text, case_id link, timestamp (relative: "5 นาทีที่แล้ว")
      - "Mark all as read" button
      - "See all" link
```

### Steps

1. Implement polling hook: `useNotificationCount()` — polls every 60s
2. Implement `useNotifications()` hook — fetches on bell click
3. Auto-mark as read when dropdown closes
4. Navigate to `/cases/:caseId` when user clicks a notification

---

## Testing Plan

### Unit Tests

| Test | What to verify |
| --- | --- |
| `build_message("CASE_ASSIGNED", {...})` | Correct Thai message string |
| `resolve_targets("OVERDUE_TIER_1", ...)` | Officer + Admins in target list |
| LINE signature — outbound message format | Valid LINE API payload structure |
| SQS message format | Valid JSON, all required fields present |

### Integration Tests

| Test | Method | Pass Criteria |
| --- | --- | --- |
| In-app notification created | Assign case → check `notifications` table | Row for each target user |
| Unread count API | Create notification → `GET /notifications/count` | Count = 1 |
| Mark as read | `POST /notifications/mark-read` | `is_read = TRUE` in DB |
| SES email (sandbox) | Trigger `CASE_ASSIGNED` event | Email received at verified address |
| LINE push message | Trigger with known LINE User ID | Message visible in LINE chat |
| Lambda DLQ | Force lambda error (bad DB creds) | Message lands in `notification-dlq` after 3 retries |
| Overdue tier notification | ETL sets `overdue_tier = 1` → run notification trigger | Notification row created for officer + admins |

### Deliverables

- [ ] In-app bell working with real notifications
- [ ] SES email delivered for all applicable event types
- [ ] LINE push message working for CASE_ASSIGNED
- [ ] Unread count polling every 60s
- [ ] DLQ alarm configured in CloudWatch
