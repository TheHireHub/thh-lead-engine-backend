# Auth Helper Functions

> 25 nodes · cohesion 0.13

## Key Concepts

- **auth.py** (12 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **AdminUser** (10 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/models.py`
- **login()** (9 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/routes.py`
- **dependencies.py** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/dependencies.py`
- **AdminUserCRUD** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/crud.py`
- **encode_jwt()** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **models.py** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/models.py`
- **decode_jwt()** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **clear_auth_cookie()** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **_cookie_secure()** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **_jwt_secret()** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **set_auth_cookie()** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **get_current_user()** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/dependencies.py`
- **FastAPI auth dependencies for admin_users (Arch-23, §6.1).  Reads the JWT from t** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/dependencies.py`
- **Dependency factory — role ints per §6.1 (0=admin, 1=growth, ... 6=viewer).** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/dependencies.py`
- **Sugar — equivalent to `Depends(get_current_user)`.** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/dependencies.py`
- **hash_password()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **_jwt_ttl_hours()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **verify_password()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **update_last_login()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/crud.py`
- **require_any_authenticated()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/dependencies.py`
- **require_role()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/dependencies.py`
- **Auth helpers for admin_users (Schema doc Arch-23, §7.1, §6.1).  DB-agnostic per** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **Return (token, max_age_seconds).** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- **Raise jwt.InvalidTokenError subclasses on failure.** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/auth.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/dependencies.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/routes.py`

## Audit Trail

- EXTRACTED: 63 (64%)
- INFERRED: 35 (36%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*