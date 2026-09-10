# Authentication

Turning on `auth.enabled: true` auto-injects a reserved `User` entity and generates a full JWT
auth module (`modules/<auth_module_name>/` — `service.py`, `routes.py`, `schemas.py`,
`email.py`), verified here against the live templates: `app/templates/Python/auth/service.py.jinja`
and `app/templates/Python/auth/routes.py.jinja`. For the exact YAML shape (`auth.jwt.*`,
`auth.registration.*`, every field's type/default), see the
[Full field reference → `auth`](../erd-reference/fields.md#auth-authspec) — this page covers what
the generated code *does*, not the field list.

## Registration modes

`auth.registration.mode` is one of three mutually exclusive values, enforced in
`AuthService.authenticate_user` (the single enforcement point every mode's checks run through, in
this order — `service.py.jinja` lines 125–142):

1. `is_active` — checked unconditionally, regardless of mode.
2. `is_verified` — only when `mode: email_verification`.
3. `is_approved` — only when `mode: admin_approval`.

| Mode | What it gates | What `register_user` does |
|---|---|---|
| `open` (default) | Nothing beyond `is_active`. A new user can log in immediately. | Creates the user with `is_active=True`; no token generated. |
| `email_verification` | Login raises `ValueError("Email not verified")` until `is_verified` is set. | Also generates an email-verification token via `create_email_verification_token` and sends it through the dev-mode `send_email()` stub. `POST /auth/verify-email` sets `is_verified=True`. `POST /auth/resend-verification` re-sends, and is **not** auth-gated (an unverified user has no bearer token to authenticate with). |
| `admin_approval` | Login raises `ValueError("Account pending approval")` until `is_approved` is set. Requires `rbac.enabled: true` (the approve endpoint is `admin`-gated). | See bootstrap-admin behavior below. `POST /users/{id}/approve` sets `is_approved=True`. |

Since the modes are mutually exclusive, at most one of the latter two checks is ever compiled
into a given generated project — there's no code path where both exist.

## Password reset: single-use tokens without a token table

`POST /auth/forgot-password` always returns the same generic message whether or not the email
exists (enumeration-safe). If it exists, `AuthService.create_password_reset_token(user_id,
password_hash)` is called and mailed via the dev-mode stub.

Reading `create_password_reset_token` and `verify_password_reset_token` directly
(`service.py.jinja` lines 67–74 and 181–204) confirms the mechanism actually shipped:

```python
def create_password_reset_token(self, user_id: int, password_hash: str) -> str:
    pwd_fp = hashlib.sha256(password_hash.encode()).hexdigest()[:16]
    return self._create_token(
        str(user_id),
        timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        "password_reset",
        extra_claims={"pwd_fp": pwd_fp},
    )
```

The token embeds a 16-character SHA-256 fingerprint of the **current** password hash as an extra
JWT claim. `verify_password_reset_token` decodes the token, re-reads the user's *current*
`password_hash` from the database (never a caller-supplied value — the method owns its own
lookup, keyed only off the token's own `sub` claim), recomputes the same fingerprint, and rejects
the token if it doesn't match:

```python
expected_fp = hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]
if payload.get("pwd_fp") != expected_fp:
    raise ValueError("Invalid or expired token")
```

Because `reset-password` changes `password_hash`, using a reset token once invalidates it for
any second use — the fingerprint recomputed against the *new* hash no longer matches the
`pwd_fp` claim minted against the old one. This gives genuine single-use semantics from a plain,
stateless JWT: no dedicated "used tokens" table, no revocation list.

**Documented limitation (verified still present and accurate in the auth-expansion spec's
Non-goals, §8):** resetting the password does **not** revoke access/refresh tokens issued before
the reset. Those keep working until they naturally expire — only the password itself changes.
Revoking already-issued stateless JWTs would need a mechanism this codebase doesn't have (token
versioning, or a `password_hash` fingerprint check on *every* authenticated request, not just
the password-reset token) and is a separable architectural change, not something this feature
attempts.

## Admin user management

Whenever `rbac.enabled: true`, five endpoints are generated under `require_roles("admin")`
(`routes.py.jinja` lines 171–245): `GET /users`, `GET /users/{id}`, `PUT /users/{id}/roles`
(full replace, rejecting any role not in the declared `rbac.roles` set), `POST
/users/{id}/deactivate`, `POST /users/{id}/reactivate`. A sixth, `POST /users/{id}/approve`, is
generated only under `admin_approval` mode.

**Bootstrap-admin auto-approval.** Under `admin_approval` mode, the very first user registered
would otherwise be locked out with no way to approve themselves — there's no existing admin to
call `POST /users/{id}/approve`. This was a real defect caught in this feature's own final
whole-branch review and is fixed in the current template. `register_user` (`service.py.jinja`
lines 76–110) computes `is_first_user` (reused from the RBAC bootstrap check below) and, when
`registration.mode == admin_approval`, stamps it straight onto the new user:

```python
is_approved=is_first_user,
```

So the first user registered in a fresh `admin_approval`-mode project is auto-approved and can
log in immediately; every subsequent registration still requires an existing admin to approve
it. This mirrors the pre-existing RBAC bootstrap convention — see
[RBAC → first-user bootstrap](rbac.md#first-user-bootstrap) — which grants the first user every
declared role for the identical reason (otherwise `roles=[]` locks everyone out of every
RBAC-gated endpoint, permanently, with no admin able to fix it).

## Deactivation takes effect immediately, not just at next login

A second defect fixed in the same final-review round: `get_current_user` (used by `/auth/me` and
every `require_roles(...)`-gated route) and `POST /auth/refresh` previously did not re-check
`is_active` after the initial login, so deactivating a user did not revoke their already-issued
tokens — they kept working until expiry. Both are now checked directly against the current
`service.py.jinja`/`routes.py.jinja` templates:

```python
# service.py.jinja, get_current_user
if not user.is_active:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
```

```python
# routes.py.jinja, /auth/refresh
if not user.is_active:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
```

So today, deactivating a user via `POST /users/{id}/deactivate` immediately blocks both
`/auth/refresh` (no new access token can be minted) and every `get_current_user`-gated route
(the existing access token stops working the moment it's next used) — not just future logins.

## Full field shape

For the exact YAML keys, types, and defaults — `auth.enabled`, `auth.jwt.*` (the four
independently configurable token lifetimes), `auth.registration.mode`, and the cross-field
validation rules the loader enforces (e.g. what `admin_approval` requires) — see the
[Full field reference → `auth`](../erd-reference/fields.md#auth-authspec).
