# Phase 2 — Backend API Core

## Goal

Build the FastAPI application skeleton with authentication, RBAC, user management, and reference data endpoints. At the end of this phase, all four roles can authenticate via Cognito and hit protected API routes. No case logic yet.

## Prerequisites

- [ ] Phase 1 complete (Aurora running, Cognito configured, EC2 accessible)
- [ ] Python 3.12 installed
- [ ] DB credentials in Secrets Manager at `/one-system/db/credentials`

---

## 2.1 FastAPI Project Setup

```
backend/
  app/
    api/
      v1/
        auth.py         ← token validation helper
        users.py        ← user management endpoints
        reference.py    ← ref data endpoints (service types, complaint types, etc.)
        health.py       ← health check
    core/
      config.py         ← settings from env vars / Secrets Manager
      security.py       ← Cognito JWT verification
      rbac.py           ← role-based dependency
      db.py             ← SQLAlchemy async engine + session
    models/             ← SQLAlchemy ORM models (mirror of DB schema)
    schemas/            ← Pydantic request/response schemas
    main.py             ← FastAPI app factory
  requirements.txt
  Dockerfile
  docker-compose.yml    ← local dev (app + local postgres)
```

### Steps

1. Create `backend/` structure above
2. Install core dependencies:
   - `fastapi`, `uvicorn[standard]`
   - `sqlalchemy[asyncio]`, `asyncpg`
   - `alembic`
   - `pydantic-settings`
   - `python-jose[cryptography]` — JWT decode
   - `boto3` — Secrets Manager, S3, SQS
   - `httpx` — async HTTP client (for Cognito JWKS fetch)
3. Create `docker-compose.yml` for local dev (app + postgres 15)
4. Verify app starts: `uvicorn app.main:app --reload`

---

## 2.2 Configuration & Secrets

All config loaded from environment variables (or Secrets Manager on EC2).

```python
# app/core/config.py
class Settings(BaseSettings):
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str
    aws_region: str
    cognito_user_pool_id: str
    cognito_app_client_id: str
    s3_attachments_bucket: str
    s3_exports_bucket: str
    s3_audit_bucket: str
    s3_landing_bucket: str
    sqs_notification_queue_url: str
    sqs_export_queue_url: str
    environment: str = "development"
```

### Steps

1. Create `Settings` class using `pydantic-settings`
2. On EC2: load from Secrets Manager at startup; export as env vars via systemd unit
3. On local: use `.env` file (`.env` in `.gitignore`)

---

## 2.3 Database Connection

Async SQLAlchemy session with connection pooling.

```python
# app/core/db.py
engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=2)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

### Steps

1. Create async engine using `asyncpg` driver
2. Create `get_db` dependency (FastAPI `Depends`)
3. Test connection on startup (`@app.on_event("startup")`)

---

## 2.4 Cognito JWT Authentication

Verify JWTs issued by Cognito without calling the Cognito endpoint on every request.

### Flow

1. Client logs in via Cognito Hosted UI or direct `InitiateAuth` call → receives `id_token` + `access_token`
2. Client sends `Authorization: Bearer <access_token>` on all API calls
3. Backend fetches Cognito JWKS (cached, refreshed every 24h) and verifies signature + expiry

```python
# app/core/security.py
async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    payload = verify_cognito_jwt(token)  # raises 401 if invalid
    user = await get_user_by_cognito_id(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401)
    return user
```

### Steps

1. Implement JWKS fetch + cache in `security.py`
2. Decode and verify JWT claims: `iss`, `aud`, `exp`, `token_use = access`
3. Extract `sub` (Cognito user ID) → look up in `users` table
4. Create `get_current_user` FastAPI dependency
5. Create `require_role(*roles)` dependency factory for RBAC

---

## 2.5 SQLAlchemy ORM Models

Mirror the full DB schema from scope §8 as ORM models.

### Steps

1. Create `app/models/` with one file per table group:
   - `user.py` — `User`
   - `case.py` — `Case`, `CaseHistory`, `CaseAttachment`
   - `reference.py` — `RefServiceType`, `RefComplaintType`, `RefHandler`, `RefClosureReason`
   - `notification.py` — `Notification`
   - `sequence.py` — `CaseSequence`
   - `sla.py` — `SlaConfig`
   - `summary.py` — `SummaryCasesDaily`
2. All models inherit from `Base = DeclarativeBase()`
3. Add `__tablename__`, column definitions with correct types and constraints

---

## 2.6 Health Check Endpoint

```
GET /health → 200 {"status": "ok", "db": "ok"}
```

### Steps

1. Create `app/api/v1/health.py`
2. Run a `SELECT 1` against the DB to verify connectivity
3. Return DB status in response body
4. Register at `/health` (no auth required — used by ALB)

---

## 2.7 User Management API

All user management requires `ADMIN` role.

### Endpoints

```
POST   /api/v1/users                    ← create user (Admin only)
GET    /api/v1/users                    ← list users with pagination
GET    /api/v1/users/{user_id}          ← get single user
PUT    /api/v1/users/{user_id}          ← update user (name, role, province, active)
POST   /api/v1/users/{user_id}/reset-password ← trigger Cognito password reset
GET    /api/v1/users/me                 ← get own profile (any authenticated role)
```

### Create User Flow

1. Admin submits name, email, role, responsible_province (for officers)
2. API calls `cognito-idp:AdminCreateUser` → Cognito sends temporary password email
3. API inserts row into `users` table with `cognito_user_id = sub` from Cognito response
4. API adds user to Cognito group matching their role

### Pydantic Schemas

```python
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    role: Literal["ADMIN", "DISPATCHER", "OFFICER", "EXECUTIVE"]
    responsible_province: str | None = None

class UserResponse(BaseModel):
    id: UUID
    full_name: str
    email: str | None
    role: str
    responsible_province: str | None
    is_active: bool
    created_at: datetime
```

### Steps

1. Implement all endpoints in `app/api/v1/users.py`
2. Password reset calls `AdminResetUserPassword` in Cognito
3. Deactivating a user (`is_active = False`) also calls `AdminDisableUser` in Cognito

---

## 2.8 Reference Data API

Read-only endpoints for frontend dropdowns. Cached in memory (TTL 5 min).

```
GET /api/v1/reference/service-types
GET /api/v1/reference/complaint-types
GET /api/v1/reference/provinces          ← distinct provinces from cases table
GET /api/v1/reference/sla-config         ← Admin only
```

### Steps

1. Create `app/api/v1/reference.py`
2. Use `functools.lru_cache` or `cachetools.TTLCache` for reference data (rarely changes)
3. `/provinces` queries `SELECT DISTINCT province FROM cases` — no cache needed

---

## 2.9 Deployment to EC2

### Steps

1. Write `Dockerfile` — multi-stage build, non-root user
2. Write `docker-compose.prod.yml` — app container + Nginx reverse proxy
3. Create systemd service file for Docker Compose
4. Create deployment script `scripts/deploy_backend.sh`:
   - Pull image from ECR (or copy and build on server)
   - Run `alembic upgrade head`
   - Restart Docker Compose service
5. Configure Nginx to proxy `/api/*` → uvicorn on port 8000

---

## Testing Plan

### Unit Tests

| Test | File | What to verify |
| --- | --- | --- |
| JWT validation — valid token | `tests/test_security.py` | Returns user object |
| JWT validation — expired token | `tests/test_security.py` | Raises 401 |
| JWT validation — wrong issuer | `tests/test_security.py` | Raises 401 |
| RBAC: ADMIN can access user list | `tests/test_users.py` | 200 returned |
| RBAC: OFFICER cannot access user list | `tests/test_users.py` | 403 returned |
| Create user — valid payload | `tests/test_users.py` | User in DB + Cognito |
| Create user — duplicate email | `tests/test_users.py` | 409 Conflict |
| Deactivate user | `tests/test_users.py` | `is_active = False` in DB |

### Integration Tests

| Test | Method | Pass Criteria |
| --- | --- | --- |
| `GET /health` | `curl` from ALB | 200 `{"status":"ok","db":"ok"}` |
| Auth flow end-to-end | Login via Cognito → call protected endpoint | 200 |
| Unauthenticated request | Call protected endpoint without token | 401 |
| Reference data endpoints | `GET /reference/service-types` | 12 items returned |

### Deliverables

- [ ] FastAPI app running on EC2 behind ALB
- [ ] JWT auth working with real Cognito tokens
- [ ] User CRUD operational
- [ ] `GET /health` passing ALB health check
- [ ] All tests passing (`pytest backend/tests/`)
