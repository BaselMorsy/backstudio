# Fixing the 4 Issues Found While Building Example Showcases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all four issues documented in `examples/ISSUES.md` and specced
in the linked spec: unescaped free-text fields breaking generated Python;
add an opt-in RLS `read_scope` for "public read, owner-only write"; support
`bypass_roles` on header-identity RLS; add an opt-in per-service URL
`prefix`.

**Architecture:** Four independent, additive/corrective fixes, executed in
this order for git-history clarity (not because of any hard dependency
between them): Issue 1 (escaping) touches template/filter code with no
schema change; Issues 2 and 3 both touch `module_routes.py.jinja`'s RLS
route bodies, sequenced back-to-back so neither task's dispatch describes a
version of that file the other has already changed out from under it;
Issue 4 touches `translate.py`/`schema.py`/docs, unrelated to RLS.

**Tech Stack:** Python 3.11/3.12, Jinja2, Pydantic v2, FastAPI, SQLAlchemy
2.0, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-09-11-examples-issues-fixes-design.md`

## Global Constraints

**Every fix here is additive or purely corrective — no task should ever
need to change an existing fixture's assertions.** If implementing a task
makes you think an existing fixture/test needs its expected behavior
changed (not just a new import or a new field added), stop: that means
something about your understanding of the "before" state is wrong, not
that the fixture is stale. Re-read the real current file and this plan's
Global Constraints before proceeding. (Contrast with several earlier plans
in this repo's history, where a genuinely-missed retroactive break WAS the
right call to fix — that is not expected to happen anywhere in this plan;
if it does, treat it as a signal to stop and re-verify, not to proceed.)

**Verification discipline, as always in this repo's history:** every
literal code/template excerpt below was read from the live file while this
plan was written (not from the spec's own prose, which itself was written
slightly earlier and has one known drift — see "Correction vs. the spec"
below). Still, read each file yourself before editing it — drift between
plan-writing time and task-execution time has happened before in this
repo's history (that's exactly why this instruction repeats in every plan).

### Correction vs. the spec (read before starting Task 4)

The spec's Section 6.2 assumed `translate.py` already has an entity→service
lookup available at the point `base_path` is computed, reused from the
`modules`-building logic. **This is not true.** `crud_entities` (which
computes `base_path`, in the function containing `translate()`'s main body)
is built in a loop that runs *before* `_resolve_modules()` is ever called
— `_resolve_modules()` (lines 390-401) is what maps `erd.services` to
entities, and it runs at line 475, well after the `crud_entities` loop at
lines 458-473 has already finished. There is no existing entity→service
mapping in scope at the point `base_path` needs it. Task 4 must build a
small, new `entity_name -> service.prefix` lookup dict from `erd.services`
directly (a 3-line loop, not a big new module) immediately before the
`crud_entities` loop, not "reuse" something that doesn't exist yet at that
point in the function.

### Exact current locations (verified live, at plan-writing time)

- **`app/erd/schema.py`**: `RLSSpec` (no `read_scope` yet) at lines 135-137;
  `ServiceDecl` (no `prefix` yet) at lines 178-192; `ProjectMeta` (the only
  other free-text field beyond `RLSSpec`/`ServiceDecl` additions —
  `description: Optional[str] = None`, `name: str = Field(..., min_length=1)`)
  at lines 61-64; `ModelField.default: Optional[Any]` at line 45 (a third,
  less obvious free-text vector for Task 1 — see Task 1's own section).
- **`app/erd/loader.py`**: `_validate_rls`, the header+`bypass_roles`
  rejection at lines 77-88 (to be removed); the `rbac.enabled`/unknown-role
  checks immediately after, lines 89-100 (stay, unconditional on identity
  source type already — verify this still reads that way, don't just trust
  this plan's line numbers after Task 3 starts editing this function).
- **`app/erd/translate.py`**: `crud_entities` loop and the `base_path` line
  (`entity.endpoints.base_path or f"/{plural_snake}"`) at lines 458-473,
  specifically line 465; `_resolve_modules` at lines 390-401 (do NOT edit
  this for Task 4 — it already works, it's just not where `base_path` is
  computed); `_resolve_rls` at lines 254-345 (Task 2 must find where `rls`
  becomes a dict here — `read_scope` needs adding to the two dict literals
  at lines 296-303 and 332-339 — both the root-owned and cascade-owned
  paths need it, since a cascade-owned entity's effective `rls` dict is
  copied from its root's).
- **`app/templates/Python/service/module_routes.py.jinja`**: the full,
  current content of this file is reproduced task-by-task below exactly as
  read at plan-writing time (233 lines) — Tasks 2 and 3 both quote the
  exact current lines they change.
- **`app/templates/Python/database/repo.py.jinja`**: the `owner_id:
  Optional[int] = None` / `if owner_id is not None:` filter mechanism
  (confirmed present, unconditional, for every RLS'd entity's read
  functions) — Task 2 needs zero changes here, verify this still holds
  before starting Task 2, don't just trust it unread.
- **`app/services/code_generator.py`**: the `to_python_value` Jinja filter
  (registered as `python_value`), lines 79-88 — `elif isinstance(value,
  str): return f"'{value}'"` — wraps a string in single quotes with **no
  escaping**, the same bug class as Issue 1's two known spots but via a
  different mechanism (a Python filter function, not raw Jinja
  interpolation) and needing a different fix (Python's own `repr()`, not
  Jinja's `tojson` — see Task 1).

## Task 1: Escape every free-text ERD field embedded in generated Python source

**Files:**
- Modify: `app/templates/Python/server.py.jinja`
- Modify: `app/templates/Python/config.py.jinja`
- Modify: `app/templates/Python/alembic/env.py.jinja`
- Modify: `app/templates/Python/auth/email.py.jinja`
- Modify: `app/templates/Python/auth/routes.py.jinja`
- Modify: `app/templates/Python/auth/schemas.py.jinja`
- Modify: `app/templates/Python/auth/service.py.jinja`
- Modify: `app/templates/Python/database/base.py.jinja`
- Modify: `app/templates/Python/database/models.py.jinja`
- Modify: `app/templates/Python/database/repo.py.jinja`
- Modify: `app/templates/Python/dependencies.py.jinja`
- Modify: `app/templates/Python/middleware.py.jinja`
- Modify: `app/templates/Python/rbac/dependency.py.jinja`
- Modify: `app/templates/Python/service/module_routes.py.jinja`
- Modify: `app/templates/Python/service/module_schemas.py.jinja`
- Modify: `app/templates/Python/service/module_service.py.jinja`
- Modify: `app/services/code_generator.py`
- Test: `app/tests/test_erd_translate.py` or a new
  `app/tests/test_generated_project_runtime.py` test (your call which file
  fits better — this repo's convention is fixture-generation-shape tests in
  the former, real-generate-and-boot tests in the latter; this test needs a
  real `generate()` + `compileall` pass, so it likely belongs in the latter)

**Interfaces:** none — this is a template-only, purely corrective fix. No
schema, loader, or translate.py change. Nothing downstream of these
templates changes shape.

- [ ] **Step 1: Fix the two known single-line double-quoted spots in `server.py.jinja`**

Read `app/templates/Python/server.py.jinja` in full first. Confirm the
current content at lines 35-36 and 83 matches (this plan quotes it exactly
as read at plan-writing time):

```jinja
    title="{{ project.name }}",
    description="{{ project.description or 'Generated by BackStudio' }}",
```

and, separately, line 83:

```jinja
        "name": "{{ project.name }}",
```

Change all three to use Jinja's `tojson` filter instead of a manually
quoted literal:

```jinja
    title={{ project.name|tojson }},
    description={{ (project.description or 'Generated by BackStudio')|tojson }},
```

```jinja
        "name": {{ project.name|tojson }},
```

`tojson` already renders its own surrounding quotes — do not wrap its
output in an additional `"..."` (that would double-quote it). This mirrors
the exact pattern already used elsewhere in this same file for embedding
`project.rbac_roles` (`{{ project.rbac_roles|tojson }}`) — read that
existing line for the precedent, then confirm your new lines follow it
exactly.

- [ ] **Step 2: Fix `config.py.jinja`'s two spots**

Read `app/templates/Python/config.py.jinja` in full first. Confirm the
current content at line 58:

```jinja
    APP_NAME: str = "{{ project.name }}"
```

and, separately, the database-URL default at line 38 — the *exact* current
text (this plan reproduces it as read at plan-writing time; re-verify,
since it's a long single line easy to mistype):

```jinja
        "{% if project.database_config.async_mode %}sqlite+aiosqlite{% else %}sqlite{% endif %}:///./{{ project.name|snake_case }}.db"  # Default to SQLite for easy testing
```

Line 38 is a genuinely distinct, third vulnerable spot found during this
plan's own audit (not one of the two named in `examples/ISSUES.md`): the
`snake_case` filter (`app/services/code_generator.py`'s `to_snake_case`)
only inserts underscores before capital letters and lowercases the result
— it does **not** strip or escape any character, so a `project.name`
containing a `"` still contains that `"` after `|snake_case`, still inside
a double-quoted literal. Verify this yourself by reading
`to_snake_case`'s actual implementation before fixing, don't take this
plan's characterization on faith.

Fix line 58 the same way as Step 1:

```jinja
    APP_NAME: str = {{ project.name|tojson }}
```

Fix line 38: wrap the whole f-string-shaped literal's *value* portion in a
Jinja expression using `tojson`, keeping the surrounding
`{% if %}...{% endif %}` scheme-selection logic intact — the cleanest way
is to build the scheme+name+`.db` string as one expression, then `tojson`
the whole thing:

```jinja
        {{ (("sqlite+aiosqlite" if project.database_config.async_mode else "sqlite") ~ ":///./" ~ project.name|snake_case ~ ".db")|tojson }}  # Default to SQLite for easy testing
```

(Jinja's `~` operator does string concatenation regardless of operand
type.) Read the surrounding lines before and after to confirm this
substitution doesn't break the enclosing Python syntax context (this line
is itself inside a larger string/default-value expression in
`config.py.jinja` — read enough context to be sure, don't edit line 38 in
isolation without seeing what it's part of).

- [ ] **Step 3: Fix every triple-quoted module docstring**

The following 15 lines (all `"""{{ project.name }} - ...text..."""`
module-level docstrings, confirmed via a repo-wide grep at plan-writing
time) are lower-risk than Steps 1-2 (a single `"` inside a triple-quoted
string doesn't break it — only 3+ consecutive quote characters, or a value
ending in a quote character positioned to merge with the closing `"""`,
would) but fix them anyway for correctness, since a value literally
containing `"""` or ending in `"` is still a real (if narrower) way to
break generation:

```
app/templates/Python/alembic/env.py.jinja:1
app/templates/Python/auth/email.py.jinja:1
app/templates/Python/auth/routes.py.jinja:1
app/templates/Python/auth/schemas.py.jinja:1
app/templates/Python/auth/service.py.jinja:1
app/templates/Python/config.py.jinja:1
app/templates/Python/database/base.py.jinja:1
app/templates/Python/database/models.py.jinja:1
app/templates/Python/database/repo.py.jinja:1
app/templates/Python/dependencies.py.jinja:1
app/templates/Python/middleware.py.jinja:1
app/templates/Python/rbac/dependency.py.jinja:1
app/templates/Python/server.py.jinja:1
app/templates/Python/service/module_routes.py.jinja:1
app/templates/Python/service/module_schemas.py.jinja:1
app/templates/Python/service/module_service.py.jinja:1
```

Re-run the grep yourself first (`grep -rn '"""{{ project.name' app/templates/Python/ --include="*.jinja"`)
to confirm this list is still exactly current before editing anything —
this plan's list is a snapshot from plan-writing time.

A triple-quoted docstring can't sensibly use `tojson` (that would produce
a JSON-quoted string *inside* a docstring, which is syntactically valid
but ugly and wrong — a docstring should contain the literal text, not a
quoted-string representation of it). Instead, replace the raw
interpolation with a Jinja `replace` filter that neutralizes the one
genuinely dangerous case (a value containing `"""`) by escaping embedded
double-quotes, matching how a docstring author would hand-escape this
themselves:

```jinja
"""{{ project.name|replace('"', '\\"') }} - Main server application"""
```

Apply the equivalent `|replace('"', '\\"')` to every one of the 16 lines
above (the module-level docstring's `{{ project.name }}` reference — some
of these lines also reference `{{ module.name }}`/`{{ project.auth_module_name }}`,
which are NOT free-text ERD fields (derived from `services[].name`, itself
already validated as a Python-identifier by `ServiceDecl.name_is_valid_python_identifier`
— leave those references unchanged, only touch `project.name`).

- [ ] **Step 4: Fix `to_python_value` in `app/services/code_generator.py`**

Read the function in full first (lines 79-88 at plan-writing time):

```python
        def to_python_value(value: Any) -> str:
            """Convert Python value to its string representation with correct syntax"""
            if isinstance(value, bool):
                return 'True' if value else 'False'
            elif isinstance(value, str):
                return f"'{value}'"
            elif value is None:
                return 'None'
            else:
                return str(value)
```

`ModelField.default: Optional[Any]` (an ERD-user-supplied field, e.g. a
string field's default value like `O'Brien` containing a single quote)
flows through this exact `elif isinstance(value, str): return f"'{value}'"`
branch with zero escaping, used in `database/models.py.jinja` (a SQLAlchemy
`Column(..., default=...)` argument) and `service/module_schemas.py.jinja`
(a Pydantic field default). This is the same bug class as Steps 1-3 but
needs a different fix — this is a plain Python function (registered as a
Jinja filter), not a Jinja template expression, so `tojson` isn't the
mechanism here. Use Python's own `repr()`, which correctly escapes quotes
and backslashes and picks single-vs-double quoting automatically to
minimize escaping — exactly the standard, idiomatic way to safely render a
Python string literal from Python code:

```python
        def to_python_value(value: Any) -> str:
            """Convert Python value to its string representation with correct syntax"""
            if isinstance(value, bool):
                return 'True' if value else 'False'
            elif isinstance(value, str):
                return repr(value)
            elif value is None:
                return 'None'
            else:
                return str(value)
```

- [ ] **Step 5: Confirm no other free-text ERD field exists**

Read `app/erd/schema.py` in full (it's ~250 lines, read all of it, not a
grep) and confirm the only free-text (arbitrary-string, not an enum/
identifier/numeric) fields a user can set that flow into generated source
are: `ProjectMeta.name`, `ProjectMeta.description`, and `ModelField.default`
(handled in Steps 1-2 and Step 4 above). Every other `str` field in the
schema (`ServiceDecl.name`, entity/field/relationship `name`s, etc.) is
already validated as a Python identifier or otherwise structurally
constrained by an existing `field_validator`/`model_validator` — confirm
this for at least `EntitySpec.name`, `RelationshipDecl.name`, and
`ModelField.name` by reading how each is actually used in the templates
(is it ever embedded raw in a string literal, or only used as a Python
identifier / attribute name, which Jinja's `snake_case`/`pascal_case`
filters at least somewhat constrain — though note Step 2 already showed
`snake_case` doesn't strip characters, so if any of these identifier-shaped
fields turn out to ALSO be embedded in a string-literal context anywhere,
flag it and extend this task's scope to cover it too, don't silently skip
it). Report what you found in your task report even if the answer is
"confirmed, nothing else needed fixing."

- [ ] **Step 6: New regression test proving the fix is real**

Add a new fixture, `app/tests/fixtures/erd/quote_stress.yml` (or reuse an
existing minimal fixture's shape — your call, but it must be a real,
loadable, valid ERD): a minimal ERD (one entity, no auth/rbac needed to
keep this focused) with `project.name` and `project.description` each
containing a literal `"`, a backslash `\`, and a non-ASCII character (e.g.
`é` or `→`) — and at least one `ModelField` with a string `type` and a
`default` value containing a literal `'` (single quote), to exercise
Step 4's fix too. Example shape (adapt as needed, this is illustrative, not
literal YAML to copy verbatim without checking it validates):

```yaml
project:
  name: "Quote\"Stress\\Test"
  version: "1.0.0"
  description: "A description with a \"quoted phrase\", a backslash \\, and unicode: café"

database:
  type: sqlite
  database_name: quote_stress.db

entities:
  - name: Item
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: label, type: string, default: "O'Brien's"}

services:
  - name: items
    entities: [Item]
```

Write a test (in `app/tests/test_generated_project_runtime.py`, matching
that file's existing generate-and-verify pattern) that: loads this fixture,
generates it, runs `python -m compileall` (or the equivalent programmatic
`compile()` check this repo's existing tests use — check how other tests
in this file already verify generated output compiles, reuse that exact
mechanism) against every generated `.py` file and asserts it succeeds; then
reads the actual rendered `server.py` and asserts the literal rendered
`title=`/`description=` lines contain properly-escaped Python (e.g. confirm
`ast.parse` or `compile()` on just that file succeeds, AND read the file
content to confirm the original quote/backslash/unicode characters are
still recoverable from the rendered value — not stripped, actually
correctly escaped) — proving the fix preserves the original content
correctly, not just "doesn't crash."

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest app/tests -q`
Expected: PASS, 254 (253 + this task's 1 new test — confirm the exact
current baseline count yourself first via a clean run before this task's
changes, don't assume 253 is still exactly right).

- [ ] **Step 8: Commit**

```bash
git add app/templates/Python/ app/services/code_generator.py app/tests/
git commit -m "Escape free-text ERD fields (project.name/description, field defaults) to prevent broken generated Python"
```

---

## Task 2: RLS `read_scope` — public read, owner-only write

**Files:**
- Modify: `app/erd/schema.py`
- Modify: `app/erd/translate.py`
- Modify: `app/templates/Python/service/module_routes.py.jinja`
- Test: new fixture under `app/tests/fixtures/erd/`, new tests in
  `app/tests/test_generated_project_runtime.py`

**Interfaces:**
- Produces: `RLSSpec.read_scope: Literal["owner", "any_authenticated"] = "owner"`
  — consumed by `translate.py` (propagated into the `rls` dict on every
  `data_models` entry) and by `module_routes.py.jinja` (read in the `list`/
  `read` route bodies as `entity.rls.read_scope`).
- Consumes: nothing new from other tasks.

- [ ] **Step 1: Add `read_scope` to `RLSSpec`**

Read `app/erd/schema.py` lines 135-137 first, confirm current content:

```python
class RLSSpec(BaseModel):
    identity_source: RLSIdentitySource
    bypass_roles: List[str] = Field(default_factory=list)
```

Change to:

```python
class RLSSpec(BaseModel):
    identity_source: RLSIdentitySource
    bypass_roles: List[str] = Field(default_factory=list)
    read_scope: Literal["owner", "any_authenticated"] = "owner"
```

(`Literal` is already imported at the top of this file — confirm, don't
add a duplicate import.)

- [ ] **Step 2: Wire `read_scope` through `translate.py`'s `_resolve_rls`**

Read `app/erd/translate.py`'s `_resolve_rls` function in full (lines
254-345 at plan-writing time) before editing. Two dict literals build the
`rls` structure attached to each model — the root-owned path (currently
lines 296-303) and the cascade-owned path (currently lines 332-339), which
copies fields from its resolved root/parent. Both need `read_scope` added,
since a cascade-owned entity's `rls` dict is a full copy propagated from
its root, not a separate resolution — `read_scope` is declared per-entity
on `RLSSpec`, but only the *root* owner entity's own `read_scope` should
apply to its whole ownership tree (a cascade-owned child entity's own
`rls:` block doesn't exist — `entity.rls` is `None` for cascade-owned
entities, per the existing `if entity.rls is None: continue` early-exit
pattern already in `_validate_rls`; verify this is also true in
`translate.py`'s own `_resolve_rls`, i.e. only root-owned entities have a
real `entity.rls` object to read `read_scope` from). Confirm this
understanding by reading the full function before making a change, then
add `"read_scope": entity.rls.read_scope,` to the root-owned dict literal
(next to the existing `"bypass_roles": list(entity.rls.bypass_roles),`
line) and `"read_scope": parent_rls["read_scope"],` to the cascade-owned
dict literal (next to the existing `"bypass_roles": parent_rls["bypass_roles"],`
line) — mirroring exactly how `bypass_roles` itself is already threaded
through both paths, since `read_scope` needs identical propagation
semantics.

- [ ] **Step 3: Change the `list`/`read` route bodies in `module_routes.py.jinja`**

Read the full current file first (233 lines) to confirm it still matches
what's quoted below (this plan reproduces the file's exact content at
plan-writing time) — **do this before Task 3 has run**, since Task 3 also
edits this same file; if Task 3 has already landed by the time you start
this step, re-read the file fresh rather than trusting this plan's "before"
snapshot, and adapt the same logical change to whatever Task 3 actually
left behind.

**`list` route** (currently lines 111-118):

```jinja
) -> List[{{ entity.name }}Response]:
{% if entity.rls and entity.rls.identity_source.type == 'auth_user' %}
    owner_id = None if set(current_user.roles or []).intersection({{ entity.rls.bypass_roles|tojson }}) else current_user.id
{% elif entity.rls %}
    owner_id = rls_owner_header
{% endif %}
    return {{ 'await ' if is_async }}service.list_{{ entity.plural_snake }}(db, skip=skip, limit=limit{% for rel in entity.owned_relationships if not rel.is_rls_link %}, {{ rel.fk_column }}={{ rel.fk_column }}{% endfor %}{% if entity.rls %}, owner_id=owner_id{% endif %})
{% endif %}
```

becomes:

```jinja
) -> List[{{ entity.name }}Response]:
{% if entity.rls and entity.rls.read_scope == 'any_authenticated' %}
    owner_id = None
{% elif entity.rls and entity.rls.identity_source.type == 'auth_user' %}
    owner_id = None if set(current_user.roles or []).intersection({{ entity.rls.bypass_roles|tojson }}) else current_user.id
{% elif entity.rls %}
    owner_id = rls_owner_header
{% endif %}
    return {{ 'await ' if is_async }}service.list_{{ entity.plural_snake }}(db, skip=skip, limit=limit{% for rel in entity.owned_relationships if not rel.is_rls_link %}, {{ rel.fk_column }}={{ rel.fk_column }}{% endfor %}{% if entity.rls %}, owner_id=owner_id{% endif %})
{% endif %}
```

(the new `{% if %}` branch is checked *first*, matching `create`'s own
precedent of having a distinguished case checked before the general
auth_user/header split — `read_scope` overrides everything else on the
read path.)

Apply the exact same 3-line change (add one `{% if entity.rls and
entity.rls.read_scope == 'any_authenticated' %} owner_id = None {% elif
... %}` branch before the existing `auth_user`/header split) to the `read`
(get-by-id) route's body, currently lines 143-149 — identical pattern, just
in the `get_{{ entity.snake_name }}_route` function instead of `list_`.

Do **not** touch the `create`, `update`, or `delete` route bodies at all —
`read_scope` only affects `list`/`read`, per spec Section 4.1's explicit
statement that `update`/`delete` stay owner-filtered for non-bypass callers
regardless of `read_scope`, and `create` is untouched by design (it was
already "deliberately NOT bypass-aware" before this task and stays that
way — `read_scope` doesn't change that).

- [ ] **Step 4: Guarantee real authentication for `read_scope: any_authenticated` regardless of identity source or RBAC config**

This is a real correctness subtlety this plan's own investigation
surfaced, not explicitly spelled out in the spec: "any_authenticated"
must actually mean "the caller presented a valid JWT," not "whatever
happens to already be required by this entity's other settings." For an
`auth_user`-identity entity, this is already guaranteed — the route
signature unconditionally depends on `current_user` (either via
`require_roles(...)` or `_auth_service.get_current_user`), which itself
IS the authentication check; no change needed there for `list`/`read`.

For a **header-identity** entity, however, today's signature has *no*
`current_user`/auth dependency at all for `list`/`read` (only the header
parameter) — RBAC's own decorator-level gating (`Depends(require_roles(...))`)
only applies when `project.rbac_enabled and entity.rbac['list']` is
truthy, which is common but not guaranteed (an ERD could have `rbac.enabled:
false` entirely, or an entity with an empty `endpoints.rbac` override that
resolves to no roles required). Without a fix, `read_scope:
any_authenticated` on a header-identity entity with no RBAC gating in play
would silently mean "no filtering AND no authentication requirement at
all" — contradicting the explicit design decision (confirmed with the
user) that "public read" means *any authenticated user*, not a fully open
endpoint.

Fix: for `list`/`read` routes specifically, when `entity.rls and
entity.rls.read_scope == 'any_authenticated' and entity.rls.identity_source.type
== 'header'`, add an explicit, unconditional authentication dependency to
the route's parameter list — reuse the existing `_auth_service.get_current_user`
dependency (the same one `auth_user`-identity routes already use when RBAC
doesn't otherwise gate them), ignoring its return value:

```jinja
{% if entity.rls and entity.rls.read_scope == 'any_authenticated' and entity.rls.identity_source.type == 'header' %}
    _: User = Depends(_auth_service.get_current_user),
{% elif entity.rls and entity.rls.identity_source.type == 'auth_user' %}
    ...(existing current_user parameter block, unchanged)...
{% elif entity.rls %}
    rls_owner_header: int = Header(..., alias="{{ entity.rls.identity_source.header_name }}"),
{% endif %}
```

Read the actual current parameter blocks for `list_..._route` (lines
94-110) and `get_..._route` (lines 130-142) before writing this — the real
Jinja has more nesting (an inner `{% if project.rbac_enabled and
entity.rbac['list'] %}` inside the `auth_user` branch) than the simplified
sketch above shows; preserve that inner structure exactly, only add the
new outer branch ahead of it. Note the header parameter itself (`rls_owner_header`)
should NOT be added for this new branch — a `read_scope: any_authenticated`
header-identity entity's `list`/`read` routes don't need the header at all
(the body's `owner_id = None` per Step 3 never reads it).

This means `module_routes.py.jinja` needs `User`/`_auth_service` imported
whenever *either* `has_auth_user_rls` *or* any header-identity entity has
`read_scope: any_authenticated` — read the top of the file (the `{% set
has_auth_user_rls = ... %}` / `{% set has_header_rls = ... %}` lines,
currently 6-7, and the conditional import block at lines 17-19 and 29-33)
and add a third `{% set %}`:

```jinja
{% set has_any_authenticated_header_rls = (rls_entities|selectattr('rls.read_scope', 'equalto', 'any_authenticated')|selectattr('rls.identity_source.type', 'equalto', 'header')|list|length) > 0 %}
```

and change the two import-gating conditions from `{% if has_auth_user_rls %}`
to `{% if has_auth_user_rls or has_any_authenticated_header_rls %}` (both
the `from database.models import User` block and the `_auth_service`
block) — verify `selectattr` with a dotted nested attribute path
(`rls.read_scope`, `rls.identity_source.type`) actually works against this
file's existing data shape by testing it (this file already uses
`|map(attribute='identity_source')|map(attribute='type')` chaining rather
than a single dotted path for a similar nested lookup at lines 6-7 — read
why, and use whichever form actually works when you test it, don't assume
dotted-path `selectattr` works here without checking).

- [ ] **Step 5: New fixture and real HTTP round-trip test**

Add `app/tests/fixtures/erd/rls_read_scope_any_authenticated.yml` (or
extend an existing RLS fixture — your call, but a dedicated new fixture is
probably clearer given this needs two RLS'd entities with different
`read_scope` values to prove the default is unaffected): `auth.enabled:
true`, `rbac.enabled: true` with at least an `admin` role, an `auth_user`-identity
entity (e.g. `Note`) with `read_scope: any_authenticated` and one *without*
it set (a sibling entity, e.g. `Secret`, using the default `read_scope:
owner`, to prove the default is unchanged in the same fixture).

Write a real HTTP round-trip test (in `app/tests/test_generated_project_runtime.py`,
matching that file's existing patterns for generating, booting via
`TestClient`, and driving real requests) proving:
1. User A creates a `Note` — it's owned by A.
2. User B (a different registered user, no special role) can `GET
   /notes/{id}` and `GET /notes` and see user A's note (the new
   `any_authenticated` behavior).
3. User B attempting `PUT`/`DELETE` on user A's note still gets the
   existing owner-filtered 404 (writes stay owner-only, unaffected by
   `read_scope`).
4. For the sibling `Secret` entity (default `read_scope: owner`): user A
   creates a `Secret`; user B's `GET` of it 404s (today's exact,
   unaffected default behavior) — this is the assertion that actually
   proves the default wasn't silently changed, not just "the new field
   works when set."
5. An unauthenticated request (no `Authorization` header at all) to `GET
   /notes` gets a `401`, not the note list — proving "any_authenticated"
   genuinely still requires authentication (this is the regression test
   for Step 4's fix specifically).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest app/tests -q`
Expected: PASS, matching baseline + this task's new tests (re-confirm the
exact count after Task 1 lands, don't assume a fixed number).

- [ ] **Step 7: Commit**

```bash
git add app/erd/schema.py app/erd/translate.py app/templates/Python/service/module_routes.py.jinja app/tests/
git commit -m "Add RLS read_scope: any_authenticated for public-read/owner-write entities"
```

---

## Task 3: `bypass_roles` for header-based RLS

**Files:**
- Modify: `app/erd/loader.py`
- Modify: `app/templates/Python/service/module_routes.py.jinja`
- Test: new fixture (extend `app/tests/fixtures/erd/rls_header_owned_with_rbac.yml`
  or add a new one — your call), new tests in
  `app/tests/test_generated_project_runtime.py`

**Interfaces:**
- Consumes: `RLSSpec.bypass_roles` (already exists) and
  `RLSIdentitySource.type` (already exists) — no schema change in this
  task.
- Produces: header-identity entities' `list`/`read`/`update`/`delete`
  routes optionally accept an absent header when the caller holds a
  bypass role; `create` is unaffected (header stays required).

- [ ] **Step 1: Remove the hard rejection in `loader.py`**

Read `app/erd/loader.py`'s `_validate_rls` in full first (confirm current
line numbers — this plan quotes lines 77-100 as read at plan-writing time,
re-verify before editing since exact line numbers shift easily). Current:

```python
        if entity.rls.bypass_roles:
            if source.type == "header":
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.bypass_roles has no effect when "
                    "identity_source.type is 'header' — the header identity source resolves "
                    "ownership purely from the request header and never reads any role "
                    "information, so there is nothing for a bypass role to plug into. "
                    "Remove bypass_roles, or switch to identity_source.type: auth_user. "
                    "(RBAC-gating a header-sourced entity's endpoints is still supported and "
                    "unaffected — that is endpoints.rbac / rbac.default_permissions, not "
                    "rls.bypass_roles.)"
                )
            if not erd.rbac.enabled:
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.bypass_roles requires rbac.enabled: true "
                    "(bypass roles are RBAC roles)."
                )
            unknown = sorted(set(entity.rls.bypass_roles) - set(erd.rbac.roles))
            if unknown:
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.bypass_roles references unknown role(s): "
                    f"{', '.join(unknown)} — declared roles are: "
                    f"{', '.join(erd.rbac.roles) or 'none declared'}."
                )
```

Remove only the `if source.type == "header": raise ERDValidationError(...)`
block (the first `if` inside the outer `if entity.rls.bypass_roles:`).
Leave the `rbac.enabled` check and the unknown-roles check completely
unchanged — both already apply regardless of `source.type`, confirmed by
reading this code (they're not nested inside any `source.type` check
themselves), so no other change is needed here for these two rules to
already cover header-identity entities correctly.

- [ ] **Step 2: Add `current_user` + optional header for header-identity + `bypass_roles` in `module_routes.py.jinja`**

Read the full current file before editing — if Task 2 has already landed,
this file now has Task 2's additions (the `read_scope` branch and the
`has_any_authenticated_header_rls` set/import-gating); re-read it fresh and
apply this task's change on top of whatever Task 2 actually left, not the
plan's pre-Task-2 snapshot quoted in this plan's Global Constraints
section.

This task's change applies specifically when `entity.rls.identity_source.type
== 'header' and entity.rls.bypass_roles` (note: distinct from Task 2's
`read_scope == 'any_authenticated'` condition — an entity could have
neither, one, or both set; if both, `read_scope` already makes `list`/`read`
unconditionally unfiltered per Task 2, in which case this task's
bypass-role check on those two actions becomes moot, but this task's
`create`'s header-required behavior and `update`/`delete`'s bypass logic
still matter independently — write the Jinja so both conditions can
coexist without conflicting, e.g. Task 2's `read_scope` branch, checked
first on `list`/`read`, already wins outright there regardless of this
task's changes to the *same* `list`/`read` bodies' fallback branches).

For **`list`** (apply the identical pattern to **`read`**/get-by-id): the
current parameter block (lines 102-110, or wherever Task 2 left it) has:

```jinja
{% if entity.rls and entity.rls.identity_source.type == 'auth_user' %}
{% if project.rbac_enabled and entity.rbac['list'] %}
    current_user: User = Depends(require_roles({% for role in entity.rbac['list'] %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %})),
{% else %}
    current_user: User = Depends(_auth_service.get_current_user),
{% endif %}
{% elif entity.rls %}
    rls_owner_header: int = Header(..., alias="{{ entity.rls.identity_source.header_name }}"),
{% endif %}
```

Change the final `{% elif entity.rls %}` branch to distinguish
bypass-enabled header entities:

```jinja
{% elif entity.rls and entity.rls.bypass_roles %}
    current_user: User = Depends(_auth_service.get_current_user),
    rls_owner_header: Optional[int] = Header(None, alias="{{ entity.rls.identity_source.header_name }}"),
{% elif entity.rls %}
    rls_owner_header: int = Header(..., alias="{{ entity.rls.identity_source.header_name }}"),
{% endif %}
```

(the original unconditional-header branch stays, as the final `{% elif %}`,
for header entities with no `bypass_roles` — unchanged behavior.) Adding
`current_user` here means `User`/`_auth_service` must be imported whenever
*any* header-identity entity has `bypass_roles` set too — extend the
`{% set %}`/import-gating logic from Task 2's Step 4 once more (a third
OR'd condition: `has_auth_user_rls or has_any_authenticated_header_rls or
has_header_bypass_rls`, where the new set is something like
`{% set has_header_bypass_rls = (rls_entities|selectattr('rls.identity_source.type', 'equalto', 'header')|selectattr('rls.bypass_roles')|list|length) > 0 %}`
— verify the exact `selectattr` chaining syntax works as intended by
testing it, per the same caveat as Task 2 Step 4).

Then the route body (currently `owner_id = rls_owner_header` unconditionally
for the header `{% elif %}` branch) becomes:

```jinja
{% if entity.rls and entity.rls.read_scope == 'any_authenticated' %}
    owner_id = None
{% elif entity.rls and entity.rls.identity_source.type == 'auth_user' %}
    owner_id = None if set(current_user.roles or []).intersection({{ entity.rls.bypass_roles|tojson }}) else current_user.id
{% elif entity.rls and entity.rls.bypass_roles %}
    owner_id = None if set(current_user.roles or []).intersection({{ entity.rls.bypass_roles|tojson }}) else rls_owner_header
{% elif entity.rls %}
    owner_id = rls_owner_header
{% endif %}
```

(this is Task 2's Step 3 body, with one more `{% elif %}` branch inserted
between the `auth_user` branch and the final unconditional-header branch —
if you're doing Task 3 after Task 2 has already landed, the file will
already have Task 2's first branch; add only this task's new branch, don't
duplicate Task 2's.)

Apply the identical two changes (parameter block + body) to `update` and
`delete`'s route functions too — both currently have the exact same
`{% elif entity.rls %} rls_owner_header: int = Header(..., alias=...) {% endif %}`
parameter shape and `owner_id = rls_owner_header` body line as `list`/`read`
(read the current `update_..._route` at ~lines 165-184 and
`delete_..._route` at ~lines 208-226 to confirm before editing — apply
the same pattern).

- [ ] **Step 3: `create` stays header-required even for bypass-role callers**

Read the current `create` route (lines 45-82, or wherever prior tasks left
it) — **do not add a `bypass_roles`-aware branch here.** The existing
header parameter block for `create` (currently `{% elif entity.rls %}
rls_owner_header: int = Header(..., alias=...) {% endif %}` at lines 59-61)
and body (`{% elif entity.rls %} owner_id = rls_owner_header {% endif %}`
at lines 71-72) stay completely unchanged by this task — a bypass-role
caller creating a row still supplies the target tenant's header explicitly,
exactly as a non-bypass caller does, per spec Section 5.2's explicit
create-exception (mirroring the pre-existing, already-shipped `auth_user`-mode
precedent at lines 63-70, which has its own explanatory comment — read
that comment, the reasoning is identical: "a NULL owner is invisible to
every non-bypass caller forever"). If you find yourself about to add a
`current_user`/bypass check to the `create` route, stop — that contradicts
the spec's explicit design decision, re-read spec Section 5.2 before
proceeding.

- [ ] **Step 4: New fixture and real HTTP round-trip test**

Extend `app/tests/fixtures/erd/rls_header_owned_with_rbac.yml` (read it
first — it currently has `auth.enabled: true`, `rbac.roles: [admin]`, a
`Tenant` entity, and an `Order` entity with `owner: true`/header-identity
RLS and no `bypass_roles`) by adding `bypass_roles: [admin]` to `Order`'s
`rls:` block — or create a new, separate fixture if extending this one
would complicate an existing test that depends on its current exact shape
(check `app/tests/test_rls_generation.py` for any test already using this
fixture's Order entity — `grep -rn "rls_header_owned_with_rbac"
app/tests/` — before deciding whether to extend in place or copy to a new
file).

Write a real HTTP round-trip test (in `app/tests/test_generated_project_runtime.py`)
proving:
1. A non-bypass, non-admin caller still requires the header on every
   action — a `GET /orders` with no `X-Tenant-Id` header still 422s,
   exactly as today (regression check that non-bypass behavior is
   unchanged).
2. An admin (bypass-role) caller can `GET /orders` (list), `GET
   /orders/{id}`, `PUT /orders/{id}`, and `DELETE /orders/{id}` — all
   **without** supplying `X-Tenant-Id` at all — and sees/affects rows
   across every tenant, not just one.
3. An admin (bypass-role) caller attempting `POST /orders` **without** the
   header still fails (a `422`, from the still-required `Header(...)`) —
   this is the one place bypass does *not* apply, and needs its own
   explicit assertion, not inferred from the other three actions passing.
4. An admin (bypass-role) caller supplying `X-Tenant-Id` on `POST /orders`
   succeeds and the created row is stamped with exactly that tenant id
   (not some default/null) — proving `create`'s behavior is genuinely
   unchanged, not silently broken by this task's other route-body edits.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest app/tests -q`
Expected: PASS, matching baseline + this task's new tests.

- [ ] **Step 6: Commit**

```bash
git add app/erd/loader.py app/templates/Python/service/module_routes.py.jinja app/tests/
git commit -m "Support bypass_roles for header-based RLS (list/read/update/delete only, create keeps requiring the header)"
```

---

## Task 4: Opt-in per-service URL prefix

**Files:**
- Modify: `app/erd/schema.py`
- Modify: `app/erd/translate.py`
- Modify: `docs-site/erd-reference/fields.md`
- Modify: `docs-site/architecture/templates.md`
- Test: new fixture, new tests in `app/tests/test_generated_project_runtime.py`
  and/or `app/tests/test_erd_loader.py` (validation-only cases)

**Interfaces:**
- Produces: `ServiceDecl.prefix: Optional[str] = None`, consumed by
  `translate.py`'s `base_path` computation. No `module_routes.py.jinja`
  change — it already just interpolates `entity.base_path` verbatim
  (confirm this yourself by reading the file's `"{{ entity.base_path }}"`
  usages before starting, per this plan's Global Constraints — don't
  assume it's still true without checking, since Tasks 2/3 both edit this
  same file and could in principle have touched something nearby, though
  neither task has any reason to touch the `@router.post("{{
  entity.base_path }}", ...)` lines specifically).

- [ ] **Step 1: Add `prefix` to `ServiceDecl` with validation**

Read `app/erd/schema.py`'s `ServiceDecl` (lines 178-192 at plan-writing
time) in full first. Current:

```python
class ServiceDecl(BaseModel):
    """Assigns a set of entities to a named service/module."""
    name: str = Field(..., min_length=1)
    entities: List[str] = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def name_is_valid_python_identifier(cls, v: str) -> str:
        if not (v.isidentifier() and v.islower()):
            raise ValueError(
                f"services: service name '{v}' must be a valid lowercase Python identifier "
                "(letters, digits, underscores; not starting with a digit) - it becomes the "
                "generated modules/<name>/ directory and function-name segment"
            )
        return v
```

Add the new field and its validator:

```python
class ServiceDecl(BaseModel):
    """Assigns a set of entities to a named service/module."""
    name: str = Field(..., min_length=1)
    entities: List[str] = Field(..., min_length=1)
    prefix: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_is_valid_python_identifier(cls, v: str) -> str:
        if not (v.isidentifier() and v.islower()):
            raise ValueError(
                f"services: service name '{v}' must be a valid lowercase Python identifier "
                "(letters, digits, underscores; not starting with a digit) - it becomes the "
                "generated modules/<name>/ directory and function-name segment"
            )
        return v

    @field_validator("prefix")
    @classmethod
    def prefix_is_valid_path_segment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v == "":
            raise ValueError(
                "services: prefix, if set, must not be an empty string - omit the field "
                "entirely (or leave it unset) rather than setting an empty prefix"
            )
        if not v.startswith("/"):
            raise ValueError(
                f"services: prefix '{v}' must start with '/' (e.g. '/catalog')"
            )
        if v.endswith("/"):
            raise ValueError(
                f"services: prefix '{v}' must not end with '/' (e.g. '/catalog', not '/catalog/') "
                "- a trailing slash would produce a double-slash when combined with an entity's "
                "own route path"
            )
        return v
```

(`Optional` is already imported at the top of this file — confirm, don't
duplicate.)

- [ ] **Step 2: Build the entity→prefix lookup and change `base_path` computation in `translate.py`**

Read `app/erd/translate.py`'s `translate()` function in full around the
`crud_entities` loop (lines 458-473 at plan-writing time) — per this plan's
Global Constraints "Correction vs. the spec" section, there is **no**
existing entity→service lookup available at this point; build a small new
one. Immediately before the `crud_entities: List[Dict[str, Any]] = []`
line, add:

```python
    service_prefix_by_entity: Dict[str, Optional[str]] = {}
    for svc in erd.services:
        for entity_name in svc.entities:
            service_prefix_by_entity[entity_name] = svc.prefix
```

Then change the `base_path` line (currently `"base_path":
entity.endpoints.base_path or f"/{plural_snake}",`) to:

```python
            "base_path": (
                entity.endpoints.base_path
                or (
                    f"{service_prefix_by_entity.get(entity.name)}/{plural_snake}"
                    if service_prefix_by_entity.get(entity.name)
                    else f"/{plural_snake}"
                )
            ),
```

Confirm `Dict`/`Optional` are already imported at the top of `translate.py`
(they almost certainly are, given the file's existing type hints — verify,
don't duplicate).

- [ ] **Step 3: Documentation**

Read `docs-site/erd-reference/fields.md`'s `services` section (`##
\`services\` (\`List[ServiceDecl]\`)`) in full first — confirm its current
exact table format (columns, style) by reading 2-3 of its existing rows
(and a couple of other pages' field tables for the site-wide convention),
then add a `prefix` row matching that exact style:

```markdown
| `prefix` | `Optional[str]` | default `None` | Prepends this string to every entity's route path in this service, unless that entity sets its own `endpoints.base_path` (which always wins, never combined with the prefix). Must start with `/` and must not end with `/` if set. |
```

Add this to the **Cross-field rules** paragraph immediately below the
table (read the existing rules list for this section's format first):

```markdown
- `services[].prefix`, if set, must start with `/`, must not end with `/`,
  and must not be an empty string (schema-level validation, `ServiceDecl.prefix_is_valid_path_segment`).
- An entity's own `endpoints.base_path`, if set, always wins outright over
  its service's `prefix` — the two are never combined.
```

Then read `docs-site/architecture/templates.md`'s section describing route
generation / the `modules`-loop (search for where it currently discusses
`base_path` or route paths) and add one clear paragraph stating the
default plainly: with no `prefix` set on a service and no `base_path` set
on an entity, routes are mounted directly at the API root with no
module/service-name-based prefix at all (only the auth module gets an
automatic prefix, `/auth` by default via `auth_module_name`) — and that
`services[].prefix` is the real, current way to opt into a shared
namespace for a whole service's entities, linking to the ERD reference
page's new row for the full field details. Verify every claim in this
paragraph against the actual current template/translate.py behavior one
more time before writing it (re-generate a fixture and check, don't just
restate this plan's own prose from memory).

- [ ] **Step 4: New fixture and tests**

Add a fixture, `app/tests/fixtures/erd/service_prefix.yml`: two services —
one with `prefix: "/catalog"` and 2+ entities that don't set their own
`base_path`, plus one entity in that same service that DOES set its own
`endpoints.base_path` (e.g. `/special-path`) to prove precedence; a second,
sibling service with no `prefix` set at all, to prove the unprefixed
default is unaffected.

Write tests:
1. (`app/tests/test_erd_loader.py` or `test_erd_schema.py`, matching
   existing validation-test conventions in whichever file already tests
   similar schema-level field validators) — `backstudio validate` (or the
   equivalent programmatic `load_erd`/schema-instantiation call this repo's
   tests already use) rejects `prefix: "catalog"` (missing leading `/`),
   `prefix: "/catalog/"` (trailing `/`), and `prefix: ""` (empty), each
   with a clear error — 3 separate test cases or one parametrized test,
   your call, matching this file's existing style.
2. (`app/tests/test_generated_project_runtime.py`) — a real HTTP
   round-trip test: generate the `service_prefix.yml` fixture, boot it,
   confirm `GET /catalog/<plural-of-unprefixed-entity>` succeeds (routes
   are genuinely reachable at the prefixed path), confirm the
   `base_path`-overridden entity is reachable at exactly `/special-path`
   (not `/catalog/special-path` — proving the entity-level override wins
   outright, not combined), and confirm the sibling unprefixed service's
   entity is still reachable at its bare `/<plural>` path with no prefix
   at all.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest app/tests -q`
Expected: PASS, matching baseline + this task's new tests.

- [ ] **Step 6: `mkdocs build --strict`**

Run: `uv run mkdocs build --strict`
Expected: exit 0, zero warnings/errors (this task edits 2 docs-site pages
— confirm no broken links/anchors were introduced).

- [ ] **Step 7: Commit**

```bash
git add app/erd/schema.py app/erd/translate.py docs-site/ app/tests/
git commit -m "Add opt-in services[].prefix for a shared URL namespace per service"
```

---

## Final whole-branch review

Once all 4 tasks are complete and individually reviewed clean, dispatch a
final, broad review on the most capable available model, per
`superpowers:subagent-driven-development`'s standard closing step —
reviewing the *whole* diff for cross-task issues no single task's review
could see. Specific things worth checking, given this plan's particular
shape: does `module_routes.py.jinja`'s final state (after both Task 2 and
Task 3 have each added their own `{% elif %}` branches to the same route
bodies) still read correctly and render valid Python for every combination
of `read_scope`/`bypass_roles`/`identity_source.type` — including
combinations no single task's own fixture exercises alone (e.g. a
header-identity entity with BOTH `read_scope: any_authenticated` AND
`bypass_roles` set together — does `list`/`read` correctly take Task 2's
branch and ignore Task 3's, while `update`/`delete` correctly still get
Task 3's bypass behavior)? Does the `has_auth_user_rls` /
`has_any_authenticated_header_rls` / `has_header_bypass_rls` import-gating
logic (three separate `{% set %}` conditions accumulated across Tasks 2
and 3) actually produce syntactically valid, correctly-scoped imports for
every fixture in the test suite, not just each task's own new fixture —
render every existing RLS fixture (not just the 2-3 new ones) and confirm
each still compiles and its own existing tests still pass unmodified. Does
Task 1's `to_python_value`/`repr()` fix interact correctly with Task 4's
`base_path`/`prefix` values (both are Python-source-embedded strings now
going through different escaping mechanisms — `prefix` itself is a
schema-validated, structurally-constrained path segment already excluded
from Task 1's "free-text field" scope by design, confirm this reasoning
actually holds, i.e. `prefix` can't contain a `"` in the first place
because of its own validator, so it never needed Task 1's fix — verify
this is genuinely true, not just assumed). Budget for at least one fix
round afterward if anything real surfaces, same as every prior plan's
precedent in this repo's history.
