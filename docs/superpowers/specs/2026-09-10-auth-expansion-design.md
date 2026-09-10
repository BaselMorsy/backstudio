# Auth Service Expansion (Spec 2) — Design Spec

Date: 2026-09-10
Status: Approved for implementation planning
Extends: `docs/superpowers/specs/2026-09-08-erd-cli-design.md`,
`docs/superpowers/specs/2026-09-09-modular-services-design.md`

## 1. Motivation

The generated auth module today covers the bare minimum: register, login,
refresh, and `/me`. Three real gaps were flagged and agreed as "Spec 2" in
the backlog, never written up formally:

- No way for an admin to manage users (list, inspect, change roles,
  deactivate/reactivate) once RBAC roles exist — an operator has no path
  but direct DB access.
- No way to gate registration — every project either has open self-signup
  or nothing; there is no "verify your email first" or "an admin must
  approve you" option.
- No forgot/reset-password flow — a user who loses their password has no
  recovery path other than an admin resetting it by hand (which isn't
  possible either, today).

This spec adds all three, as one combined design (per explicit agreement —
they share the auth module and the User model, and reviewing them together
surfaces the token-mechanism and User-schema decisions that both
registration-gating and password-reset need in common).

## 2. Scope boundary

**In scope:**
- Admin user-management endpoints (list/get/set-roles/deactivate/
  reactivate/approve), generated whenever `rbac.enabled: true`.
- Registration gating: `open` (today's behavior, default), `email_verification`,
  `admin_approval` — a single, mutually-exclusive mode per project.
- Forgot/reset password, available whenever `auth.enabled: true`,
  independent of registration mode.
- Four independently configurable JWT lifetimes: access token (already
  configurable), refresh token (currently hardcoded 7 days — becomes
  configurable), email-verification token, password-reset token (both new).
- Full sync/async propagation and RBAC integration, per this codebase's
  established conventions.

**Out of scope (see §8 for the complete list):** invite-only registration,
real email delivery, admin self-lockout protection, a reject/deny action
for pending users, audit logging, rate-limiting.

## 3. ERD schema additions

```yaml
auth:
  enabled: true
  jwt:
    secret_env_var: JWT_SECRET
    algorithm: HS256
    expiration_minutes: 30                        # access token (existing, unchanged)
    refresh_token_expiration_minutes: 10080        # refresh token (was hardcoded 7 days = 10080 min)
    email_verification_expiration_minutes: 1440    # 24h default
    password_reset_expiration_minutes: 30          # 30min default

  registration:
    mode: open   # open (default) | email_verification | admin_approval
```

`JWTSpec` gains three new fields with the defaults shown above (all
optional, all overridable). `AuthSpec` gains a new nested `RegistrationSpec`
(`mode: Literal["open", "email_verification", "admin_approval"] = "open"`).

### 3.1 Validation rules (ERD load time, alongside the existing checks)

1. Admin user-management endpoints are generated whenever `rbac.enabled: true`
   — no separate opt-in flag. `rbac.roles` must include `"admin"` (a
   reserved role name, exactly like `User` is a reserved entity name) or
   loading fails with a clear error naming the missing role.
2. `auth.registration.mode` other than `"open"` requires `auth.enabled: true`
   (already implied — `registration` only exists under `auth`, but stated
   explicitly for a clear error message rather than a schema-shape error).
3. `auth.registration.mode: "admin_approval"` requires `rbac.enabled: true`
   (the `POST /users/{id}/approve` endpoint needs `admin` to exist, same as
   rule 1 — this is not a separate requirement, it composes with rule 1).
4. `email_verification_expiration_minutes` / `password_reset_expiration_minutes`
   / `refresh_token_expiration_minutes`, if set, must be positive integers
   (already implied by `int` typing with no explicit lower bound needed
   beyond Pydantic's default int validation — no new custom validator
   required beyond what `expiration_minutes` already gets).

## 4. User model additions

Two new fields on the reserved `User` entity, added to `AUTH_USER_FIELDS`
**conditionally** based on `auth.registration.mode` (not unconditionally —
matching this codebase's existing minimalism: `rbac.py` is only generated
when `rbac.enabled`, so an unused-mode field is likewise not generated
here):

- `is_verified: bool` (default `false`) — added only when
  `mode == "email_verification"`.
- `is_approved: bool` (default `false`) — added only when
  `mode == "admin_approval"`.

Both are surfaced on `UserResponse` (auth schemas) and on the admin
module's user-facing response schema, whenever present — mirroring how
`is_active` is already always present and visible.

## 5. Mechanics

### 5.1 Admin user management

New file `backend/templates/Python/auth/admin_routes.py.jinja` (or a new
section of the existing `auth/routes.py.jinja` — implementation detail for
the plan to decide; conceptually a separate route group under the same
router), generated whenever `rbac.enabled: true`. All five (or six, with
`approve`) endpoints require `Depends(require_roles("admin"))`:

- `GET /users` — paginated (`skip`/`limit`, matching every other list
  endpoint's convention), returns `List[UserResponse]`.
- `GET /users/{id}` — 404 if not found.
- `PUT /users/{id}/roles` — body `{"roles": [...]}`, **full replace** (not
  add/remove). Every role in the payload must be a declared `rbac.roles`
  entry, or 400 naming the invalid role(s) (this response *can* be
  specific — it's admin-only, not a public enumeration surface). Returns
  the updated `UserResponse`.
- `POST /users/{id}/deactivate` / `POST /users/{id}/reactivate` — toggle
  `is_active`, return the updated `UserResponse`. No self-lockout guard
  (§8).
- `POST /users/{id}/approve` — generated only when
  `mode == "admin_approval"`. Sets `is_approved = true`, returns the
  updated `UserResponse`. No "reject" counterpart (§8).

### 5.2 Registration gating

Both modes hook into the **same single enforcement point** —
`authenticate_user` (login) — which already rejects `is_active=False` with
`ValueError("User is inactive")`. The new modes add analogous checks in
the same function, in this order (all still map to 401 in `routes.py`):
`is_active` (existing) → `is_verified` if mode is `email_verification`
(`ValueError("Email not verified")`) → `is_approved` if mode is
`admin_approval` (`ValueError("Account pending approval")`). Since the
modes are mutually exclusive, at most one of the latter two checks is ever
compiled into a given project.

**`email_verification` mode:**
- `register`'s response shape is unchanged (still returns the created
  `UserResponse`, still 201) — it additionally calls
  `AuthService.create_email_verification_token(user_id)` and passes the
  result to the dev-mode `send_email()` stub (§5.4).
- New `POST /auth/verify-email` (body `{"token": "..."}`) — decodes via
  `decode_token(token, expected_type="email_verification")`, sets
  `is_verified = true`, returns a generic `MessageResponse`
  (`{"message": "Email verified."}`) — no user object, nothing to leak.
  An expired/malformed/wrong-type token → generic 400
  `{"detail": "Invalid or expired token"}`. Re-verifying an already-verified
  account is a harmless no-op (idempotent), so no special replay
  protection is needed here (contrast §5.3's password-reset tokens, which
  need genuine single-use enforcement since a leaked one grants account
  takeover).
- New `POST /auth/resend-verification` (body `{"email": "..."}`) — **must
  not require authentication** (an unverified user cannot log in to obtain
  a bearer token in the first place, so this cannot be
  `Depends(get_current_user)`-gated). Always returns the same generic
  `MessageResponse` regardless of whether the email exists or is already
  verified — enumeration-safe, mirroring `forgot-password`'s shape below.
  If the email exists and is unverified, sends a fresh verification email.

**`admin_approval` mode:** `register` is unchanged; no email is sent (this
mode has no email-delivery requirement — an admin discovers pending users
via `GET /users` and calls `POST /users/{id}/approve`).

### 5.3 Forgot/reset password

Available whenever `auth.enabled: true`, independent of `registration.mode`.

- `POST /auth/forgot-password` (body `{"email": "..."}`) — **always**
  returns the same generic `MessageResponse` 200, regardless of whether
  the email exists — enumeration-safe. If it does exist, calls
  `AuthService.create_password_reset_token(user_id, password_hash)` and
  passes the result to the dev-mode `send_email()` stub.
- `POST /auth/reset-password` (body `{"token": "...", "new_password": "..."}`)
  — verifies and consumes the token (see below), sets a new
  `password_hash`, returns a generic `MessageResponse`. An
  expired/malformed/wrong-type/already-used token → generic 400
  `{"detail": "Invalid or expired token"}` — deliberately not
  distinguishing *why* it failed, same reasoning as `verify-email`.

**Single-use enforcement without a new DB table.**
`create_password_reset_token(user_id, password_hash)` embeds a short
fingerprint of the *current* password hash as an extra JWT claim:
`pwd_fp = hashlib.sha256(password_hash.encode()).hexdigest()[:16]`
(alongside the standard `sub`/`exp`/`type` claims already used by every
other token type). A dedicated verification method,
`verify_password_reset_token(token, current_password_hash) -> int`, calls
`decode_token(token, expected_type="password_reset")` to get the subject
id and validate expiry/type, then independently recomputes the fingerprint
from `current_password_hash` (freshly read from the DB, not cached) and
compares it against the token's `pwd_fp` claim — a mismatch means the
password has already changed since this token was issued (either this
token was already used once, or the password changed some other way in
the interim), so the token is rejected as stale. This gives genuine
single-use semantics for a plain, stateless JWT, with no new table and no
"used tokens" bookkeeping.

### 5.4 The dev-mode email stub

New file `backend/templates/Python/auth/email.py.jinja`, generated
whenever `auth.enabled: true` (forgot-password needs it unconditionally,
not just under `email_verification` mode):

```python
def send_email(to: str, subject: str, body: str) -> None:
    """Development-mode stub - logs instead of sending. Replace with a real
    email provider integration (SES, SendGrid, SMTP, ...) before production."""
    print(f"[DEV EMAIL] To: {to}\nSubject: {subject}\n\n{body}\n")
```

`AuthService` methods that need to send email call this directly (no
abstraction beyond the one function) — `register` (verification email) and
`forgot-password` (reset email) both import and call `send_email(...)`
with the token embedded in the body text (a real integration would embed
it in a clickable link instead; out of scope here, see §8).

## 6. New/changed schemas (`auth/schemas.py.jinja`)

- `SetUserRolesRequest {roles: List[str]}`
- `VerifyEmailRequest {token: str}` (generated only under `email_verification` mode)
- `ResendVerificationRequest {email: EmailStr}` (generated only under `email_verification` mode)
- `ForgotPasswordRequest {email: EmailStr}`
- `ResetPasswordRequest {token: str, new_password: str = Field(..., min_length=8)}`
  (same `min_length=8` convention as `UserRegister.password`)
- `MessageResponse {message: str}` — the generic-response shape shared by
  `verify-email`, `resend-verification`, `forgot-password`, `reset-password`.
- `UserResponse` gains `is_verified`/`is_approved` fields, each present
  only when the corresponding mode is active (mirroring §4).

## 7. Testing plan

Concrete test code belongs in the implementation plan, not this spec.
Coverage this plan must include:
- All 5 (or 6, with `approve`) admin endpoints: a 403-for-non-admin case
  and a real success case for each, over real HTTP against a real
  generated app.
- Full `email_verification` flow: register → capture the token from the
  dev-mode stub's output → verify → login now succeeds; login while
  unverified is rejected; `resend-verification`'s generic response for
  both a real and a nonexistent email; an expired verification token is
  rejected.
- Full `admin_approval` flow: register → login rejected (pending) → admin
  approves via `POST /users/{id}/approve` → login now succeeds.
- Full forgot/reset flow: forgot-password → capture the token → reset →
  login with the new password succeeds, the old password is now rejected;
  resetting with an **already-used** token is rejected (proving the
  fingerprint single-use mechanism actually works, not just that expiry
  works); resetting with a genuinely expired token is rejected;
  `forgot-password`'s generic response for a nonexistent email.
- ERD-load-time validation: missing `admin` role with `rbac.enabled`,
  `admin_approval` mode without `rbac.enabled`, each new JWT lifetime
  field accepting a custom value and it actually taking effect (e.g. a
  1-minute-lifetime reset token that's expired by the time the test
  checks it).
- Sync/async parity for every scenario above.

## 8. Non-goals

- Invite-only registration mode (flagged in the backlog as deferred, no
  concrete design yet).
- Real email delivery (SES/SendGrid/SMTP/...) — the dev-mode `print()`
  stub is the full extent of this pass; a real integration is a clearly
  separable follow-up that only touches `email.py.jinja`.
- Admin self-lockout protection (an admin deactivating their own account).
- A "reject"/"deny" action for a pending `admin_approval` user distinct
  from simply never approving them.
- Audit logging of admin actions (who deactivated/approved/changed roles
  for whom, and when).
- Rate-limiting on `forgot-password`/`resend-verification` (both are
  unauthenticated, enumeration-adjacent endpoints that would benefit from
  it in production, but that's a cross-cutting concern this codebase has
  no existing pattern for, not specific to this feature).
- Clickable-link email bodies (the dev-mode stub embeds the raw token as
  text; a real provider integration would template a proper link).
