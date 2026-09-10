# Auth Service Expansion (Spec 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin user-management endpoints (generated whenever `rbac.enabled: true`), opt-in registration gating (`open` / `email_verification` / `admin_approval`, mutually exclusive), and a forgot/reset-password flow — plus make all four JWT lifetimes (access, refresh, email-verification, password-reset) independently configurable from the YAML.

**Architecture:** `JWTSpec` gains three new lifetime fields; `AuthSpec` gains a `registration.mode` field. `loader.py` gains two new cross-entity checks (the reserved `admin` role, and `admin_approval` requiring `rbac.enabled`). `translate.py`'s `_build_user_entity` becomes mode-aware (conditionally appending `is_verified`/`is_approved` to `AUTH_USER_FIELDS`), and `translate()` threads `registration_mode` plus the three new JWT lifetimes through the top-level state dict / `security_config`. `auth/service.py.jinja` gains `create_email_verification_token`/`create_password_reset_token`/`verify_password_reset_token`/`verify_email`/five-to-six admin methods, plus a new `auth/email.py.jinja` dev-mode stub; `authenticate_user` gains one new mode-gated check. `auth/schemas.py.jinja` gains new request/response schemas, several mode-gated. `auth/routes.py.jinja` gains the verify-email/resend-verification/forgot-password/reset-password/admin routes, mode- and rbac-gated respectively. Every template change branches on `database.async_mode` using this codebase's established sync/async conventions (surgical inline tokens throughout the auth module — confirmed against the current file, not assumed).

**Tech Stack:** Python 3.11, Jinja2 (`trim_blocks`/`lstrip_blocks`), SQLAlchemy 2.0.23, FastAPI, `python-jose` (JWT), `passlib`/`bcrypt`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-auth-expansion-design.md`

## Global Constraints

- **New `JWTSpec` fields and defaults** (`backend/erd/schema.py`), copied verbatim from spec §3:
  ```python
  refresh_token_expiration_minutes: int = 10080          # was hardcoded timedelta(days=7) in the template
  email_verification_expiration_minutes: int = 1440      # 24h
  password_reset_expiration_minutes: int = 30
  ```
  `expiration_minutes` (access token) is unchanged, both in name and meaning.
- **New `RegistrationSpec`**: `mode: Literal["open", "email_verification", "admin_approval"] = "open"`. `AuthSpec.registration: RegistrationSpec = Field(default_factory=RegistrationSpec)`. The `Literal` type constrains `mode` to exactly these three values at the Pydantic level for free — no custom validator needed for that part.
- **Validation dependency chain** (enforced in `loader.py`, alongside the existing `rbac.enabled requires auth.enabled` check at line 144-147 of the current file):
  1. `rbac.enabled: true` requires `"admin"` in `rbac.roles`, or `ERDValidationError`.
  2. `registration.mode == "admin_approval"` requires `rbac.enabled: true` (which, by rule 1, also requires `"admin"` in `rbac.roles` — composed, not a separate admin-role check).
  Verified against every existing fixture in `backend/tests/fixtures/erd/`: every `rbac.enabled: true` fixture already declares `admin` in its roles, so rule 1 does not break any existing test. Still, Task 2's implementer must re-verify this against the fixtures directory as it exists at execution time (a fixture could have been added or changed since this plan was written) — do not skip this check on the assumption that this plan's snapshot is still accurate.
- **`User` model field additions are mode-gated, never unconditional** (mirrors this codebase's `rbac.py`-only-when-`rbac.enabled` minimalism): `is_verified: bool` (default `false`) only when `mode == "email_verification"`; `is_approved: bool` (default `false`) only when `mode == "admin_approval"`. `RESERVED_USER_FIELDS` in `loader.py` (currently a flat set checked against a user-declared `User` entity's own fields) must become mode-aware for these two names specifically — a user-declared `User` entity may freely have a field named `is_verified` when `mode != "email_verification"` (nothing will collide), but not when it is that mode.
- **Two axes of conditional generation compose independently, and every task touching `routes.py.jinja`/`service.py.jinja`/`schemas.py.jinja` must keep them independent, never conflate them:** `rbac_enabled` gates the 5-6 admin endpoints/methods; `registration_mode` gates the verify-email/resend-verification endpoints (`email_verification` only) and the `approve` endpoint (`admin_approval` only, and ALSO requires `rbac_enabled` — both conditions apply to `approve` specifically, nothing else). Forgot/reset-password is gated on neither — unconditional whenever `auth_enabled` (which is already implied by being inside the auth module at all).
- **`decode_token`'s existing contract is unchanged and must not be touched**: it raises `HTTPException(401, ...)` directly (not `ValueError`) on any decode failure — this is DIFFERENT from every other service method in this file, which raises `ValueError` for the route layer to catch and translate. Every NEW method that needs `decode_token`'s result but must surface a `ValueError`-shaped failure (so the existing `except ValueError as exc: raise HTTPException(400, ...)` route idiom can catch it) must wrap the call: `try: ... = self.decode_token(...) except HTTPException: raise ValueError("Invalid or expired token")`. This applies to `verify_email` and `verify_password_reset_token` (Task 4) — get this wrapping right in both, or a malformed/expired token will surface as an uncaught 401 with a different body shape than the spec's generic 400, breaking the enumeration-safety/uniformity requirement below.
- **The single-use password-reset-token mechanism is the binding mechanism, not negotiable per-task** (spec §5.3): `create_password_reset_token(user_id, password_hash)` embeds `pwd_fp = hashlib.sha256(password_hash.encode()).hexdigest()[:16]` as an extra JWT claim (needs `_create_token` extended with an `extra_claims: Optional[dict] = None` parameter — a purely additive change, `create_access_token`/`create_refresh_token` are unaffected since they don't pass it). `verify_password_reset_token(self, db, token)` decodes the token to learn its subject user id, looks up that user's *current* `password_hash` itself (read fresh from the DB, never caller-supplied and never cached), and compares its own freshly-recomputed fingerprint against the token's `pwd_fp` claim — the method owns its DB lookup entirely; no caller ever needs to know which user a token belongs to before calling it. Getting at the `pwd_fp` claim requires `decode_token` to optionally return the full payload dict instead of just the subject id; add a `return_payload: bool = False` parameter (default `False` preserves every existing caller's behavior unchanged) rather than a second decode implementation.
- **Enumeration-safety is a binding requirement, not a suggestion**: `resend-verification` and `forgot-password` must return the *identical* HTTP status and body regardless of whether the target email exists, is already verified/active, etc. No task may introduce a code path in the route or service layer that branches on "does this email exist" before returning — the branch must happen *after* deciding the response is already fixed (i.e., do the conditional work — send email or don't — as a side effect, then always return the same `MessageResponse`).
- **Async/sync branching**: every touched auth template (`service.py.jinja`, `routes.py.jinja`) already uses the surgical-inline-token convention exclusively (`{{ 'async ' if is_async }}def`, `{{ 'await ' if is_async }}...`) — confirmed against the current files, not assumed. `schemas.py.jinja` has no sync/async branching today and this plan does not introduce any (schemas are identical either way). The new `email.py.jinja` file has no DB access at all and needs no sync/async branching either.
- **Context variable paths** (all confirmed against the current `code_generator.py`, which builds the auth-module Jinja context as `{'project': state}` where `state` is `translate()`'s full returned dict — NOT the per-module `{'project': state, 'module': module}` shape regular CRUD modules get): `project.registration_mode` (new), `project.security_config.jwt_refresh_expiration_minutes` / `.jwt_email_verification_expiration_minutes` / `.jwt_password_reset_expiration_minutes` (new, alongside the existing `.jwt_expiration_minutes`), `project.rbac_enabled`, `project.rbac_roles`, `project.auth_module_name` (all pre-existing, unchanged).
- **`Depends(require_roles("admin"))` for the admin endpoints uses the decorator-only form** (`dependencies=[Depends(require_roles("admin"))]`), never the named-parameter restructuring the RLS plan needed for its `auth_user`-sourced routes — none of the admin endpoints need to read the caller's own identity inside the handler body, only gate on it, so the simpler pre-existing pattern (already used by every RBAC-gated CRUD route in `module_routes.py.jinja`) applies directly.
- **Every template change must be verified by actually rendering against a real fixture and reading the output** — not just eyeballing the template source or trusting `ast.parse`/`py_compile`, which catch syntax errors but not a wrong gating condition or a missing `await`.
- **Do not introduce Jinja macros anywhere** (this codebase has never used them).

---

### Task 1: ERD schema fields + local validation

**Files:**
- Modify: `backend/erd/schema.py`
- Test: `backend/tests/test_erd_schema.py`

**Interfaces:**
- Produces: `JWTSpec.refresh_token_expiration_minutes`/`.email_verification_expiration_minutes`/`.password_reset_expiration_minutes`, `RegistrationSpec`, `AuthSpec.registration`.
- Consumed by: Task 2 (loader validation), Task 3 (translate.py wiring).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_erd_schema.py` (read the file first for its exact existing style/imports):

```python
from backend.erd.schema import JWTSpec, RegistrationSpec, AuthSpec


def test_jwt_spec_new_lifetime_fields_have_correct_defaults():
    jwt = JWTSpec()
    assert jwt.expiration_minutes == 30
    assert jwt.refresh_token_expiration_minutes == 10080
    assert jwt.email_verification_expiration_minutes == 1440
    assert jwt.password_reset_expiration_minutes == 30


def test_jwt_spec_new_lifetime_fields_are_overridable():
    jwt = JWTSpec(
        refresh_token_expiration_minutes=5,
        email_verification_expiration_minutes=10,
        password_reset_expiration_minutes=1,
    )
    assert jwt.refresh_token_expiration_minutes == 5
    assert jwt.email_verification_expiration_minutes == 10
    assert jwt.password_reset_expiration_minutes == 1


def test_registration_spec_defaults_to_open():
    reg = RegistrationSpec()
    assert reg.mode == "open"


def test_registration_spec_accepts_valid_modes():
    assert RegistrationSpec(mode="email_verification").mode == "email_verification"
    assert RegistrationSpec(mode="admin_approval").mode == "admin_approval"


def test_registration_spec_rejects_unknown_mode():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RegistrationSpec(mode="invite_only")


def test_auth_spec_registration_defaults_to_open_mode():
    auth = AuthSpec(enabled=True)
    assert auth.registration.mode == "open"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_erd_schema.py -k "jwt_spec_new or registration_spec or auth_spec_registration" -v`
Expected: FAIL — `refresh_token_expiration_minutes` etc. and `RegistrationSpec` don't exist yet.

- [ ] **Step 3: Implement**

In `backend/erd/schema.py`, modify `JWTSpec`:

```python
class JWTSpec(BaseModel):
    secret_env_var: str = "JWT_SECRET"
    algorithm: str = "HS256"
    expiration_minutes: int = 30
    refresh_token_expiration_minutes: int = 10080
    email_verification_expiration_minutes: int = 1440
    password_reset_expiration_minutes: int = 30
```

Add `RegistrationSpec` (placed immediately after `JWTSpec`, before `AuthSpec`, so `AuthSpec` can reference it in source order):

```python
class RegistrationSpec(BaseModel):
    mode: Literal["open", "email_verification", "admin_approval"] = "open"
```

Modify `AuthSpec`:

```python
class AuthSpec(BaseModel):
    enabled: bool = False
    jwt: JWTSpec = Field(default_factory=JWTSpec)
    registration: RegistrationSpec = Field(default_factory=RegistrationSpec)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_erd_schema.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS, same count as before plus the new tests.

- [ ] **Step 6: Commit**

```bash
git add backend/erd/schema.py backend/tests/test_erd_schema.py
git commit -m "Add configurable JWT lifetimes and registration.mode to the ERD schema"
```

---

### Task 2: Load-time cross-entity validation — `backend/erd/loader.py`

**Files:**
- Modify: `backend/erd/loader.py`
- Test: `backend/tests/test_erd_loader.py`

**Interfaces:**
- Consumes: `AuthSpec.registration.mode`, `RBACSpec.enabled`/`.roles` (Task 1).
- Produces: rejection of every ERD that violates spec §3.1 rules — `rbac.enabled` without `"admin"` in `rbac.roles`; `registration.mode: admin_approval` without `rbac.enabled: true`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_erd_loader.py` (read a couple of existing tests first for the exact `tmp_path` + inline-YAML style):

```python
def test_rbac_enabled_requires_admin_role(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
rbac: {enabled: true, roles: [customer]}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="admin"):
        load_erd(bad)


def test_rbac_enabled_with_admin_role_loads_fine(tmp_path):
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
rbac: {enabled: true, roles: [admin, customer]}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert "admin" in erd.rbac.roles


def test_admin_approval_mode_requires_rbac_enabled(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth:
  enabled: true
  registration: {mode: admin_approval}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="admin_approval"):
        load_erd(bad)


def test_admin_approval_mode_with_rbac_and_admin_role_loads_fine(tmp_path):
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth:
  enabled: true
  registration: {mode: admin_approval}
rbac: {enabled: true, roles: [admin]}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert erd.auth.registration.mode == "admin_approval"


def test_email_verification_mode_needs_no_rbac(tmp_path):
    """email_verification mode has no admin-only endpoint, so it must NOT
    require rbac.enabled - only admin_approval does (it needs the admin-gated
    approve endpoint).
    """
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth:
  enabled: true
  registration: {mode: email_verification}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert erd.auth.registration.mode == "email_verification"


def test_declared_user_entity_can_have_is_verified_field_when_mode_is_not_email_verification(tmp_path):
    """RESERVED_USER_FIELDS must be mode-aware: is_verified only collides
    with the auto-injected field when email_verification mode is active.
    """
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - name: User
    fields:
      - {name: is_verified, type: boolean, default: false}
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    erd = load_erd(ok)  # must not raise - mode is "open", is_verified is not reserved
    assert erd.auth.registration.mode == "open"


def test_declared_user_entity_is_verified_field_collides_under_email_verification_mode(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth:
  enabled: true
  registration: {mode: email_verification}
entities:
  - name: User
    fields:
      - {name: is_verified, type: boolean, default: false}
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="is_verified"):
        load_erd(bad)
```

Add the needed imports at the top of `backend/tests/test_erd_loader.py` if not already present (`import pytest` and `from backend.erd.loader import load_erd, ERDValidationError` are almost certainly already there — check first, add only what's missing).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_erd_loader.py -k "admin_role or admin_approval or email_verification_mode or is_verified" -v`
Expected: FAIL — none of these rules are enforced yet.

- [ ] **Step 3: Implement**

In `backend/erd/loader.py`, modify `RESERVED_USER_FIELDS` handling to become mode-aware. First, change the module-level constant to only the fields that are *always* reserved regardless of mode:

```python
RESERVED_USER_FIELDS = {"id", "email", "password_hash", "roles", "is_active", "created_at", "updated_at"}
MODE_GATED_RESERVED_USER_FIELDS = {
    "email_verification": {"is_verified"},
    "admin_approval": {"is_approved"},
}
```

In `_validate_semantics`, find the existing block (around the current line 174-181):

```python
        if entity.name == "User" and erd.auth.enabled:
            collide = sorted(set(field_names) & RESERVED_USER_FIELDS)
            if collide:
                raise ERDValidationError(
                    f"Entity 'User': field(s) {', '.join(collide)} collide with auto-injected auth "
                    f"fields ({', '.join(sorted(RESERVED_USER_FIELDS))}) — rename the colliding "
                    "field(s) on your declared 'User' entity."
                )
```

Replace it with a version that also checks the mode-gated set for the active mode:

```python
        if entity.name == "User" and erd.auth.enabled:
            reserved = RESERVED_USER_FIELDS | MODE_GATED_RESERVED_USER_FIELDS.get(erd.auth.registration.mode, set())
            collide = sorted(set(field_names) & reserved)
            if collide:
                raise ERDValidationError(
                    f"Entity 'User': field(s) {', '.join(collide)} collide with auto-injected auth "
                    f"fields ({', '.join(sorted(reserved))}) — rename the colliding "
                    "field(s) on your declared 'User' entity."
                )
```

Add the two new cross-entity checks to `_validate_semantics`, immediately after the existing `rbac.enabled requires auth.enabled` check (around the current line 144-147):

```python
    if erd.rbac.enabled and not erd.auth.enabled:
        raise ERDValidationError(
            "rbac.enabled requires auth.enabled: true (RBAC needs a way to identify the current user)"
        )

    if erd.rbac.enabled and "admin" not in erd.rbac.roles:
        raise ERDValidationError(
            "rbac.enabled requires 'admin' to be declared in rbac.roles — the auto-generated "
            "admin user-management endpoints (list/get/set-roles/deactivate/reactivate users) "
            "are gated to that specific role name, exactly like 'User' is a reserved entity "
            f"name. Declared roles: {', '.join(erd.rbac.roles) or 'none'}."
        )

    if erd.auth.registration.mode == "admin_approval" and not erd.rbac.enabled:
        raise ERDValidationError(
            "auth.registration.mode: admin_approval requires rbac.enabled: true — the "
            "'POST /users/{id}/approve' endpoint that approves a pending registration is "
            "gated to the 'admin' role, which requires RBAC to exist."
        )
```

(Note: this reuses the *existing* `rbac.enabled requires auth.enabled` check's location — read the current file to place the two new checks correctly relative to it, not necessarily verbatim-adjacent if the surrounding code has shifted.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_erd_loader.py -v`
Expected: PASS, all tests in the file (existing + new).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS. (This is also the point where this task's implementer must re-verify, against the fixtures directory as it currently exists, that no existing `rbac.enabled: true` fixture is missing `admin` from its roles — the plan's own snapshot found none, but re-check; grep `backend/tests/fixtures/erd/*.yml` for `rbac:` blocks with `enabled: true` and confirm each has `admin` in `roles:`.)

- [ ] **Step 6: Commit**

```bash
git add backend/erd/loader.py backend/tests/test_erd_loader.py
git commit -m "Add load-time validation for the reserved admin role and admin_approval's rbac dependency"
```

---

### Task 3: `translate.py` — mode-aware User fields + state wiring

**Files:**
- Modify: `backend/erd/translate.py`
- Create: `backend/tests/fixtures/erd/auth_email_verification.yml`, `backend/tests/fixtures/erd/auth_admin_approval.yml`
- Test: `backend/tests/test_erd_translate.py`

**Interfaces:**
- Consumes: `AuthSpec.registration.mode`, the three new `JWTSpec` lifetime fields (Task 1).
- Produces: `translate()`'s returned dict gains `registration_mode: str` (top-level key) and three new keys on `security_config` (`jwt_refresh_expiration_minutes`, `jwt_email_verification_expiration_minutes`, `jwt_password_reset_expiration_minutes`); the `User` entity's `fields` list conditionally includes `is_verified`/`is_approved`. This is what every remaining task (4-9) consumes — none of them re-derive it.

- [ ] **Step 1: Create the fixtures**

Create `backend/tests/fixtures/erd/auth_email_verification.yml` (extends `shophub_mini.yml`'s general shape — auth + rbac + a couple of entities — with `registration.mode: email_verification`):

```yaml
project:
  name: AuthEmailVerification
  version: "1.0.0"

database:
  type: sqlite
  database_name: auth_email_verification.db

auth:
  enabled: true
  jwt:
    secret_env_var: JWT_SECRET
    algorithm: HS256
    expiration_minutes: 30
    refresh_token_expiration_minutes: 10080
    email_verification_expiration_minutes: 1440
    password_reset_expiration_minutes: 30
  registration:
    mode: email_verification

rbac:
  enabled: true
  roles: [admin, customer]
  default_permissions:
    create: [admin, customer]
    list: [admin, customer]
    read: [admin, customer]
    update: [admin, customer]
    delete: [admin]

entities:
  - name: Note
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: body, type: string}

services:
  - name: notes
    entities: [Note]
```

Create `backend/tests/fixtures/erd/auth_admin_approval.yml` (identical shape, `registration.mode: admin_approval`):

```yaml
project:
  name: AuthAdminApproval
  version: "1.0.0"

database:
  type: sqlite
  database_name: auth_admin_approval.db

auth:
  enabled: true
  registration:
    mode: admin_approval

rbac:
  enabled: true
  roles: [admin, customer]
  default_permissions:
    create: [admin, customer]
    list: [admin, customer]
    read: [admin, customer]
    update: [admin, customer]
    delete: [admin]

entities:
  - name: Note
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: body, type: string}

services:
  - name: notes
    entities: [Note]
```

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/test_erd_translate.py`:

```python
def test_translate_email_verification_mode_adds_is_verified_field():
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    user = next(m for m in state["data_models"] if m["name"] == "User")
    field_names = [f["name"] for f in user["fields"]]
    assert "is_verified" in field_names
    assert "is_approved" not in field_names

    is_verified_field = next(f for f in user["fields"] if f["name"] == "is_verified")
    assert is_verified_field["type"] == "boolean"
    assert is_verified_field["nullable"] is False
    assert is_verified_field["default"] is False

    assert state["registration_mode"] == "email_verification"


def test_translate_admin_approval_mode_adds_is_approved_field():
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    user = next(m for m in state["data_models"] if m["name"] == "User")
    field_names = [f["name"] for f in user["fields"]]
    assert "is_approved" in field_names
    assert "is_verified" not in field_names

    is_approved_field = next(f for f in user["fields"] if f["name"] == "is_approved")
    assert is_approved_field["type"] == "boolean"
    assert is_approved_field["nullable"] is False
    assert is_approved_field["default"] is False

    assert state["registration_mode"] == "admin_approval"


def test_translate_open_mode_adds_neither_field():
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    user = next(m for m in state["data_models"] if m["name"] == "User")
    field_names = [f["name"] for f in user["fields"]]
    assert "is_verified" not in field_names
    assert "is_approved" not in field_names
    assert state["registration_mode"] == "open"


def test_translate_threads_jwt_lifetimes_into_security_config():
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    sec = state["security_config"]
    assert sec["jwt_expiration_minutes"] == 30
    assert sec["jwt_refresh_expiration_minutes"] == 10080
    assert sec["jwt_email_verification_expiration_minutes"] == 1440
    assert sec["jwt_password_reset_expiration_minutes"] == 30


def test_translate_custom_jwt_lifetimes_flow_through():
    from backend.erd.schema import ERDConfig, ProjectMeta, DatabaseSpec, AuthSpec, JWTSpec, EntitySpec, ServiceDecl
    from backend.schemas.data import ModelField, FieldType

    erd = ERDConfig(
        project=ProjectMeta(name="CustomLifetimes", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="c.db"),
        auth=AuthSpec(
            enabled=True,
            jwt=JWTSpec(
                refresh_token_expiration_minutes=5,
                email_verification_expiration_minutes=7,
                password_reset_expiration_minutes=1,
            ),
        ),
        entities=[
            EntitySpec(name="Widget", fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]),
        ],
        services=[ServiceDecl(name="widgets", entities=["Widget"])],
    )
    state = translate(erd)

    sec = state["security_config"]
    assert sec["jwt_refresh_expiration_minutes"] == 5
    assert sec["jwt_email_verification_expiration_minutes"] == 7
    assert sec["jwt_password_reset_expiration_minutes"] == 1
```

Add the needed imports at the top of `backend/tests/test_erd_translate.py` if not already present (`load_erd`, `translate`, `FIXTURES` constant are almost certainly already there — check first).

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_erd_translate.py -k "email_verification_mode or admin_approval_mode or open_mode_adds_neither or jwt_lifetimes" -v`
Expected: FAIL — `registration_mode` key and the new `security_config` keys don't exist yet; `is_verified`/`is_approved` are never added to `AUTH_USER_FIELDS`.

- [ ] **Step 4: Implement**

In `backend/erd/translate.py`, modify `_build_user_entity` to accept the mode and conditionally extend the fields list:

```python
def _build_user_entity(erd: ERDConfig) -> Dict[str, Any]:
    declared = next((e for e in erd.entities if e.name == "User"), None)
    fields = [dict(f) for f in AUTH_USER_FIELDS]
    if erd.auth.registration.mode == "email_verification":
        fields.append({"name": "is_verified", "type": "boolean", "nullable": False, "default": False})
    elif erd.auth.registration.mode == "admin_approval":
        fields.append({"name": "is_approved", "type": "boolean", "nullable": False, "default": False})
    if declared:
        fields.extend(f.model_dump(mode='json') for f in declared.fields)
    return {
        "name": "User",
        "table_name": "users",
        "plural_snake": _pluralize("User"),
        "fields": fields,
        "relationships": [],
        "owned_relationships": [],
        "many_to_many_relationships": [],
    }
```

(No change to `_build_user_entity`'s call site — it already receives `erd` and can read `erd.auth.registration.mode` directly, no new parameter needed.)

In `translate()`, extend the `security_config` dict construction (currently):

```python
    security_config = None
    if erd.auth.enabled:
        security_config = {
            "auth_strategy": "jwt",
            "jwt_secret_env_var": erd.auth.jwt.secret_env_var,
            "jwt_algorithm": erd.auth.jwt.algorithm,
            "jwt_expiration_minutes": erd.auth.jwt.expiration_minutes,
        }
```

to:

```python
    security_config = None
    if erd.auth.enabled:
        security_config = {
            "auth_strategy": "jwt",
            "jwt_secret_env_var": erd.auth.jwt.secret_env_var,
            "jwt_algorithm": erd.auth.jwt.algorithm,
            "jwt_expiration_minutes": erd.auth.jwt.expiration_minutes,
            "jwt_refresh_expiration_minutes": erd.auth.jwt.refresh_token_expiration_minutes,
            "jwt_email_verification_expiration_minutes": erd.auth.jwt.email_verification_expiration_minutes,
            "jwt_password_reset_expiration_minutes": erd.auth.jwt.password_reset_expiration_minutes,
        }
```

Add `"registration_mode": erd.auth.registration.mode,` to `translate()`'s final returned dict, alongside the existing `auth_enabled`/`rbac_enabled`/`rbac_roles` keys:

```python
        "auth_module_name": auth_module_name,
        "auth_enabled": erd.auth.enabled,
        "rbac_enabled": erd.rbac.enabled,
        "rbac_roles": erd.rbac.roles,
        "registration_mode": erd.auth.registration.mode,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_erd_translate.py -v`
Expected: PASS, all tests in the file (existing + new).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/erd/translate.py backend/tests/fixtures/erd/auth_email_verification.yml backend/tests/fixtures/erd/auth_admin_approval.yml backend/tests/test_erd_translate.py
git commit -m "Thread registration_mode and configurable JWT lifetimes through translate(), add mode-aware User fields"
```

---

### Task 4: `auth/service.py.jinja` — all new/changed methods, `email.py.jinja`, `config.py.jinja`, `code_generator.py` wiring

**Files:**
- Modify: `backend/templates/Python/auth/service.py.jinja`, `backend/templates/Python/config.py.jinja`, `backend/services/code_generator.py`
- Create: `backend/templates/Python/auth/email.py.jinja`
- Test: `backend/tests/test_auth_generation.py` (generation-level), a new `backend/tests/test_auth_expansion_generation.py` (generation-level, this feature's own file, mirroring how RLS got its own `test_rls_generation.py`), and live-DB tests in the latter.

**Interfaces:**
- Consumes: `registration_mode`, `security_config.jwt_*_expiration_minutes` (Task 3).
- Produces: `AuthService.create_email_verification_token`/`.create_password_reset_token`/`.verify_password_reset_token`/`.verify_email`/`.list_users`/`.get_user`/`.set_user_roles`/`.deactivate_user`/`.reactivate_user`/`.approve_user` (mode/rbac-gated) — consumed by Task 6 (routes).

**This is the largest, highest-risk task in the plan.** The password-reset fingerprint mechanism and the two new `authenticate_user` checks are security-sensitive; both need real live-DB proof, not just string assertions on rendered source.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_auth_expansion_generation.py` (new file):

```python
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_email_dot_py_generated_whenever_auth_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # open mode, no registration gating at all
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    email_path = codebase_dir / "modules" / "auth" / "email.py"
    assert email_path.exists()
    email_src = email_path.read_text(encoding="utf-8")
    ast.parse(email_src)
    assert "def send_email(to: str, subject: str, body: str) -> None:" in email_src
    assert "print(" in email_src


def test_refresh_token_uses_configurable_lifetime_not_hardcoded_seven_days(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    assert "timedelta(days=7)" not in service_src
    assert "settings.REFRESH_TOKEN_EXPIRE_MINUTES" in service_src

    config_src = (codebase_dir / "config.py").read_text(encoding="utf-8")
    assert "REFRESH_TOKEN_EXPIRE_MINUTES: int = 10080" in config_src
    assert "EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 1440" in config_src
    assert "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30" in config_src


def test_email_verification_mode_service_has_verification_methods(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "def create_email_verification_token(self, user_id: int) -> str:" in service_src
    assert 'token_type="email_verification"' in service_src
    assert "EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES" in service_src
    assert "def verify_email(self, db: Session, token: str) -> None:" in service_src
    assert "is_verified = True" in service_src
    assert "from .email import send_email" in service_src

    # authenticate_user must reject an unverified user
    auth_start = service_src.index("def authenticate_user(")
    auth_end = service_src.index("\n    def decode_token(")
    auth_src = service_src[auth_start:auth_end]
    assert "if not user.is_verified:" in auth_src
    assert 'raise ValueError("Email not verified")' in auth_src
    assert "is_approved" not in auth_src  # admin_approval's check must NOT be compiled in


def test_admin_approval_mode_service_has_approve_and_pending_check(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "def approve_user(self, db: Session, user_id: int) -> Optional[User]:" in service_src
    assert "is_approved = True" in service_src

    auth_start = service_src.index("def authenticate_user(")
    auth_end = service_src.index("\n    def decode_token(")
    auth_src = service_src[auth_start:auth_end]
    assert "if not user.is_approved:" in auth_src
    assert 'raise ValueError("Account pending approval")' in auth_src
    assert "is_verified" not in auth_src  # email_verification's check must NOT be compiled in

    # create_email_verification_token must NOT exist under this mode
    assert "create_email_verification_token" not in service_src


def test_open_mode_service_has_neither_gate_but_has_forgot_reset(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    auth_start = service_src.index("def authenticate_user(")
    auth_end = service_src.index("\n    def decode_token(")
    auth_src = service_src[auth_start:auth_end]
    assert "is_verified" not in auth_src
    assert "is_approved" not in auth_src
    assert "create_email_verification_token" not in service_src
    assert "approve_user" not in service_src

    # forgot/reset-password is unconditional, present regardless of mode
    assert "def create_password_reset_token(self, user_id: int, password_hash: str) -> str:" in service_src
    assert "pwd_fp" in service_src
    assert "def verify_password_reset_token(self, db: Session, token: str) -> int:" in service_src


def test_rbac_enabled_service_has_admin_methods(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # rbac.enabled: true, roles: [admin, customer]
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "def list_users(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:" in service_src
    assert "def get_user(self, db: Session, user_id: int) -> Optional[User]:" in service_src
    assert "def set_user_roles(self, db: Session, user_id: int, roles: List[str]) -> Optional[User]:" in service_src
    assert "def deactivate_user(self, db: Session, user_id: int) -> Optional[User]:" in service_src
    assert "def reactivate_user(self, db: Session, user_id: int) -> Optional[User]:" in service_src
    # this fixture is open mode - approve_user must NOT exist even though rbac is enabled
    assert "approve_user" not in service_src


def test_no_rbac_service_has_no_admin_methods(tmp_path):
    # rls_no_rbac_action.yml (from the RLS plan): auth.enabled: true, no rbac: block at all.
    erd = load_erd(f"{FIXTURES}/rls_no_rbac_action.yml")
    state = translate(erd)
    assert state["auth_enabled"] is True
    assert state["rbac_enabled"] is False

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "list_users" not in service_src
    assert "get_user" not in service_src
    assert "set_user_roles" not in service_src
    assert "deactivate_user" not in service_src
    assert "reactivate_user" not in service_src
    assert "approve_user" not in service_src


def test_set_user_roles_rejects_unknown_role(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    roles_start = service_src.index("def set_user_roles(")
    roles_end = service_src.index("\n    def deactivate_user(")
    roles_src = service_src[roles_start:roles_end]
    assert "ValueError" in roles_src
    assert "rbac_roles" not in roles_src  # the ALLOWED roles list is baked in at render time, not read from a runtime attribute
    assert '["admin", "customer"]' in roles_src or "'admin', 'customer'" in roles_src.replace('"', "'")
```

Add live-DB tests to the same file:

```python
def test_email_verification_blocks_login_until_verified(tmp_path):
    """The core email_verification security property, proven against a real
    DB: register -> login rejected -> verify -> login succeeds. Also proves
    the token round-trips through create_email_verification_token/verify_email
    correctly (not just that the methods exist).
    """
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "email_verif_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            user = service.register_user(db, "alice@example.com", "supersecret123")
            assert user.is_verified is False

            import pytest as _pytest
            with _pytest.raises(ValueError, match="Email not verified"):
                service.authenticate_user(db, "alice@example.com", "supersecret123")

            token = service.create_email_verification_token(user.id)
            service.verify_email(db, token)

            db.refresh(user)
            assert user.is_verified is True

            authed = service.authenticate_user(db, "alice@example.com", "supersecret123")
            assert authed.id == user.id
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_admin_approval_blocks_login_until_approved(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "admin_approval_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            user = service.register_user(db, "bob@example.com", "supersecret123")
            assert user.is_approved is False

            import pytest as _pytest
            with _pytest.raises(ValueError, match="Account pending approval"):
                service.authenticate_user(db, "bob@example.com", "supersecret123")

            approved = service.approve_user(db, user.id)
            assert approved.is_approved is True

            authed = service.authenticate_user(db, "bob@example.com", "supersecret123")
            assert authed.id == user.id
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_password_reset_token_is_genuinely_single_use(tmp_path):
    """The single most important test in this entire plan: proves the SHA256
    fingerprint mechanism actually gives single-use semantics on a plain
    stateless JWT, not just that expiry works.
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "pwd_reset_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            user = service.register_user(db, "carol@example.com", "originalpassword1")
            old_hash = user.password_hash

            token = service.create_password_reset_token(user.id, old_hash)

            # first use: succeeds, verifies subject and updates the hash
            user_id = service.verify_password_reset_token(db, token)
            assert user_id == user.id
            user.password_hash = service.hash_password("newpassword2")
            db.commit()
            db.refresh(user)
            new_hash = user.password_hash
            assert new_hash != old_hash

            # second use of the SAME token: must fail now, since password_hash changed
            import pytest as _pytest
            with _pytest.raises(ValueError, match="Invalid or expired token"):
                service.verify_password_reset_token(db, token)

            # old password no longer authenticates, new one does
            with _pytest.raises(ValueError, match="Invalid email or password"):
                service.authenticate_user(db, "carol@example.com", "originalpassword1")
            authed = service.authenticate_user(db, "carol@example.com", "newpassword2")
            assert authed.id == user.id
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_password_reset_token_rejects_malformed_or_wrong_type_token(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "pwd_reset_malformed_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            user = service.register_user(db, "dave@example.com", "supersecret123")

            import pytest as _pytest
            with _pytest.raises(ValueError, match="Invalid or expired token"):
                service.verify_password_reset_token(db, "not-a-real-token")

            # an access token (wrong type) must also be rejected, not just garbage
            access_token = service.create_access_token(user.id)
            with _pytest.raises(ValueError, match="Invalid or expired token"):
                service.verify_password_reset_token(db, access_token)
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_admin_service_methods_actually_work_against_a_real_db(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "admin_methods_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            admin_user = service.register_user(db, "admin@example.com", "supersecret123")
            other_user = service.register_user(db, "other@example.com", "supersecret123")

            listed = service.list_users(db)
            assert {u.id for u in listed} == {admin_user.id, other_user.id}

            fetched = service.get_user(db, other_user.id)
            assert fetched.id == other_user.id
            assert service.get_user(db, 999999) is None

            updated = service.set_user_roles(db, other_user.id, ["customer"])
            assert updated.roles == ["customer"]

            import pytest as _pytest
            with _pytest.raises(ValueError):
                service.set_user_roles(db, other_user.id, ["not_a_real_role"])

            deactivated = service.deactivate_user(db, other_user.id)
            assert deactivated.is_active is False
            reactivated = service.reactivate_user(db, other_user.id)
            assert reactivated.is_active is True

            assert service.deactivate_user(db, 999999) is None
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_auth_expansion_generation.py -v`
Expected: FAIL across the board — none of this exists in `service.py.jinja`/`email.py.jinja`/`config.py.jinja` yet.

- [ ] **Step 3: Implement**

Create `backend/templates/Python/auth/email.py.jinja` (no sync/async branching, no DB access):

```jinja
"""{{ project.name }} - {{ project.auth_module_name }} email stub"""


def send_email(to: str, subject: str, body: str) -> None:
    """Development-mode stub - logs instead of sending. Replace with a real
    email provider integration (SES, SendGrid, SMTP, ...) before production."""
    print(f"[DEV EMAIL] To: {to}\nSubject: {subject}\n\n{body}\n")
```

In `backend/templates/Python/config.py.jinja`, find the existing block (around the current lines 41-50):

```jinja
    {% if project.security_config and project.security_config.auth_strategy == 'jwt' %}
    # Security - JWT
    ...
    JWT_SECRET_KEY: str = _require_env("{{ project.security_config.jwt_secret_env_var }}")
    JWT_ALGORITHM: str = "{{ project.security_config.jwt_algorithm }}"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = {{ project.security_config.jwt_expiration_minutes }}
    {% endif %}
```

Add three lines immediately after `ACCESS_TOKEN_EXPIRE_MINUTES`, still inside the same `{% if %}` block:

```jinja
    ACCESS_TOKEN_EXPIRE_MINUTES: int = {{ project.security_config.jwt_expiration_minutes }}
    REFRESH_TOKEN_EXPIRE_MINUTES: int = {{ project.security_config.jwt_refresh_expiration_minutes }}
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = {{ project.security_config.jwt_email_verification_expiration_minutes }}
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = {{ project.security_config.jwt_password_reset_expiration_minutes }}
    {% endif %}
```

In `backend/templates/Python/auth/service.py.jinja`, apply these changes (read the current full file first — reproduced above in this plan's research, but re-read the actual file on disk before editing, since line numbers may have shifted):

1. Add `import hashlib` to the top imports, alongside the existing `from datetime import datetime, timedelta` / `from typing import Optional` block — change `from typing import Optional` to `from typing import Optional` plus a new line `from typing import List` is likely ALREADY needed once `list_users`/`set_user_roles` are added (check whether `List` is already imported anywhere in this file; it is not, per the current file's imports — add `List` to the existing `from typing import Optional` line, making it `from typing import List, Optional`), and add `import hashlib` as its own line near the top (with the other stdlib imports).

2. Extend `_create_token` to accept optional extra claims:

```jinja
    def _create_token(self, subject: str, expires_delta: timedelta, token_type: str, extra_claims: Optional[dict] = None) -> str:
        expire = datetime.utcnow() + expires_delta
        payload = {"sub": subject, "exp": expire, "type": token_type}
        if extra_claims:
            payload.update(extra_claims)
        return jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
```

3. Change `create_refresh_token` to use the configurable lifetime instead of the hardcoded `timedelta(days=7)`:

```jinja
    def create_refresh_token(self, user_id: int) -> str:
        return self._create_token(str(user_id), timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES), "refresh")
```

4. Add two new token-creation methods, immediately after `create_refresh_token`:

```jinja
{% if registration_mode == 'email_verification' %}
    def create_email_verification_token(self, user_id: int) -> str:
        return self._create_token(str(user_id), timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES), "email_verification")
{% endif %}

    def create_password_reset_token(self, user_id: int, password_hash: str) -> str:
        pwd_fp = hashlib.sha256(password_hash.encode()).hexdigest()[:16]
        return self._create_token(
            str(user_id),
            timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            "password_reset",
            extra_claims={"pwd_fp": pwd_fp},
        )
```

(Note `registration_mode` here is the top-level Jinja variable — since this template's context is `{'project': state}`, the correct reference is `{{ project.registration_mode }}`/`{% if project.registration_mode == 'email_verification' %}`, NOT a bare `registration_mode`. Use `project.registration_mode` everywhere in this file, matching how `project.rbac_enabled`/`project.rbac_roles` are already referenced elsewhere in this codebase's auth-adjacent templates — the brief text above uses the bare name for readability only; write the fully-qualified `project.registration_mode` form in the actual file.)

5. Modify `authenticate_user` to add the mode-gated checks after the existing `is_active` check:

```jinja
    {{ 'async ' if is_async }}def authenticate_user(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, email: str, password: str) -> User:
{% if is_async %}
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
{% else %}
        user = db.query(User).filter(User.email == email).first()
{% endif %}
        if not user or not self.verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")
        if not user.is_active:
            raise ValueError("User is inactive")
{% if project.registration_mode == 'email_verification' %}
        if not user.is_verified:
            raise ValueError("Email not verified")
{% elif project.registration_mode == 'admin_approval' %}
        if not user.is_approved:
            raise ValueError("Account pending approval")
{% endif %}
        return user
```

6. Add `import hashlib` is already covered above; now add `verify_email` (only under `email_verification` mode) and `verify_password_reset_token` (unconditional), placed after `decode_token` and before `get_current_user`:

```jinja
{% if registration_mode == 'email_verification' %}
    {{ 'async ' if is_async }}def verify_email(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, token: str) -> None:
        try:
            user_id = self.decode_token(token, expected_type="email_verification")
        except HTTPException:
            raise ValueError("Invalid or expired token")
{% if is_async %}
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
{% else %}
        user = db.query(User).filter(User.id == user_id).first()
{% endif %}
        if user is None:
            raise ValueError("Invalid or expired token")
        user.is_verified = True
{% if is_async %}
        await db.commit()
{% else %}
        db.commit()
{% endif %}
{% endif %}

    {{ 'async ' if is_async }}def verify_password_reset_token(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, token: str) -> int:
        """Decodes the token, then looks up the CURRENT password_hash for the
        token's own subject user (never a caller-supplied hash) to compare
        against the embedded fingerprint - the method owns its own DB lookup
        specifically so the caller never has to know which user a token
        belongs to before calling this, which is the whole point of a
        password-reset flow: the token itself carries that information.
        """
        try:
            payload = self.decode_token(token, expected_type="password_reset", return_payload=True)
        except HTTPException:
            raise ValueError("Invalid or expired token")
        user_id = int(payload["sub"])
{% if is_async %}
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
{% else %}
        user = db.query(User).filter(User.id == user_id).first()
{% endif %}
        if user is None:
            raise ValueError("Invalid or expired token")
        expected_fp = hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]
        if payload.get("pwd_fp") != expected_fp:
            raise ValueError("Invalid or expired token")
        return user_id
```

**Interface note (binding, not optional):** `verify_password_reset_token` takes `(self, db, token)`, not `(self, token, current_password_hash)` — it does its own DB lookup of the token's subject user internally, rather than requiring the caller to already know which user a token belongs to (which the caller can't know without decoding the token first). Every caller of this method — Task 6's `reset-password` route, and every test in this task and Task 7/8 — must use this exact signature.

(Same `project.registration_mode` correction applies to the `{% if registration_mode == 'email_verification' %}` line above — write `project.registration_mode`.)

7. Modify `decode_token` to support the optional payload return, WITHOUT changing its default behavior for existing callers:

```jinja
    def decode_token(self, token: str, expected_type: str = "access", return_payload: bool = False):
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        subject = payload.get("sub")
        if subject is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        if payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Expected a {expected_type} token",
            )
        if return_payload:
            return payload
        return int(subject)
```

(This drops the explicit `-> int` return type annotation on `decode_token`, since it can now return either `int` or `dict` — leave it unannotated, or annotate as `Union[int, dict]` if you prefer; either is fine, just be consistent and don't claim `-> int` when `return_payload=True` can be passed.)

8. Add the admin methods (gated on `rbac_enabled`, `approve_user` additionally gated on `registration_mode == 'admin_approval'`), placed after `get_current_user`, before the module-level singleton code:

```jinja
{% if project.rbac_enabled %}
    {{ 'async ' if is_async }}def list_users(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, skip: int = 0, limit: int = 100) -> List[User]:
{% if is_async %}
        result = await db.execute(select(User).offset(skip).limit(limit))
        return list(result.scalars().all())
{% else %}
        return db.query(User).offset(skip).limit(limit).all()
{% endif %}

    {{ 'async ' if is_async }}def get_user(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, user_id: int) -> Optional[User]:
{% if is_async %}
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
{% else %}
        return db.query(User).filter(User.id == user_id).first()
{% endif %}

    {{ 'async ' if is_async }}def set_user_roles(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, user_id: int, roles: List[str]) -> Optional[User]:
        allowed = {{ project.rbac_roles|tojson }}
        unknown = [r for r in roles if r not in allowed]
        if unknown:
            raise ValueError(f"Unknown role(s): {', '.join(unknown)} — declared roles are: {', '.join(allowed)}")
        user = {{ 'await ' if is_async }}self.get_user(db, user_id)
        if user is None:
            return None
        user.roles = roles
{% if is_async %}
        await db.commit()
        await db.refresh(user)
{% else %}
        db.commit()
        db.refresh(user)
{% endif %}
        return user

    {{ 'async ' if is_async }}def deactivate_user(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, user_id: int) -> Optional[User]:
        user = {{ 'await ' if is_async }}self.get_user(db, user_id)
        if user is None:
            return None
        user.is_active = False
{% if is_async %}
        await db.commit()
        await db.refresh(user)
{% else %}
        db.commit()
        db.refresh(user)
{% endif %}
        return user

    {{ 'async ' if is_async }}def reactivate_user(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, user_id: int) -> Optional[User]:
        user = {{ 'await ' if is_async }}self.get_user(db, user_id)
        if user is None:
            return None
        user.is_active = True
{% if is_async %}
        await db.commit()
        await db.refresh(user)
{% else %}
        db.commit()
        db.refresh(user)
{% endif %}
        return user

{% if project.registration_mode == 'admin_approval' %}
    {{ 'async ' if is_async }}def approve_user(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, user_id: int) -> Optional[User]:
        user = {{ 'await ' if is_async }}self.get_user(db, user_id)
        if user is None:
            return None
        user.is_approved = True
{% if is_async %}
        await db.commit()
        await db.refresh(user)
{% else %}
        db.commit()
        db.refresh(user)
{% endif %}
        return user
{% endif %}
{% endif %}
```

9. Wire the email-sending calls into `register_user` (for `email_verification` mode) — modify the existing `register_user` method's tail, right before `return user`:

```jinja
        db.add(user)
{% if is_async %}
        await db.commit()
        await db.refresh(user)
{% else %}
        db.commit()
        db.refresh(user)
{% endif %}
{% if project.registration_mode == 'email_verification' %}
        token = self.create_email_verification_token(user.id)
        send_email(user.email, "Verify your email", f"Your verification token: {token}")
{% endif %}
        return user
```

10. Add the `from .email import send_email` import near the top of the file, alongside `from database.models import User` — but ONLY when it's actually needed (i.e., always, since forgot-password's route layer will need `create_password_reset_token` + `send_email` too — decide in Task 6 whether the route layer or the service layer calls `send_email` for the forgot-password case; per this task's scope, add the import unconditionally in `service.py.jinja` since `register_user` already needs it under `email_verification` mode and forgot-password's route (Task 6) will import it separately in `routes.py.jinja` if it orchestrates the send itself — do not gate this import on `registration_mode`, since `email.py.jinja` is unconditionally generated whenever `auth_enabled`, per the Global Constraints).

In `backend/services/code_generator.py`, add `email.py` generation next to the three existing auth-module file writes (around the current lines 279-281):

```python
            self._write_file(auth_dir / "schemas.py", self._render_template("Python/auth/schemas.py.jinja", context))
            self._write_file(auth_dir / "service.py", self._render_template("Python/auth/service.py.jinja", context))
            self._write_file(auth_dir / "routes.py", self._render_template("Python/auth/routes.py.jinja", context))
            self._write_file(auth_dir / "email.py", self._render_template("Python/auth/email.py.jinja", context))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_auth_expansion_generation.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Render and read the output by hand**

Run (use the scratchpad temp directory instead of `/tmp` if `/tmp` is unreliable on this Windows environment, per this session's established convention):
```bash
uv run backstudio generate backend/tests/fixtures/erd/auth_email_verification.yml --output /tmp/rc_auth_task4a --force
uv run backstudio generate backend/tests/fixtures/erd/auth_admin_approval.yml --output /tmp/rc_auth_task4b --force
uv run backstudio generate backend/tests/fixtures/erd/shophub_mini.yml --output /tmp/rc_auth_task4c --force
```
Read `modules/auth/service.py`, `modules/auth/email.py`, and `config.py` in full for all three. Confirm: the `email_verification` render has `create_email_verification_token`/`verify_email` and the `is_verified` check, no `is_approved`/`approve_user` anywhere; the `admin_approval` render has `approve_user` and the `is_approved` check, no `create_email_verification_token`/`verify_email` anywhere; the `shophub_mini.yml` (open mode, rbac enabled) render has all 5 admin methods, `create_password_reset_token`/`verify_password_reset_token` (unconditional), but no mode-gated methods at all and no `is_verified`/`is_approved` checks in `authenticate_user`. `py_compile` all three renders' `service.py`/`email.py`/`config.py`.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/auth/service.py.jinja backend/templates/Python/auth/email.py.jinja backend/templates/Python/config.py.jinja backend/services/code_generator.py backend/tests/test_auth_expansion_generation.py
git commit -m "Add admin methods, registration-gating checks, and forgot/reset-password to AuthService"
```

---

### Task 5: `auth/schemas.py.jinja` — all new/changed schemas

**Files:**
- Modify: `backend/templates/Python/auth/schemas.py.jinja`
- Test: `backend/tests/test_auth_expansion_generation.py`

**Interfaces:**
- Consumes: `registration_mode` (Task 3).
- Produces: `SetUserRolesRequest`/`ForgotPasswordRequest`/`ResetPasswordRequest`/`MessageResponse` (unconditional), `VerifyEmailRequest`/`ResendVerificationRequest` (email_verification mode only); `UserResponse` gains `is_verified`/`is_approved` (mode-gated) — consumed by Task 6 (routes).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_auth_expansion_generation.py`:

```python
def test_unconditional_new_schemas_always_present(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # open mode
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "auth" / "schemas.py").read_text(encoding="utf-8")
    ast.parse(schemas_src)
    assert "class SetUserRolesRequest(BaseModel):" in schemas_src
    assert "class ForgotPasswordRequest(BaseModel):" in schemas_src
    assert "class ResetPasswordRequest(BaseModel):" in schemas_src
    assert "class MessageResponse(BaseModel):" in schemas_src

    # open mode: email_verification-only schemas must be absent
    assert "class VerifyEmailRequest(BaseModel):" not in schemas_src
    assert "class ResendVerificationRequest(BaseModel):" not in schemas_src

    # open mode: UserResponse must not have is_verified/is_approved
    resp_start = schemas_src.index("class UserResponse(")
    resp_src = schemas_src[resp_start:]
    assert "is_verified" not in resp_src
    assert "is_approved" not in resp_src


def test_email_verification_mode_schemas(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "auth" / "schemas.py").read_text(encoding="utf-8")
    ast.parse(schemas_src)
    assert "class VerifyEmailRequest(BaseModel):" in schemas_src
    assert "class ResendVerificationRequest(BaseModel):" in schemas_src

    resp_start = schemas_src.index("class UserResponse(")
    resp_end = schemas_src.index("\n    class Config:", resp_start)
    resp_src = schemas_src[resp_start:resp_end]
    assert "is_verified: bool" in resp_src
    assert "is_approved" not in resp_src


def test_admin_approval_mode_user_response_schema(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "auth" / "schemas.py").read_text(encoding="utf-8")
    resp_start = schemas_src.index("class UserResponse(")
    resp_end = schemas_src.index("\n    class Config:", resp_start)
    resp_src = schemas_src[resp_start:resp_end]
    assert "is_approved: bool" in resp_src
    assert "is_verified" not in resp_src

    # admin_approval mode has no email flow - these two must still be absent
    assert "class VerifyEmailRequest(BaseModel):" not in schemas_src
    assert "class ResendVerificationRequest(BaseModel):" not in schemas_src


def test_reset_password_request_enforces_min_length(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "auth" / "schemas.py").read_text(encoding="utf-8")
    reset_start = schemas_src.index("class ResetPasswordRequest(")
    reset_end = schemas_src.index("\n\n\n", reset_start)
    reset_src = schemas_src[reset_start:reset_end]
    assert "min_length=8" in reset_src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_auth_expansion_generation.py -k "schema" -v`
Expected: FAIL — none of these classes exist yet.

- [ ] **Step 3: Implement**

Full new file for `backend/templates/Python/auth/schemas.py.jinja`:

```jinja
"""{{ project.name }} - Auth schemas"""

from typing import List
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class SetUserRolesRequest(BaseModel):
    roles: List[str]


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


{% if project.registration_mode == 'email_verification' %}
class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


{% endif %}
class UserResponse(BaseModel):
    id: int
    email: str
    roles: List[str] = []
    is_active: bool
{% if project.registration_mode == 'email_verification' %}
    is_verified: bool
{% elif project.registration_mode == 'admin_approval' %}
    is_approved: bool
{% endif %}

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_auth_expansion_generation.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Render and read the output by hand**

Render the same three fixtures as Task 4 and read `modules/auth/schemas.py` in full for each. Confirm the mode-gated classes appear only where expected, `UserResponse` has exactly the right extra field per mode (or neither), and `valid_minimal.yml`'s render (no auth at all) is completely unaffected (no `modules/auth/` directory generated at all — this should already be true from before this task, confirm it still is). `py_compile` all three.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/auth/schemas.py.jinja backend/tests/test_auth_expansion_generation.py
git commit -m "Add admin/registration-gating/forgot-reset schemas to auth/schemas.py.jinja"
```

---

### Task 6: `auth/routes.py.jinja` — all new/changed routes

**Files:**
- Modify: `backend/templates/Python/auth/routes.py.jinja`
- Test: `backend/tests/test_auth_expansion_generation.py` (generation-level), `backend/tests/test_generated_project_runtime.py` (real HTTP)

**Interfaces:**
- Consumes: `registration_mode`, `rbac_enabled` (Task 3); the new `AuthService` methods (Task 4); the new schemas (Task 5).
- Produces: `POST /auth/verify-email`, `POST /auth/resend-verification` (email_verification only), `POST /auth/forgot-password`, `POST /auth/reset-password` (unconditional), `GET /users`, `GET /users/{id}`, `PUT /users/{id}/roles`, `POST /users/{id}/deactivate`, `POST /users/{id}/reactivate` (rbac_enabled only), `POST /users/{id}/approve` (rbac_enabled AND admin_approval).

**This is the second-highest-risk task in the plan** (two independent gating axes compose: `registration_mode` and `rbac_enabled`). Needs both generation-level tests and real-HTTP tests, especially for the enumeration-safety requirement.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_auth_expansion_generation.py`:

```python
def test_email_verification_mode_routes_present_admin_routes_absent(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")  # also rbac.enabled: true
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert '"/verify-email"' in routes_src
    assert '"/resend-verification"' in routes_src
    assert '"/forgot-password"' in routes_src
    assert '"/reset-password"' in routes_src
    assert '"/users"' in routes_src  # rbac.enabled is true on this fixture too
    assert '"/users/{user_id}/approve"' not in routes_src  # not admin_approval mode


def test_admin_approval_mode_approve_route_present(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    assert '"/users/{user_id}/approve"' in routes_src
    assert '"/verify-email"' not in routes_src
    assert '"/resend-verification"' not in routes_src
    # forgot/reset-password is unconditional regardless of mode
    assert '"/forgot-password"' in routes_src
    assert '"/reset-password"' in routes_src


def test_open_mode_no_rbac_has_only_forgot_reset(tmp_path):
    from backend.erd.schema import ERDConfig, ProjectMeta, DatabaseSpec, AuthSpec, EntitySpec, ServiceDecl
    from backend.schemas.data import ModelField, FieldType

    erd = ERDConfig(
        project=ProjectMeta(name="OpenNoRbac", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="o.db"),
        auth=AuthSpec(enabled=True),
        entities=[
            EntitySpec(name="Widget", fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]),
        ],
        services=[ServiceDecl(name="widgets", entities=["Widget"])],
    )
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert '"/forgot-password"' in routes_src
    assert '"/reset-password"' in routes_src
    assert '"/verify-email"' not in routes_src
    assert '"/users"' not in routes_src
    assert "require_roles" not in routes_src
    assert "from rbac import require_roles" not in routes_src


def test_admin_routes_gated_with_require_roles_admin(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    assert "from rbac import require_roles" in routes_src
    list_start = routes_src.index('"/users"')
    list_block = routes_src[list_start:list_start + 400]
    assert 'dependencies=[Depends(require_roles("admin"))]' in list_block


def test_list_users_route_has_pagination_query_params(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    list_start = routes_src.index("def list_users_route(")
    list_end = routes_src.index("\n@router.get", list_start)
    list_src = routes_src[list_start:list_end]
    assert "skip: int = Query(0, ge=0)" in list_src
    assert "limit: int = Query(100, ge=1, le=500)" in list_src
```

Add to `backend/tests/test_generated_project_runtime.py` (read the file's existing conventions first):

```python
def test_admin_user_management_403_then_200_round_trip(tmp_path, monkeypatch, isolated_sys_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "admin_routes_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            assert set(admin_resp.json()["roles"]) == {"admin", "customer"}  # bootstrap
            admin_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'admin@example.com', 'password': 'supersecret123'}).json()['access_token']}"}

            cust_resp = client.post("/auth/register", json={"email": "cust@example.com", "password": "supersecret123"})
            assert cust_resp.json()["roles"] == []
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.execute("UPDATE users SET roles = '[\"customer\"]' WHERE email = 'cust@example.com'")
            conn.commit()
            conn.close()
            cust_login = client.post("/auth/login", json={"email": "cust@example.com", "password": "supersecret123"})
            cust_headers = {"Authorization": f"Bearer {cust_login.json()['access_token']}"}
            cust_id = cust_resp.json()["id"]

            # non-admin gets 403 on every admin endpoint
            assert client.get("/users", headers=cust_headers).status_code == 403
            assert client.get(f"/users/{cust_id}", headers=cust_headers).status_code == 403
            assert client.put(f"/users/{cust_id}/roles", json={"roles": ["admin"]}, headers=cust_headers).status_code == 403
            assert client.post(f"/users/{cust_id}/deactivate", headers=cust_headers).status_code == 403

            # admin succeeds on all of them
            list_resp = client.get("/users", headers=admin_headers)
            assert list_resp.status_code == 200
            assert cust_id in [u["id"] for u in list_resp.json()]

            get_resp = client.get(f"/users/{cust_id}", headers=admin_headers)
            assert get_resp.status_code == 200
            assert get_resp.json()["id"] == cust_id

            roles_resp = client.put(f"/users/{cust_id}/roles", json={"roles": ["admin", "customer"]}, headers=admin_headers)
            assert roles_resp.status_code == 200
            assert set(roles_resp.json()["roles"]) == {"admin", "customer"}

            bad_roles_resp = client.put(f"/users/{cust_id}/roles", json={"roles": ["not_a_real_role"]}, headers=admin_headers)
            assert bad_roles_resp.status_code == 400

            deact_resp = client.post(f"/users/{cust_id}/deactivate", headers=admin_headers)
            assert deact_resp.status_code == 200
            assert deact_resp.json()["is_active"] is False

            react_resp = client.post(f"/users/{cust_id}/reactivate", headers=admin_headers)
            assert react_resp.status_code == 200
            assert react_resp.json()["is_active"] is True

            assert client.get("/users/999999", headers=admin_headers).status_code == 404


def test_forgot_password_and_resend_verification_are_enumeration_safe(tmp_path, monkeypatch, isolated_sys_path):
    """The one test that would catch a status-code or body-shape leak of
    'does this email exist' - the single most important correctness property
    Task 6 must preserve.
    """
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "enum_safe_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            client.post("/auth/register", json={"email": "real@example.com", "password": "supersecret123"})

            real_resp = client.post("/auth/forgot-password", json={"email": "real@example.com"})
            fake_resp = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
            assert real_resp.status_code == fake_resp.status_code == 200
            assert real_resp.json() == fake_resp.json()

            real_resend = client.post("/auth/resend-verification", json={"email": "real@example.com"})
            fake_resend = client.post("/auth/resend-verification", json={"email": "nobody@example.com"})
            assert real_resend.status_code == fake_resend.status_code == 200
            assert real_resend.json() == fake_resend.json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_auth_expansion_generation.py -k "route" backend/tests/test_generated_project_runtime.py -k "admin_user_management or enumeration_safe" -v`
Expected: FAIL — none of this exists in `routes.py.jinja` yet.

- [ ] **Step 3: Implement**

In `backend/templates/Python/auth/routes.py.jinja`, apply these changes on top of the current file:

1. Add `Query` to the existing `from fastapi import APIRouter, Depends, HTTPException, status` import, making it `from fastapi import APIRouter, Depends, HTTPException, Query, status`.
2. Extend the `.schemas` import with the new classes:
```jinja
from .schemas import (
    ForgotPasswordRequest, MessageResponse, RefreshRequest, ResetPasswordRequest,
    SetUserRolesRequest, TokenResponse, UserLogin, UserRegister, UserResponse,
{% if project.registration_mode == 'email_verification' %}
    ResendVerificationRequest, VerifyEmailRequest,
{% endif %}
)
```
3. Add `from rbac import require_roles` right after the existing `from .service import AuthService, get_{{ project.auth_module_name }}_service` line, gated:
```jinja
{% if project.rbac_enabled %}
from rbac import require_roles
{% endif %}
```
4. After the existing `/me` route, add (all four unconditional, whenever `auth_enabled` — which is implied by being in this file at all). Note `reset_password` calls `service.verify_password_reset_token(db, payload.token)` — per Task 4's binding interface note, this method does its own internal lookup of the token's subject user; the route never needs to know which user a token belongs to before calling it:
```jinja
@router.post("/forgot-password", response_model=MessageResponse)
{{ 'async ' if is_async }}def forgot_password(
    payload: ForgotPasswordRequest,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> MessageResponse:
{% if is_async %}
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
{% else %}
    user = db.query(User).filter(User.email == payload.email).first()
{% endif %}
    if user is not None:
        token = service.create_password_reset_token(user.id, user.password_hash)
        from .email import send_email
        send_email(user.email, "Reset your password", f"Your password reset token: {token}")
    return MessageResponse(message="If that email is registered, a password reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
{{ 'async ' if is_async }}def reset_password(
    payload: ResetPasswordRequest,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> MessageResponse:
    try:
        user_id = {{ 'await ' if is_async }}service.verify_password_reset_token(db, payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    new_hash = service.hash_password(payload.new_password)
{% if is_async %}
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
{% else %}
    user = db.query(User).filter(User.id == user_id).first()
{% endif %}
    user.password_hash = new_hash
{% if is_async %}
    await db.commit()
{% else %}
    db.commit()
{% endif %}
    return MessageResponse(message="Password reset successfully.")
```

5. Add (email_verification mode only):
```jinja
{% if project.registration_mode == 'email_verification' %}
@router.post("/verify-email", response_model=MessageResponse)
{{ 'async ' if is_async }}def verify_email_route(
    payload: VerifyEmailRequest,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> MessageResponse:
    try:
        {{ 'await ' if is_async }}service.verify_email(db, payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return MessageResponse(message="Email verified.")


@router.post("/resend-verification", response_model=MessageResponse)
{{ 'async ' if is_async }}def resend_verification(
    payload: ResendVerificationRequest,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> MessageResponse:
{% if is_async %}
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
{% else %}
    user = db.query(User).filter(User.email == payload.email).first()
{% endif %}
    if user is not None and not user.is_verified:
        token = service.create_email_verification_token(user.id)
        from .email import send_email
        send_email(user.email, "Verify your email", f"Your verification token: {token}")
    return MessageResponse(message="If that email is registered and unverified, a verification link has been sent.")
{% endif %}
```

(Note: `select` is already imported when `is_async` — but the sync branch's `db.query(User)` calls above need `User` to already be imported, which it already is at the top of the current file. If `is_async`, `select` is likewise already imported at the top. No new imports needed for these route bodies beyond what's added in steps 1-3.)

6. Add the admin routes (gated on `rbac_enabled`; `approve` additionally gated on `admin_approval`), at the end of the file:
```jinja
{% if project.rbac_enabled %}
@router.get("/users", response_model=List[UserResponse], dependencies=[Depends(require_roles("admin"))])
{{ 'async ' if is_async }}def list_users_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> List[UserResponse]:
    return {{ 'await ' if is_async }}service.list_users(db, skip=skip, limit=limit)


@router.get("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(require_roles("admin"))])
{{ 'async ' if is_async }}def get_user_route(
    user_id: int,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> UserResponse:
    user = {{ 'await ' if is_async }}service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/users/{user_id}/roles", response_model=UserResponse, dependencies=[Depends(require_roles("admin"))])
{{ 'async ' if is_async }}def set_user_roles_route(
    user_id: int,
    payload: SetUserRolesRequest,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> UserResponse:
    try:
        user = {{ 'await ' if is_async }}service.set_user_roles(db, user_id, payload.roles)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/users/{user_id}/deactivate", response_model=UserResponse, dependencies=[Depends(require_roles("admin"))])
{{ 'async ' if is_async }}def deactivate_user_route(
    user_id: int,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> UserResponse:
    user = {{ 'await ' if is_async }}service.deactivate_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/users/{user_id}/reactivate", response_model=UserResponse, dependencies=[Depends(require_roles("admin"))])
{{ 'async ' if is_async }}def reactivate_user_route(
    user_id: int,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> UserResponse:
    user = {{ 'await ' if is_async }}service.reactivate_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


{% if project.registration_mode == 'admin_approval' %}
@router.post("/users/{user_id}/approve", response_model=UserResponse, dependencies=[Depends(require_roles("admin"))])
{{ 'async ' if is_async }}def approve_user_route(
    user_id: int,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> UserResponse:
    user = {{ 'await ' if is_async }}service.approve_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
{% endif %}
{% endif %}
```

(This block needs `List` imported from `typing` — add `from typing import List` near the top of the file if not already present; it is not, per the current file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_auth_expansion_generation.py backend/tests/test_generated_project_runtime.py -v`
Expected: PASS, all tests (existing + new).

- [ ] **Step 5: Render and read the output by hand**

Render the same fixtures as Tasks 4-5 plus the ad-hoc "open mode, no rbac" config used in `test_open_mode_no_rbac_has_only_forgot_reset`. Read every `routes.py` in full for each. Confirm: `require_roles`/admin routes only appear when `rbac_enabled`; `verify-email`/`resend-verification` only appear under `email_verification`; `approve` only appears when BOTH `rbac_enabled` AND `admin_approval`; `forgot-password`/`reset-password` appear in every render (any mode, any rbac state) whenever `auth_enabled`. `py_compile` every render.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/auth/routes.py.jinja backend/tests/test_auth_expansion_generation.py backend/tests/test_generated_project_runtime.py
git commit -m "Add admin/registration-gating/forgot-reset routes to auth/routes.py.jinja"
```

---

### Task 7: Real HTTP+DB round-trip tests, sync

**Files:**
- Modify: `backend/tests/test_generated_project_runtime.py`

**Interfaces:** none new — this task proves Tasks 1-6's mechanism works end-to-end over real HTTP against a real generated app, for every scenario not already covered by Task 4's live-DB (service-layer, not HTTP-layer) tests or Task 6's admin/enumeration-safety tests.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_generated_project_runtime.py`:

```python
def test_full_email_verification_flow_over_http(tmp_path, monkeypatch, isolated_sys_path, capfd):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "email_verif_http_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import re

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            register_resp = client.post("/auth/register", json={"email": "eve@example.com", "password": "supersecret123"})
            assert register_resp.status_code == 201, register_resp.text

            login_resp = client.post("/auth/login", json={"email": "eve@example.com", "password": "supersecret123"})
            assert login_resp.status_code == 401, login_resp.text  # unverified

            captured = capfd.readouterr()
            match = re.search(r"Your verification token: (\S+)", captured.out)
            assert match, f"no verification token found in captured stdout: {captured.out}"
            token = match.group(1)

            verify_resp = client.post("/auth/verify-email", json={"token": token})
            assert verify_resp.status_code == 200, verify_resp.text

            login_resp2 = client.post("/auth/login", json={"email": "eve@example.com", "password": "supersecret123"})
            assert login_resp2.status_code == 200, login_resp2.text

            bad_verify_resp = client.post("/auth/verify-email", json={"token": "garbage"})
            assert bad_verify_resp.status_code == 400


def test_full_admin_approval_flow_over_http(tmp_path, monkeypatch, isolated_sys_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "admin_approval_http_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            assert set(admin_resp.json()["roles"]) == {"admin", "customer"}  # bootstrap gets every role AND is auto-approved? see below
            admin_id = admin_resp.json()["id"]

            # the bootstrap admin (first user) still needs approval like anyone else under
            # admin_approval mode - registration and role-bootstrap are orthogonal to approval
            login_before = client.post("/auth/login", json={"email": "admin@example.com", "password": "supersecret123"})
            assert login_before.status_code == 401, login_before.text

            # approve the admin directly via the DB (no bootstrap approval mechanism exists -
            # this mirrors how other tests in this suite grant a role via direct SQL when no
            # endpoint yet exists to do it through the API)
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.execute("UPDATE users SET is_approved = 1 WHERE id = ?", (admin_id,))
            conn.commit()
            conn.close()

            admin_login = client.post("/auth/login", json={"email": "admin@example.com", "password": "supersecret123"})
            assert admin_login.status_code == 200, admin_login.text
            admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

            pending_resp = client.post("/auth/register", json={"email": "pending@example.com", "password": "supersecret123"})
            assert pending_resp.status_code == 201, pending_resp.text
            pending_id = pending_resp.json()["id"]
            assert pending_resp.json()["is_approved"] is False

            pending_login = client.post("/auth/login", json={"email": "pending@example.com", "password": "supersecret123"})
            assert pending_login.status_code == 401, pending_login.text

            approve_resp = client.post(f"/users/{pending_id}/approve", headers=admin_headers)
            assert approve_resp.status_code == 200, approve_resp.text
            assert approve_resp.json()["is_approved"] is True

            pending_login2 = client.post("/auth/login", json={"email": "pending@example.com", "password": "supersecret123"})
            assert pending_login2.status_code == 200, pending_login2.text


def test_full_forgot_reset_password_flow_over_http(tmp_path, monkeypatch, isolated_sys_path, capfd):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "forgot_reset_http_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import re

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            client.post("/auth/register", json={"email": "frank@example.com", "password": "originalpass1"})

            forgot_resp = client.post("/auth/forgot-password", json={"email": "frank@example.com"})
            assert forgot_resp.status_code == 200, forgot_resp.text

            captured = capfd.readouterr()
            match = re.search(r"Your password reset token: (\S+)", captured.out)
            assert match, f"no reset token found in captured stdout: {captured.out}"
            token = match.group(1)

            reset_resp = client.post("/auth/reset-password", json={"token": token, "new_password": "newpassword2"})
            assert reset_resp.status_code == 200, reset_resp.text

            old_login = client.post("/auth/login", json={"email": "frank@example.com", "password": "originalpass1"})
            assert old_login.status_code == 401

            new_login = client.post("/auth/login", json={"email": "frank@example.com", "password": "newpassword2"})
            assert new_login.status_code == 200

            # reusing the SAME token a second time must fail - the single-use proof, now at the HTTP layer
            reuse_resp = client.post("/auth/reset-password", json={"token": token, "new_password": "thirdpassword3"})
            assert reuse_resp.status_code == 400, reuse_resp.text

            # a genuinely nonexistent email gets the identical generic response (already covered
            # by test_forgot_password_and_resend_verification_are_enumeration_safe in Task 6, not
            # re-asserted here to avoid duplicating that test's exact purpose)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_generated_project_runtime.py -k "email_verification_flow or admin_approval_flow or forgot_reset_password_flow" -v`
Expected: PASS (this task adds no new template code — if anything fails, that means a genuine defect in already-merged Tasks 1-6 code surfaced by composing everything together for the first time over real HTTP; diagnose and fix the actual template file, document it clearly, do not weaken the test).

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_generated_project_runtime.py
git commit -m "Add full HTTP+DB round-trip tests for email verification, admin approval, and forgot/reset password"
```

---

### Task 8: Async-mode round-trip test

**Files:**
- Create: `backend/tests/fixtures/erd/auth_expansion_async_full.yml`
- Modify: `backend/tests/test_generated_project_runtime.py`

**Interfaces:** none new — proves Tasks 1-7's mechanism works when `database.async_mode: true`. Nothing in this plan has been exercised against a real async engine yet.

**Why this matters, not just "more tests":** every mechanism in this plan branches on `is_async` in `service.py.jinja`/`routes.py.jinja` — this is exactly the class of gap the async-support plan's own Task 8 and the RLS plan's own Task 9 existed to close for those features (and each found or confirmed real things: async-support's final review caught a genuine async-only bug; RLS's did too). Take this task exactly as seriously.

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/erd/auth_expansion_async_full.yml` (combines admin endpoints + `admin_approval` mode + forgot/reset password + `async_mode: true` — chosen over `email_verification` mode because it exercises one more distinct code path, `approve_user`, that `email_verification` mode doesn't have; forgot/reset-password is exercised either way since it's unconditional):

```yaml
project:
  name: AuthExpansionAsyncFull
  version: "1.0.0"

database:
  type: sqlite
  database_name: auth_expansion_async_full.db
  async_mode: true

auth:
  enabled: true
  registration:
    mode: admin_approval

rbac:
  enabled: true
  roles: [admin, customer]
  default_permissions:
    create: [admin, customer]
    list: [admin, customer]
    read: [admin, customer]
    update: [admin, customer]
    delete: [admin]

entities:
  - name: Note
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: body, type: string}

services:
  - name: notes
    entities: [Note]
```

- [ ] **Step 2: Write the failing test**

Add to `backend/tests/test_generated_project_runtime.py`:

```python
def test_async_mode_auth_expansion_full_stack_round_trip(tmp_path, monkeypatch, isolated_sys_path, capfd):
    """auth_expansion_async_full.yml driven through real HTTP + a real aiosqlite
    DB - proves admin_approval gating, admin endpoints, and forgot/reset
    password all compose correctly through the full async stack, mirroring
    what the sync-path tests in Tasks 6-7 already proved individually.
    """
    erd = load_erd(f"{FIXTURES}/auth_expansion_async_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "auth_expansion_async_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import re
        import sqlite3

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            assert admin_resp.status_code == 201, admin_resp.text
            admin_id = admin_resp.json()["id"]

            conn = sqlite3.connect(str(db_path))
            conn.execute("UPDATE users SET is_approved = 1 WHERE id = ?", (admin_id,))
            conn.commit()
            conn.close()

            admin_login = client.post("/auth/login", json={"email": "admin@example.com", "password": "supersecret123"})
            assert admin_login.status_code == 200, admin_login.text
            admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

            # admin_approval flow
            pending_resp = client.post("/auth/register", json={"email": "pending@example.com", "password": "supersecret123"})
            pending_id = pending_resp.json()["id"]
            assert client.post("/auth/login", json={"email": "pending@example.com", "password": "supersecret123"}).status_code == 401

            approve_resp = client.post(f"/users/{pending_id}/approve", headers=admin_headers)
            assert approve_resp.status_code == 200, approve_resp.text

            assert client.post("/auth/login", json={"email": "pending@example.com", "password": "supersecret123"}).status_code == 200

            # admin endpoints
            list_resp = client.get("/users", headers=admin_headers)
            assert list_resp.status_code == 200
            assert {u["id"] for u in list_resp.json()} >= {admin_id, pending_id}

            # forgot/reset password
            forgot_resp = client.post("/auth/forgot-password", json={"email": "pending@example.com"})
            assert forgot_resp.status_code == 200
            captured = capfd.readouterr()
            match = re.search(r"Your password reset token: (\S+)", captured.out)
            assert match
            token = match.group(1)
            reset_resp = client.post("/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"})
            assert reset_resp.status_code == 200, reset_resp.text
            assert client.post("/auth/login", json={"email": "pending@example.com", "password": "brandnewpass1"}).status_code == 200

    # `with TestClient(...)` has already exited here, running the async lifespan
    # shutdown (await engine.dispose()) - reaching this line without a hang is
    # itself part of what this test proves, per the established precedent from
    # the async-support and RLS plans.
```

- [ ] **Step 3: Run test to verify it fails or passes for a real reason**

Run: `uv run pytest backend/tests/test_generated_project_runtime.py -k "async_mode_auth_expansion" -v`
Expected: either a real failure surfacing a genuine compositional defect in already-merged Tasks 1-7 code (fix the template, don't weaken the test), or a clean pass proving the prior tasks' async branches were correct all along. Either outcome is legitimate.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS. Watch the wall-clock and the process's actual exit — the same async-engine-disposal risk flagged throughout the async-support and RLS plans.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/erd/auth_expansion_async_full.yml backend/tests/test_generated_project_runtime.py
git commit -m "Add async-mode round-trip test for admin approval, admin endpoints, and forgot/reset password"
```

---

### Task 9: Documentation + backlog close-out

**Files:**
- Modify: `README.md`, `docs/superpowers/backlog.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Update the root README**

Read `README.md` in full first. Add a section documenting `auth.registration` (the three modes, what each requires/gates) and the four `jwt.*_expiration_minutes` fields, near the existing `auth:`/`jwt:` documentation (find it — the RLS plan's own Task 9 already added an RLS section nearby, giving a direct style precedent in the same file). Also document the new endpoints (admin user management, verify-email/resend-verification, forgot/reset-password) at whatever level of detail the README's existing endpoint documentation already uses (check what's there for the existing `/register`/`/login`/`/me` endpoints and match it — don't invent a heavier documentation style than what's already established).

Verify every claim against real generated output: render `auth_email_verification.yml`, `auth_admin_approval.yml`, and `shophub_mini.yml`, and read the actual rendered `routes.py`/`schemas.py`/`service.py` — don't write examples from memory, per this session's established convention (this caught a real doc inaccuracy in both the async-support and RLS plans' own final reviews).

- [ ] **Step 2: Close out the backlog item**

In `docs/superpowers/backlog.md`, find the "Spec 2 — Auth service expansion" item and check it off, appending a `Fixed <today's date>:` summary in the style of the other closed-out items (read a couple for the exact style — e.g. the RLS item's own close-out, immediately above this one in the file). Cover: what shipped (admin user management gated to a reserved `admin` role; registration gating with two mutually-exclusive modes; forgot/reset password; four independently configurable JWT lifetimes); the one notable technical finding worth calling out — the single-use password-reset-token mechanism (a stateless JWT achieving genuine single-use semantics via a SHA256-truncated fingerprint of the current password hash, looked up by the token's own decoded subject user, no new DB table and no caller-supplied hash); a pointer to the spec (`docs/superpowers/specs/2026-09-10-auth-expansion-design.md`) and this plan file.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/backlog.md
git commit -m "Document auth.registration/JWT lifetimes/new endpoints in README, close out the Spec 2 backlog item"
```

---

## Final whole-branch review

Once all 9 tasks are complete and individually reviewed clean, dispatch a final, broad review on the most capable available model, per `superpowers:subagent-driven-development`'s standard closing step — reviewing the *whole* diff for cross-task composition issues no single task's review could see. Specific things worth checking: does every caller of `verify_password_reset_token` use its `(self, db, token)` signature consistently (Task 4 defines it, Task 6's route and Tasks 7-8's tests all consume it — confirm none reverted to an older, caller-supplied-hash shape); does the `decode_token` HTTPException-vs-ValueError wrapping get applied correctly at both of the two call sites that need it (`verify_email`, `verify_password_reset_token`), not just one; does `registration_mode`/`rbac_enabled`'s two independent gating axes ever produce an inconsistent combination in the generated output (e.g. an `approve` route with no corresponding service method, or vice versa) for any fixture shape this plan's own fixtures don't happen to cover; is the enumeration-safety property genuinely preserved end-to-end, not just at the one layer each task's own tests happened to check. This is exactly the kind of review that caught a real Critical bug in the RLS plan's own final pass (a bypass-role caller silently writing a NULL owner) — budget for at least one fix round afterward, same as that plan's precedent.
