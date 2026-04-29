# Auth Layer (JWT + Cookie)

> 56 nodes · cohesion 0.04

## Key Concepts

- **deps.get_current_user** (8 connections) — `services/admin_users/dependencies.py`
- **routes.login** (8 connections) — `services/admin_users/routes.py`
- **AdminUser model** (7 connections) — `services/admin_users/models.py`
- **admin_users router** (7 connections) — `services/admin_users/routes.py`
- **AuditLogCRUD.record** (6 connections) — `services/audit/crud.py`
- **AuditLog model** (5 connections) — `services/audit/models.py`
- **get_db()** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/database_connection/connection.py`
- **auth.encode_jwt** (4 connections) — `services/admin_users/auth.py`
- **routes.create_user** (4 connections) — `services/admin_users/routes.py`
- **app.py** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/app.py`
- **connection.py** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/database_connection/connection.py`
- **auth.set_auth_cookie** (3 connections) — `services/admin_users/auth.py`
- **routes.logout** (3 connections) — `services/admin_users/routes.py`
- **Arch-23 JWT httpOnly Cookie Auth** (3 connections) — `CLAUDE.md`
- **services.common.envelope.ok / fail** (3 connections) — `services/common/envelope.py`
- **_build_database_url()** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/database_connection/connection.py`
- **auth.clear_auth_cookie** (2 connections) — `services/admin_users/auth.py`
- **auth.decode_jwt** (2 connections) — `services/admin_users/auth.py`
- **auth.hash_password (bcrypt)** (2 connections) — `services/admin_users/auth.py`
- **auth.verify_password** (2 connections) — `services/admin_users/auth.py`
- **AdminUserCRUD.create** (2 connections) — `services/admin_users/crud.py`
- **AdminUserCRUD.get_by_email** (2 connections) — `services/admin_users/crud.py`
- **AdminUserCRUD.get_by_id** (2 connections) — `services/admin_users/crud.py`
- **AdminUserCRUD.soft_delete** (2 connections) — `services/admin_users/crud.py`
- **deps.require_role** (2 connections) — `services/admin_users/dependencies.py`
- *... and 31 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `/Users/lakshayjain/thh/thh-lead-engine-backend/app.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/database_connection/connection.py`
- `CLAUDE.md`
- `alembic/env.py`
- `app.py`
- `database_connection/connection.py`
- `requirements.txt`
- `services/admin_users/auth.py`
- `services/admin_users/crud.py`
- `services/admin_users/dependencies.py`
- `services/admin_users/enums.py`
- `services/admin_users/models.py`
- `services/admin_users/routes.py`
- `services/admin_users/schemas.py`
- `services/audit/crud.py`
- `services/audit/models.py`
- `services/common/enums.py`
- `services/common/envelope.py`

## Audit Trail

- EXTRACTED: 119 (87%)
- INFERRED: 18 (13%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*