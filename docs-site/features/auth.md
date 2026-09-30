# Authentication

`auth.mode` picks between two entirely different auth generators, `builtin` (the default) and
`external`. Everything from here down to [External JWT verification](#external-jwt-verification-authmode-external)
describes `mode: builtin`; that section covers `mode: external` on its own terms, since the two
share no generated code.

Turning on `auth.enabled: true` with `mode: builtin` auto-injects a reserved `User` entity and
generates a full JWT auth module (`modules/<auth_module_name>/` — `service.py`, `routes.py`,
`schemas.py`, `email.py`), verified here against the live templates:
`app/templates/Python/auth/service.py.jinja` and `app/templates/Python/auth/routes.py.jinja`. For
the exact YAML shape (`auth.jwt.*`, `auth.registration.*`, every field's type/default), see the
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
| `admin_approval` | Login raises `ValueError("Account pending approval")` until `is_approved` is set. Requires `rbac.enabled: true` (the approve endpoint is `admin`-gated). | See bootstrap-admin behavior below. `POST /auth/users/{id}/approve` sets `is_approved=True`. |

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
(`routes.py.jinja` lines 171–245): `GET /auth/users`, `GET /auth/users/{id}`, `PUT
/auth/users/{id}/roles` (full replace, rejecting any role not in the declared `rbac.roles` set),
`POST /auth/users/{id}/deactivate`, `POST /auth/users/{id}/reactivate`. A sixth, `POST
/auth/users/{id}/approve`, is generated only under `admin_approval` mode. (These are mounted
under the auth module's prefix, `/auth` by default, the same as the auth-flow routes above.)

**Bootstrap-admin auto-approval.** Under `admin_approval` mode, the very first user registered
would otherwise be locked out with no way to approve themselves — there's no existing admin to
call `POST /auth/users/{id}/approve`. This was a real defect caught in this feature's own final
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

So today, deactivating a user via `POST /auth/users/{id}/deactivate` immediately blocks both
`/auth/refresh` (no new access token can be minted) and every `get_current_user`-gated route
(the existing access token stops working the moment it's next used) — not just future logins.

## External JWT verification (`auth.mode: external`)

`auth.mode: external` is for the case where some *other* service already issues JWTs (an identity
provider, a gateway, another backend) and this generated project only needs to **verify** them —
never issue, refresh, or store credentials for its own users. Setting it changes what gets
generated, not just how the existing auth module behaves:

```yaml
auth:
  enabled: true
  mode: external
  external:
    jwks_url_env_var: AUTH_JWKS_URL   # env var holding the JWKS endpoint URL
    issuer: authservice
    audience: my-api                  # optional - see below
    algorithms: [RS256]               # default; any asymmetric alg is allowed
    claims:
      subject: sub                    # default
      roles: roles                    # default
```

**What is *not* generated:** no `User` entity (`database/models.py` has no `class User(Base):` at
all), no `register`/`login`/`refresh`/`/me` endpoints, no password hashing dependency
(`passlib`/`bcrypt`/`email-validator`/`python-multipart` are dropped from `requirements.txt`
entirely — verified in `app/tests/test_external_auth_generation.py::test_requirements_has_jose_and_httpx_but_not_password_deps`).
The `auth.jwt.*` and `auth.registration.*` blocks above don't apply and must be left unset (the
loader rejects a customized `jwt`/`registration` block under `mode: external`, and rejects any
declared `User` entity too).

Instead, `modules/<auth_module_name>/service.py` (`app/templates/Python/auth/external_service.py.jinja`)
generates a single `ExternalAuthService` whose `get_current_user` verifies the bearer token against
a JWKS and returns a `Principal(id, roles, claims)` — the `mode: external` stand-in for `User`
everywhere a route or `require_roles(...)` dependency needs "the current caller" (RBAC and RLS
templates key off `principal_type_name`/`principal_import` rather than hardcoding `User`, so the
same generated route code works under either mode).

### JWKS verification mechanics

- **Lazy, in-memory cache keyed by `kid`.** The JWKS endpoint is fetched only when a token's `kid`
  isn't already in the cache — not eagerly at startup, not on a timer.
- **Refetch-once on an unknown `kid`, no TTL.** If a token's `kid` isn't cached, the JWKS is
  fetched exactly once more; if the `kid` still isn't found after that, verification fails with a
  401. There is no periodic background refresh — a `kid` that was valid once stays resolvable for
  the life of the process, and a genuinely rotated-out key simply stops being cached anew.
- **Every verification failure is a 401, fail-closed**, through a single `except JWTError:` — bad
  signature, wrong issuer, wrong (or missing, when required) audience, expired token, malformed
  token, and an unknown `kid` all collapse to the same outcome. This was verified empirically
  against python-jose 3.3.0 (real RSA keypair, real signed tokens), not assumed from its docs —
  see `test_get_current_user_rejects_every_failure_mode`.

### `audience` is optional, but unset warns

Omitting `audience` skips audience validation entirely (`jwt.decode(...)` is called without an
`audience=` kwarg) rather than defaulting to some implicit check — a token with no `aud` claim at
all still verifies. Because a missing `audience` is easy to omit by accident and silently widens
what tokens are accepted, `backstudio validate` emits a warning (not an error) whenever
`mode: external` and `external.audience` is unset.

### Why HS256/HS384/HS512 are rejected

`external.algorithms` only accepts asymmetric algorithms (`RS256` by default); declaring `HS256`,
`HS384`, or `HS512` is a schema-construction-time validation error, not a runtime one. This is
alg-confusion prevention: an HMAC algorithm's "signature" is a MAC keyed by the same secret used to
verify it, and in a JWKS-based, verify-only setup there is no shared secret at all — only public
keys are published. If a shared-secret algorithm were accepted, in the specific case where an
attacker could get an endpoint to treat a JWKS-published RSA *public* key as an HMAC *secret*, they
could forge tokens the service would accept. Requiring an asymmetric algorithm removes that failure
mode structurally rather than relying on every deployment to configure it correctly.

For the exact schema (every field's type, default, and required/optional status), see the
[Full field reference → `AuthSpec`](../erd-reference/fields.md#auth-authspec) and
[`ExternalAuthSpec`](../erd-reference/fields.md#authexternal-externalauthspec).

## Full field shape

For the exact YAML keys, types, and defaults — `auth.enabled`, `auth.jwt.*` (the four
independently configurable token lifetimes), `auth.registration.mode`, and the cross-field
validation rules the loader enforces (e.g. what `admin_approval` requires) — see the
[Full field reference → `auth`](../erd-reference/fields.md#auth-authspec).
