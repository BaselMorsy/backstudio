# Repo restructure, README rewrite, and mkdocs documentation site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename/flatten this repo's own package from `backend/` to `app/`
while deleting the dead old-UI-serving subsystem found during survey,
rewrite `README.md` as a short front door, and stand up a local `mkdocs`
documentation site as the actual reference material the README links to.

**Architecture:** Three initiatives sequenced to avoid conflicting with
each other: cleanup deletions first (reviewed against today's `backend/...`
paths), then the single big `backend/` → `app/` rename (the one task that
can't be split further — a half-renamed repo doesn't build), then the
README rewrite and mkdocs content (both need final `app/...` paths to be
correct, not paths about to change).

**Tech Stack:** Python 3.11, `uv`, Jinja2, Typer CLI, pytest — plus new:
`mkdocs`, `mkdocs-material` (dev-only dependencies).

**Spec:** `docs/superpowers/specs/2026-09-10-repo-restructure-and-docs-design.md`

## Global Constraints

**Target top-level layout** (final state, after Task 4):
```
backstudio/                  (repo root, unchanged name)
├── app/
│   ├── cli/
│   ├── erd/
│   ├── services/
│   ├── templates/
│   ├── tests/
│   └── utils/
├── docs/
│   └── superpowers/          (this project's own internal specs/plans/
│                               backlog archive — UNCHANGED, not touched
│                               by this plan except as a content source)
├── docs-site/                (new — mkdocs source content)
├── examples/
├── assets/
├── mkdocs.yml
├── pyproject.toml
└── README.md
```

**Complete deletion list** (all confirmed dead by direct repo survey —
every task below that deletes something is deleting from this exact list,
nothing else): `frontend/`, `mcp_server/`, `backend/api/`, `backend/main.py`,
`backend/services/project_service.py`, `backend/config/` (both files
literally empty, 0 lines each), `backend/requirements.txt`, `setup.bat`,
`setup.sh`, `start.bat`, `start.sh`, `stop.bat`, `stop.sh`,
`examples/example_project_generator.py`, `RELEASE_NOTES.md`,
`backend/schemas/` (all files except the 4 classes relocated in Task 2),
`backend/templates/Python/service/service.py.jinja`,
`backend/templates/Python/service/schemas.py.jinja`,
`backend/templates/Python/service/routes.py.jinja`.

**Complete "moves as-is" list** (Task 4): `backend/cli/` → `app/cli/`,
`backend/erd/` → `app/erd/`, `backend/services/` → `app/services/` (minus
the already-deleted `project_service.py`), `backend/templates/` →
`app/templates/` (minus the already-deleted 3 dead service templates —
`module_service.py.jinja`/`module_schemas.py.jinja`/`module_routes.py.jinja`
DO move, they back the real `modules` loop), `backend/tests/` →
`app/tests/`, `backend/utils/` → `app/utils/`.

**The 4-class schema relocation** (Task 2): `Cardinality`, `LazyStrategy`,
`FieldType`, `ModelField` move from `backend/schemas/data.py` into
`backend/erd/schema.py` (still at the pre-rename `backend/` path — Task 2
runs before Task 4). Their 4 importers, updated to import from
`backend.erd.schema` instead of the deleted `backend.schemas.data`:
`backend/erd/schema.py` (becomes the definition site, no import needed for
its own classes), `backend/erd/visualize.py`,
`backend/tests/test_auth_expansion_generation.py`,
`backend/tests/test_auth_generation.py`,
`backend/tests/test_rls_generation.py`.

**`pyproject.toml` diff shape** (Task 4): `[project.scripts] backstudio =
"app.cli.main:app"` (was `"backend.cli.main:app"`);
`[tool.hatch.build.targets.wheel] packages = ["app"]` (was `["backend"]`);
remove `"python-multipart==0.0.6"` from `dependencies`; add
`"mkdocs>=1.6"` and `"mkdocs-material>=9.5"` to both
`[project.optional-dependencies] dev` and `[dependency-groups] dev` lists;
update the two inline comments inside `dependencies` that reference
`backend/tests/test_generated_project_runtime.py` and
`backend/templates/Python/config.py.jinja` to say `app/tests/...` and
`app/templates/...` instead (comments only, not just code — stale comments
are exactly the kind of doc-drift this plan exists to avoid introducing).

**The `templates_dir` fix's exact resolution expression** (Task 4, spec
3.6): in `app/services/code_generator.py`, replace the CWD-relative
default with a module-location-relative one. Add
`from typing import Dict, Any, List, Optional` (add `Optional` to the
existing import), define a module-level constant right after the imports:
```python
_DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
```
(`Path(__file__)` is `app/services/code_generator.py`; `.parent.parent`
reaches `app/`; `/ "templates"` reaches `app/templates/` — verify this
resolves correctly once the file actually lives at that path, not before).
Change the constructor signature from
`def __init__(self, templates_dir: str = "backend/templates", output_dir: str = "workspace"):`
to
`def __init__(self, templates_dir: Optional[str] = None, output_dir: str = "workspace"):`
and its body's first line from `self.templates_dir = Path(templates_dir)`
to:
```python
        self.templates_dir = Path(templates_dir) if templates_dir is not None else _DEFAULT_TEMPLATES_DIR
```
No call site anywhere in the codebase passes `templates_dir` today (verify
this remains true after Task 4's import rewrite) — this is a pure
default-value behavior change with zero call-site edits required.

**Docs-content verification discipline** (Tasks 6-10, binding on every one
of them): never write a factual claim into README.md or any `docs-site/`
page from memory or by transcribing an older doc/spec verbatim. Every
command, flag, field name, default value, or behavior description must be
checked against the actual current source file or actual rendered/CLI
output before being written down. A design spec written mid-session (like
this plan's own spec, or the RLS/async-support/auth-expansion specs this
plan's docs tasks draw from) can describe intent that a later fix round
changed — the auth-expansion plan's own final whole-branch review is a
concrete, real example: it found and fixed two genuine behavioral defects
*after* that feature's spec was written and its 9 tasks were individually
reviewed clean. A spec or an old README section is a *starting draft* for
docs content, never a citable source of truth on its own.

**Adapting "No Placeholders" for the documentation-writing tasks (7-10):**
full literal prose for ~13 documentation pages would make this plan
enormous and isn't how documentation tasks work anyway. The rule's
*intent* — an implementer should never have to invent unstated facts —
still applies, enforced differently: each docs task below gives the exact
file path, its position in the nav, a concrete and specific outline of
what the page must cover (not "explain how auth works" but the literal
named facts that must appear), and the exact source(s) to verify each
claim against. The plan constrains *what must be true in the page*; the
implementer supplies the actual sentences, verified against those named
sources per the discipline above. This is a deliberate, spec-approved
adaptation for this plan's docs tasks only — Tasks 1-6 (code/cleanup) give
full literal diffs/code exactly per the skill's normal rule.

**Binding authority:** this plan argues from the spec
(`docs/superpowers/specs/2026-09-10-repo-restructure-and-docs-design.md`).
Where a task's own text doesn't settle something, the spec does; where
neither does, the smallest reasonable call has already been made inline
below and is not left for the implementer to invent.

---

### Task 1: Delete the dead UI-serving subsystem

**Files:**
- Delete: `frontend/` (entire directory)
- Delete: `mcp_server/` (entire directory)
- Delete: `backend/api/` (entire directory, incl. `routes.py`)
- Delete: `backend/main.py`
- Delete: `backend/services/project_service.py`
- Delete: `backend/config/` (entire directory — both files empty)
- Delete: `backend/requirements.txt`
- Delete: `setup.bat`, `setup.sh`, `start.bat`, `start.sh`, `stop.bat`, `stop.sh`
- Delete: `examples/example_project_generator.py`
- Delete: `RELEASE_NOTES.md`
- Test: none new — this task removes code with zero surviving callers;
  the existing suite is the regression check

**Interfaces:** none — every one of these was confirmed dead by direct
repo-wide grep during the spec's survey (Section 3.2): `backend/api/` and
`backend/main.py` are only ever imported by each other and by
`frontend`/`examples/example_project_generator.py` (also deleted this
task); `backend/services/project_service.py` is only imported by
`backend/api/routes.py`; `backend/config/`'s two files are 0 lines each,
referenced nowhere; `backend/requirements.txt` is a standalone file, not
imported by anything (it's a requirements list, not code).
`examples/blog.yml` is explicitly NOT deleted — it is a real CLI ERD
example, unrelated to `example_project_generator.py`'s old-REST-API usage.

- [ ] **Step 1: Delete the files/directories**

```bash
rm -rf frontend/ mcp_server/ backend/api/ backend/main.py \
  backend/services/project_service.py backend/config/ \
  backend/requirements.txt setup.bat setup.sh start.bat start.sh \
  stop.bat stop.sh examples/example_project_generator.py RELEASE_NOTES.md
```

- [ ] **Step 2: Confirm nothing else referenced these paths**

```bash
grep -rn "backend\.api\|backend\.main\|project_service\|ProjectService\|from backend\.config\|import backend\.config" --include="*.py" backend/ | grep -v __pycache__
grep -rln "example_project_generator" --include="*.py" --include="*.md" .
```

Expected: zero matches for both (if the second finds a mention in
`README.md`, leave it — Task 6 rewrites the README separately; don't fix
docs prose in this task).

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS, same count as before this task (252) — no test in this
suite exercised any of the deleted code (confirmed during spec survey:
zero test files import `backend.api`, `backend.main`, or
`ProjectService`).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Delete dead UI-serving subsystem (frontend, mcp_server, old REST API, old UI dev scripts)"
```

---

### Task 2: Relocate 4 load-bearing schema classes, delete the rest of `backend/schemas/`

**Files:**
- Modify: `backend/erd/schema.py`
- Modify: `backend/erd/visualize.py`
- Modify: `backend/tests/test_auth_expansion_generation.py`
- Modify: `backend/tests/test_auth_generation.py`
- Modify: `backend/tests/test_rls_generation.py`
- Delete: `backend/schemas/` (entire directory, after the above edits land)

**Interfaces:**
- Produces: `Cardinality`, `LazyStrategy`, `FieldType`, `ModelField` now
  live in `backend/erd/schema.py` — importable as
  `from backend.erd.schema import Cardinality, LazyStrategy, FieldType, ModelField`
  (or any subset). Task 4's later `backend.` → `app.` rewrite will update
  this import path again; this task's job is only to change *which
  module* hosts these classes, not yet to rename the package.
- Consumes: nothing new.

- [ ] **Step 1: Move the 4 classes into `backend/erd/schema.py`**

Read `backend/erd/schema.py` in full first — confirm its current line 8 is
exactly `from backend.schemas.data import Cardinality, LazyStrategy, ModelField`
before editing (if it differs, the file has changed since this plan was
written — stop and re-derive from the live file rather than blindly apply
this diff).

Replace line 8:
```python
from backend.schemas.data import Cardinality, LazyStrategy, ModelField
```
with nothing (delete the line) — instead, insert the 4 classes' full
definitions immediately after the existing imports (i.e. after the current
`from pydantic import BaseModel, Field, field_validator, model_validator`
line, before `ALL_ACTIONS = [...]`). Copy these 4 class definitions
verbatim from `backend/schemas/data.py` (read that file first to confirm
these are still exact — this plan's snapshot is current as of the spec's
survey, but verify before pasting):

```python
class Cardinality(str, Enum):
    """Relationship cardinality types"""
    ONE_TO_MANY = "one-to-many"
    MANY_TO_ONE = "many-to-one"
    ONE_TO_ONE = "one-to-one"
    MANY_TO_MANY = "many-to-many"


class LazyStrategy(str, Enum):
    """SQLAlchemy lazy loading strategies"""
    SELECT = "select"
    JOINED = "joined"
    SELECTIN = "selectin"
    SUBQUERY = "subquery"
    RAISE = "raise"


class FieldType(str, Enum):
    """Data model field types"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    TEXT = "text"
    JSON = "json"
    UUID = "uuid"


class ModelField(BaseModel):
    """Data model field specification"""
    name: str = Field(..., description="Field name")
    type: FieldType = Field(..., description="Field data type")
    nullable: bool = Field(default=True, description="Whether field can be null")
    unique: bool = Field(default=False, description="Whether field must be unique")
    default: Optional[Any] = Field(None, description="Default value")
    primary_key: bool = Field(default=False, description="Whether this is a primary key")
    index: bool = Field(default=False, description="Whether to create an index")
    max_length: Optional[int] = Field(None, description="Max length for string fields")
```

`backend/erd/schema.py`'s existing `from typing import Dict, List, Literal,
Optional` already imports `Optional` — check whether it also needs `Any`
(used by `ModelField.default`'s type hint) and add it to that same import
line if missing (`from typing import Any, Dict, List, Literal, Optional`).
`Enum` and `BaseModel`/`Field` are already imported by the file's existing
`from enum import Enum` and `from pydantic import BaseModel, Field, ...`
lines — do not duplicate those imports.

- [ ] **Step 2: Update the 4 importers**

`backend/erd/visualize.py` currently has two separate import lines (read
the file first to confirm):
```python
from backend.erd.schema import ERDConfig
from backend.schemas.data import ModelField
```
Merge into one:
```python
from backend.erd.schema import ERDConfig, ModelField
```

`backend/tests/test_auth_expansion_generation.py`,
`backend/tests/test_auth_generation.py`,
`backend/tests/test_rls_generation.py`: each currently has (read each file
first to confirm the exact line):
```python
from backend.schemas.data import ModelField, FieldType
```
Change to:
```python
from backend.erd.schema import ModelField, FieldType
```

- [ ] **Step 3: Delete the rest of `backend/schemas/`**

```bash
rm -rf backend/schemas/
```

- [ ] **Step 4: Confirm no remaining reference**

```bash
grep -rn "backend\.schemas\|backend/schemas" --include="*.py" --include="*.toml" . | grep -v __pycache__
```
Expected: zero matches.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS, 252 (same count — this is a pure relocation, no test's
assertions change).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Relocate 4 load-bearing schema classes into erd/schema.py, delete the rest of backend/schemas/"
```

---

### Task 3: Remove the dead `services`-loop, its templates, and `README.md.jinja`'s `project.services` blocks

**Files:**
- Modify: `backend/services/code_generator.py`
- Modify: `backend/erd/translate.py`
- Modify: `backend/templates/Python/README.md.jinja`
- Delete: `backend/templates/Python/service/service.py.jinja`
- Delete: `backend/templates/Python/service/schemas.py.jinja`
- Delete: `backend/templates/Python/service/routes.py.jinja`

**Interfaces:**
- Consumes: nothing new.
- Produces: `translate()`'s returned dict no longer has a `"services"`
  key at all (previously always `[]`) — confirm nothing downstream reads
  `state.get('services')`/`project.services` after this task other than
  the 4 blocks this task itself removes (grep in Step 4 covers this).

- [ ] **Step 1: Remove the dead loop in `code_generator.py`**

Read `backend/services/code_generator.py` in full first, locate the exact
current block (as of the spec's survey, lines 223-245):
```python
        # Generate service directories
        for service in state.get('services', []):
            # Get full service data from services dict
            service_name = service if isinstance(service, str) else service.get('name', service.get('id'))
            service_dir = output_dir / self._to_snake_case(service_name)
            ensure_directory(service_dir)
            (service_dir / "__init__.py").touch()

            # Service context
            service_context = {'project': state, 'service': service}

            self._write_file(
                service_dir / "service.py",
                self._render_template("Python/service/service.py.jinja", service_context)
            )
            self._write_file(
                service_dir / "schemas.py",
                self._render_template("Python/service/schemas.py.jinja", service_context)
            )
            self._write_file(
                service_dir / "routes.py",
                self._render_template("Python/service/routes.py.jinja", service_context)
            )
```
Delete this entire block. Leave the surrounding code (the database-file
generation above it, the `if state.get('modules'):`/`for module in
state.get('modules', []):` block below it) untouched — verify the deletion
doesn't leave a dangling blank-line gap wider than the file's existing
style elsewhere (one blank line between logical blocks, matching the
surrounding convention).

- [ ] **Step 2: Delete the 3 dead templates**

```bash
rm backend/templates/Python/service/service.py.jinja
rm backend/templates/Python/service/schemas.py.jinja
rm backend/templates/Python/service/routes.py.jinja
```

Confirm `backend/templates/Python/service/module_service.py.jinja`,
`module_schemas.py.jinja`, `module_routes.py.jinja` still exist after this
— those 3 are NOT part of this deletion, they back the real `modules` loop
a few lines below the one just deleted.

- [ ] **Step 3: Drop the `"services": []` key in `translate.py`**

Read `backend/erd/translate.py` in full first, locate the exact current
line (as of the spec's survey, line 498): `"services": [],` inside the
dict `translate()` returns. Delete that one line. Verify the surrounding
dict literal's trailing comma structure stays syntactically valid (e.g. if
`"services": [],` was not the last key, deleting it is a no-op on the
comma structure; if it happened to be last, check the previous line still
ends with a comma).

- [ ] **Step 4: Remove the 4 `project.services` blocks in `README.md.jinja`**

Read `backend/templates/Python/README.md.jinja` in full first — confirm
these 4 locations still match (as of the spec's survey) before editing:

Block A (project structure tree, ~lines 37-44):
```jinja
{% if project.services %}
{% for service in project.services %}
├── {{ service.name|snake_case }}/
│   ├── service.py           # Business logic
│   ├── schemas.py           # Pydantic schemas
│   └── routes.py            # API endpoints
{% endfor %}
{% endif %}
```
Delete this whole block.

Block B (Modules & Services API section, ~lines 186-205):
```jinja
{% if project.services %}
{% for service in project.services %}
### {{ service.name }}

{{ service.description or 'No description' }}

**Base Path:** `/api/{{ service.name|kebab_case }}`

{% if service.endpoints %}
#### Endpoints

{% for endpoint in service.endpoints %}
- `{{ endpoint.method }} {{ endpoint.path }}` - {{ endpoint.description or endpoint.function_name }}
{% endfor %}
{% else %}
No endpoints configured yet.
{% endif %}

{% endfor %}
{% endif %}
```
Delete this whole block.

Block C (empty-state check, ~line 206): change
```jinja
{% if not project.modules and not project.services and not project.auth_enabled %}
```
to
```jinja
{% if not project.modules and not project.auth_enabled %}
```
(remove only the `and not project.services` clause — the line's `{%
if %}`/body/`{% endif %}` structure is otherwise unchanged).

Block D (Implementation Guide section, ~lines 249-264):
```jinja
{% if project.services %}
{% for service in project.services %}
### {{ service.name }}

Edit `{{ service.name|snake_case }}/service.py` and implement:

{% if service.functions %}
{% for func in service.functions %}
- `{{ func.name }}()` - {{ func.description or 'TODO: Add description' }}
{% endfor %}
{% else %}
No functions defined yet.
{% endif %}

{% endfor %}
{% endif %}
```
Delete this whole block.

- [ ] **Step 5: Confirm no remaining `project.services`/`state.get('services'` reference**

```bash
grep -rn "project\.services\|state\.get('services'\|state\.get(\"services\"" backend/ | grep -v __pycache__
```
Expected: zero matches.

- [ ] **Step 6: Render every existing fixture and confirm output is unaffected**

For each fixture in `backend/tests/fixtures/erd/*.yml`, run the existing
generation path (e.g. via a quick throwaway script or by running the
relevant fixture's own test) and confirm: no `service.py`/`schemas.py`/
`routes.py` directory that isn't `modules/<name>/` or `<auth_module_name>/`
appears in the output, and the rendered `README.md` in each output
contains no leftover empty section from the deleted blocks (read at least
2-3 rendered `README.md` outputs directly, don't just check exit codes).

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS, 252 (this code path never executed for any ERD-driven
fixture — confirmed by Task 3's own premise that `translate()` always
emitted `"services": []` — so no test's assertions should be affected).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Remove dead services-loop, its 3 dead templates, and README.md.jinja's project.services blocks"
```

---

### Task 4: The rename — `backend/` → `app/`, full import rewrite, `pyproject.toml`, `templates_dir` fix, root `.gitignore`

**Files:**
- Move: `backend/cli/` → `app/cli/`, `backend/erd/` → `app/erd/`,
  `backend/services/` → `app/services/`, `backend/templates/` →
  `app/templates/`, `backend/tests/` → `app/tests/`, `backend/utils/` →
  `app/utils/`
- Delete: `backend/README.md`, `backend/__init__.py`, and any other
  stray top-level file directly under `backend/` not already covered
  above (read `backend/`'s current top-level listing first — after Tasks
  1-3, everything under it should be one of the 6 subfolders just listed
  plus possibly a top-level `__init__.py`/`README.md`; move or recreate
  `__init__.py` under `app/` as needed, since `app/` becomes the new
  Python package root)
- Modify: every one of the 24 files with a `from backend.`/`import
  backend.` statement (6 non-test: `app/cli/main.py`, `app/erd/loader.py`,
  `app/erd/schema.py`, `app/erd/translate.py`, `app/erd/visualize.py`,
  `app/services/code_generator.py`; 18 test files under `app/tests/`:
  `test_alembic_generation.py`, `test_async_generation.py`,
  `test_auth_expansion_generation.py`, `test_auth_generation.py`,
  `test_cli_generate.py`, `test_cli_skeleton.py`, `test_cli_validate.py`,
  `test_cli_visualize.py`, `test_crud_generation.py`,
  `test_end_to_end.py`, `test_erd_loader.py`, `test_erd_schema.py`,
  `test_erd_translate.py`, `test_erd_visualize.py`,
  `test_generated_project_runtime.py`, `test_rbac_generation.py`,
  `test_rls_generation.py`, `test_server_wiring.py`)
- Modify: `pyproject.toml`
- Create: `.gitignore` (repo root)

**Interfaces:**
- Produces: installable package `app` (was `backend`), CLI entry point
  `app.cli.main:app`, importable as `from app.erd.schema import ...` etc.
  throughout. Every later task (5-11) assumes this new layout exists.
- Consumes: nothing new — this task's job is purely mechanical relocation
  plus a rename of every import statement's package prefix, not a logic
  change anywhere.

This is the highest-risk task in the plan — do it as one coherent, careful
pass, verify before committing, not incrementally-committed-and-hoped.

- [ ] **Step 1: Move the directories**

```bash
git mv backend/cli app/cli
git mv backend/erd app/erd
git mv backend/services app/services
git mv backend/templates app/templates
git mv backend/tests app/tests
git mv backend/utils app/utils
```

(Using `git mv` preserves file history through the rename — plain `mv` +
`git add`/`git rm` also works but loses the rename-detection signal in
`git log --follow`; prefer `git mv` where the tool is available.)

Read what remains directly under `backend/` after these 6 moves (should be
at most `__init__.py` and/or `README.md`, per Tasks 1-3 having already
removed everything else). Move `backend/__init__.py` to `app/__init__.py`
if it exists and has real content (read it first — if it's empty, an
empty `app/__init__.py` still needs to exist for `app` to be a valid
Python package, so create one either way). `backend/README.md` (a
description of the *old* `backend/` module, distinct from the root
`README.md`) — read it first: if it describes only the now-deleted UI
subsystem, delete it; if it has real content still relevant to `app/`,
move it to `app/README.md`, then trim any stale references during Task 6
(don't try to fully rewrite it in this task — that's Task 6's job, this
task just needs the file in the right place).

```bash
rmdir backend  # only after confirming it's empty
```

- [ ] **Step 2: Rewrite every `backend.` import to `app.`**

For each of the 24 files listed above, replace every `from backend.` with
`from app.` and every `import backend.` with `import app.` — this is a
literal string substitution on the import statement's package prefix
only; nothing else in any of these files changes. Do NOT do a blind
repo-wide find/replace of the substring `backend` (that would also touch
prose, variable names, or unrelated strings) — scope the substitution to
lines matching `from backend.` / `import backend.` specifically, in
exactly these 24 files.

After the substitution, `app/cli/main.py` becomes the CLI's actual entry
module — confirm its own imports (e.g. `from app.erd.loader import
load_erd`, `from app.services.code_generator import CodeGenerator`, or
whatever its current exact import list is — read the file to confirm)
are all correctly rewritten.

- [ ] **Step 3: Apply the `templates_dir` fix**

In `app/services/code_generator.py` (now at its new path), apply the exact
fix specified in this plan's Global Constraints section under "The
`templates_dir` fix's exact resolution expression" — add `Optional` to the
`typing` import, add the `_DEFAULT_TEMPLATES_DIR` module-level constant,
change the constructor signature and its first body line exactly as
specified there. Re-read that section now rather than relying on memory of
it.

- [ ] **Step 4: Update `pyproject.toml`**

Apply the exact diff specified in this plan's Global Constraints section
under "`pyproject.toml` diff shape" — re-read that section now. Six
changes: the `[project.scripts]` entry point, `[tool.hatch.build.targets.wheel]
packages`, drop `python-multipart`, add `mkdocs`/`mkdocs-material` to both
dev dependency lists, and fix the two stale inline comments referencing
`backend/tests/...`/`backend/templates/...` paths.

- [ ] **Step 5: Add the root `.gitignore`**

Create `.gitignore` at repo root with at least:
```
__pycache__/
*.pyc
.venv/
venv/
workspace/
.pytest_cache/
*.egg-info/
.env
```

- [ ] **Step 6: Reinstall and run the full suite**

```bash
uv sync
uv run pytest app/tests -q
```
Expected: PASS, 252 (pure rename at the test level — no test's assertions
change, only the module paths they import from). If anything fails,
diagnose the actual import-path or path-resolution error for real — do
not weaken any assertion or skip any test to work around a rename mistake;
find and fix the actual missed reference.

- [ ] **Step 7: Confirm the CLI entry point itself works**

```bash
uv run backstudio --help
uv run backstudio validate examples/blog.yml
```
Expected: both succeed — this is the first direct proof the
`[project.scripts]` entry point change (Step 4) actually resolves, which
the pytest suite alone does not exercise (pytest imports `app.cli.main`
directly, it doesn't invoke the installed console-script entry point).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Rename backend/ to app/, rewrite all imports, update pyproject.toml, fix templates_dir CWD-dependence"
```

---

### Task 5: Verify the rename end-to-end

**Files:** none modified — this task is pure verification. If it finds a
real problem, the fix belongs in Task 4's own commit area (amend/fix
forward in a new commit here, documented as a correction) rather than
silently patched without a record.

**Interfaces:** none.

- [ ] **Step 1: The CWD-independence regression test (proves Task 4's `templates_dir` fix is real, not cosmetic)**

The existing test suite alone does NOT prove this fix works — pytest's own
CWD happens to already be the repo root in this workflow, so the *old*
CWD-relative bug would also have passed the full suite. Write and run a
direct, one-off repro from outside the repo root:

```bash
mkdir -p /tmp/cwd-independence-check
cd /tmp/cwd-independence-check
uv run --project /path/to/this/repo backstudio generate /path/to/this/repo/examples/blog.yml --output ./out
```
(Adjust the exact invocation to however `uv run --project` / an installed
console script actually resolves in this environment — the point is: the
process's CWD must NOT be the repo root when `generate` runs.) Expected:
generation succeeds and produces real output under `./out` — if it instead
fails with a template-not-found error, Task 4's Step 3 fix did not
actually take effect; go back and diagnose it there, don't patch around it
here.

If `uv run --project` doesn't cleanly support this from an external CWD in
practice, an equivalent Python-level repro is acceptable: from a script or
interactive session with CWD set to somewhere outside the repo, `import
sys; sys.path.insert(0, "/path/to/repo"); from app.services.code_generator
import CodeGenerator; CodeGenerator()` and confirm `.templates_dir` points
at the real `app/templates/` directory regardless of the process's actual
CWD. Either form proves the same thing — use whichever is more reliable in
this environment, but don't skip this check by only re-running pytest.

- [ ] **Step 2: CLI smoke test against a scratch output**

```bash
uv run backstudio generate examples/blog.yml --output /tmp/backstudio-smoke-test --force
```
Read at least 3-4 of the generated files directly (e.g. `server.py`,
`database/models.py`, one `modules/<name>/service.py`) to confirm they
render real, non-empty, syntactically sane Python — not just that the
command exited 0. If quick to check, also confirm the generated project's
own dependencies would install and the app would start
(`uv pip install -r requirements.txt` inside the generated output +
`uvicorn server:app --port 0` or equivalent smoke boot, matching whatever
this repo's existing `test_generated_project_runtime.py` tests already do
for other fixtures — reuse that pattern rather than inventing a new one).

- [ ] **Step 3: Repo-wide leftover-reference sweep**

```bash
grep -rln "backend\." --include="*.py" . | grep -v __pycache__ | grep -v "/\.venv/" | grep -v "/venv/"
grep -rln "backend/" --include="*.md" --include="*.toml" --include="*.jinja" . | grep -v __pycache__
grep -rln "\bfrontend\b\|mcp_server" --include="*.py" --include="*.toml" . | grep -v __pycache__
```
Expected: zero matches from the first two (any `backend/` mention
remaining in `README.md` at this point is expected and gets fixed in Task
6, not here — but confirm no `.py`/`.toml`/`.jinja` file references it).
The third command may still find README.md prose mentions (also Task 6's
job) — but zero matches in any `.py`/`.toml` file.

- [ ] **Step 4: Full suite, one more time, for the record**

Run: `uv run pytest app/tests -q`
Expected: PASS, 252.

- [ ] **Step 5: Commit (only if Step 1-3 required a real fix; otherwise this task produces no commit)**

If everything passed cleanly, this task is verification-only — no commit
needed, move directly to Task 6. If Step 1 or Step 3 surfaced a genuine
missed reference, fix it directly, re-run Steps 1-4, then:
```bash
git add -A
git commit -m "Fix missed backend-path reference found during rename verification"
```

---

### Task 6: README rewrite

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the final `app/`-rooted layout (Task 4), the real current CLI
  commands/flags (`app/cli/main.py`), the mkdocs page paths this task
  links out to (Task 7-10's pages — those tasks run after this one per
  the plan's ordering, so this task links to paths that will exist once
  Tasks 7-10 land; use the exact paths from this plan's Task 7-10
  sections, they are fixed in advance).
- Produces: the new front-door README other tasks/users read going
  forward.

- [ ] **Step 1: Read the current README in full, and read the real source it will describe**

Read `README.md` completely (before editing — you need to know exactly
what's being replaced, including the `## Legacy: Visual UI (unmaintained)`
and `## Checksum system` sections this task resolves per the spec). Then
read, directly, the actual current state of what the new README will
describe: `app/cli/main.py` (exact command names, exact flags/options —
do not trust the old README's command examples, re-derive them from the
live file), `examples/blog.yml` (for the quick-start example), and the
top-level `app/` layout (for the Project layout section).

- [ ] **Step 2: Write the new README**

Structure, per the spec (Section 4) — 7 sections:

1. **Hero** — keep the existing logo image reference (`assets/logo.svg` or
   whatever the current exact path/markdown is — read the current
   README's hero section to get the exact syntax, don't guess it) and a
   one-line pitch.
2. **What it is / why** — ERD YAML in, FastAPI project out, short and
   concrete. Fold in the one real point from the old `## Checksum system`
   section (generation is deterministic — same ERD always produces the
   same output) as a sentence here, not as its own heading.
3. **Quick start** — install (`uv sync` or equivalent, read the current
   README's install section and verify it's still accurate against
   `pyproject.toml`), a minimal ERD example (can reuse a trimmed version
   of `examples/blog.yml`'s shape or write an even smaller one — verify it
   would actually validate via `uv run backstudio validate` against it, not
   just visually resemble valid YAML), `backstudio generate`, then running
   the generated project.
4. **Feature overview** — short paragraphs (not full mechanics) for auth,
   RBAC, Row-Level Security, async database support, admin user
   management — each linking to its corresponding `docs-site/features/*.md`
   page (Task 9): `docs-site/features/auth.md`, `rbac.md`, `rls.md`,
   `async.md` (admin user management is covered within `auth.md`, per Task
   9's own scope below — link there for it, don't invent a 5th features
   page).
5. **CLI reference** — brief command list (the real 3 commands from
   `app/cli/main.py` — verify the exact current list, don't assume it's
   still exactly `validate`/`visualize`/`generate` without checking),
   linking to `docs-site/cli-reference.md` (Task 7) for full flag details.
6. **Project layout** — a tree diagram of the actual current `app/`-rooted
   structure (verify against the real directory listing at time of
   writing, not copied from this plan's Global Constraints section without
   checking it still matches).
7. **Contributing / License** — carry the current README's `##
   Contributing` and `## License` sections over verbatim (read them first
   to confirm their current exact content before copying).

Delete `## Legacy: Visual UI (unmaintained)` entirely (describes the
subsystem Task 1 deleted).

- [ ] **Step 3: Verify every factual claim**

Before finishing, go back through the new README and, for every command,
flag, or example shown, confirm it against the live repo one more time
(not just once during drafting) — run every shown command for real if it's
cheap to do so (`backstudio --help`, `backstudio validate
examples/blog.yml`, etc.) and confirm the output matches what the README
claims.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Rewrite README as a short front door, linking out to the new docs site for full feature/CLI reference"
```

---

### Task 7: mkdocs scaffolding + Getting Started + CLI Reference

**Files:**
- Create: `mkdocs.yml`
- Create: `docs-site/index.md`
- Create: `docs-site/getting-started/installation.md`
- Create: `docs-site/getting-started/quick-start.md`
- Create: `docs-site/cli-reference.md`

**Interfaces:**
- Consumes: `app/cli/main.py` (the real, current CLI commands/flags/help
  text — the primary source for this task), `pyproject.toml` (for
  install/dependency info).
- Produces: the mkdocs site's skeleton nav + its first 4 pages — Tasks
  8-10 add the remaining nav sections to the same `mkdocs.yml`'s `nav:`
  list.

- [ ] **Step 1: Write `mkdocs.yml`**

```yaml
site_name: BackStudio
site_description: Generate FastAPI backend projects from a single ERD YAML file
docs_dir: docs-site

theme:
  name: material
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      toggle:
        icon: material/brightness-4
        name: Switch to light mode
  features:
    - navigation.sections
    - navigation.top
    - content.code.copy
    - search.suggest

markdown_extensions:
  - admonition
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
  - pymdownx.highlight
  - pymdownx.tabbed:
      alternate_style: true
  - tables
  - toc:
      permalink: true

nav:
  - Home: index.md
  - Getting Started:
      - Installation: getting-started/installation.md
      - Quick start: getting-started/quick-start.md
  - ERD Reference:
      - Schema overview: erd-reference/overview.md
      - Full field reference: erd-reference/fields.md
  - Features:
      - Auth: features/auth.md
      - RBAC: features/rbac.md
      - Row-Level Security: features/rls.md
      - Async database support: features/async.md
  - Architecture:
      - Pipeline overview: architecture/pipeline.md
      - Template system: architecture/templates.md
      - Adding a new feature: architecture/extending.md
  - CLI Reference: cli-reference.md
```

This full `nav:` list is written now, in this task, even though Tasks 8-10
create the pages it points to later — `mkdocs build --strict` (Task 11)
will fail loudly on any nav entry with no matching file until all of Tasks
7-10 land, which is expected and fine mid-plan; don't work around it by
trimming the nav early and re-adding it later.

- [ ] **Step 2: `docs-site/index.md`**

Cover: what BackStudio is (one paragraph, can reuse the README's "What it
is / why" wording once Task 6 has written it — read Task 6's final
`README.md` for this, don't duplicate independent phrasing that could
drift from it), a short "why ERD-driven" pitch, and a prominent link to
Getting Started → Installation as the next step.

- [ ] **Step 3: `docs-site/getting-started/installation.md`**

Cover: exact install steps, verified against the real current
`pyproject.toml` (Python version constraint, `uv` usage, `requires-python
= ">=3.11,<3.12"` — quote the actual constraint from the live file, don't
assume it's still exactly that) and the real current `[project.scripts]`
entry point. Show the actual command(s) to get `backstudio --help`
working from a fresh clone.

- [ ] **Step 4: `docs-site/getting-started/quick-start.md`**

Cover: write a minimal real ERD YAML inline (verify it actually validates
via `uv run backstudio validate` against it — don't just show YAML that
looks plausible), run `backstudio generate` against it, show what gets
produced (a real directory listing from an actual generation run, not an
imagined one), and how to run the generated project. This should be
independently runnable by a reader copy-pasting the page's own commands —
verify that by actually running them yourself as if you were that reader.

- [ ] **Step 5: `docs-site/cli-reference.md`**

Cover every command in `app/cli/main.py` (read the file directly — verify
the current exact command names and every `typer.Argument`/`typer.Option`
per command, including help text, defaults, and short/long flag forms).
For each command: what it does, its arguments/options with their real
defaults, and one real example invocation. Do not omit a command or a flag
because it seems minor — this page's whole job is completeness that the
README's brief command list (Task 6) intentionally doesn't provide.

- [ ] **Step 6: Local build check (partial — full `--strict` build happens in Task 11 once all pages exist)**

```bash
uv run mkdocs build --strict 2>&1 | head -50
```
Expected at this point: it will report missing files for every nav entry
Tasks 8-10 haven't created yet — confirm the *errors are only* about those
not-yet-created files (`erd-reference/*.md`, `features/*.md`,
`architecture/*.md`) and not about anything from this task's own 4 pages
or `mkdocs.yml` itself (a syntax error in this task's own YAML/markdown
would also show up here and must be fixed now, not left for Task 11).

- [ ] **Step 7: Commit**

```bash
git add mkdocs.yml docs-site/
git commit -m "Add mkdocs scaffolding, Getting Started, and CLI Reference pages"
```

---

### Task 8: mkdocs ERD Reference pages

**Files:**
- Create: `docs-site/erd-reference/overview.md`
- Create: `docs-site/erd-reference/fields.md`

**Interfaces:**
- Consumes: `app/erd/schema.py` (the actual Pydantic ERD schema — the
  single source of truth for every field name, type, and default this
  task documents) and `app/erd/loader.py` (for any cross-field validation
  rules worth documenting, e.g. the auth-expansion plan's `rbac.enabled`
  requiring `"admin"` in `rbac.roles` rule, and `admin_approval` requiring
  `rbac.enabled` — these are real, currently-enforced rules a reader
  writing an ERD YAML needs to know about, not just the field shapes in
  isolation).

- [ ] **Step 1: `docs-site/erd-reference/overview.md`**

Cover: the top-level shape of an ERD YAML file (the major top-level keys —
`project`, `database`, `auth`, `rbac`, `entities`, `services`/`modules` —
read `app/erd/schema.py`'s top-level model to confirm the real current set
and their real names, don't assume this plan's own prose list above is
exhaustive or current) with one short example snippet per key, and a
pointer to the Full field reference page for exhaustive detail.

- [ ] **Step 2: `docs-site/erd-reference/fields.md`**

The exhaustive reference. For every Pydantic model in `app/erd/schema.py`,
document every field: its name, type, whether required or its literal
default value, and a one-line description (use the model's own `Field(...,
description=...)` text where present as the base, expand only where the
description alone would be unclear to a new reader — don't just copy
`description=` strings verbatim without reading whether they're actually
sufficient). Organize by section matching the overview page's top-level
keys. Specifically verify and correctly state (these are exactly the kind
of specific values that go stale and this plan's own survey flagged the
JWT lifetime fields by name earlier this session):
- The `auth.registration.mode` enum's exact allowed values and what each
  requires/gates (cross-check against `app/erd/loader.py`'s validation
  rules, not just the schema's own field definition).
- All 4 JWT lifetime fields under `auth.jwt` — read `JWTSpec` in
  `app/erd/schema.py` directly for their exact field names and exact
  default values; do not carry over any number from memory or from this
  plan's own prose (this plan does not restate them precisely on purpose,
  to force verification against the live source rather than propagating a
  figure that might already be stale).
- `rbac.enabled`/`rbac.roles`/`rbac.default_permissions`'s shape and the
  cross-field validation rules from `app/erd/loader.py` (admin role
  requirement, admin_approval's rbac dependency).
- `database.async_mode`'s effect (what it changes about generated code, at
  a level appropriate for an ERD reference — link to
  `docs-site/features/async.md` for the full mechanics rather than
  duplicating them here).

- [ ] **Step 3: Build check**

```bash
uv run mkdocs build --strict 2>&1 | grep -i "erd-reference\|error"
```
Expected: no errors referencing this task's 2 files (errors about
`features/*.md`/`architecture/*.md` not yet existing are still expected
and fine at this point).

- [ ] **Step 4: Commit**

```bash
git add docs-site/erd-reference/
git commit -m "Add mkdocs ERD Reference pages (schema overview and full field reference)"
```

---

### Task 9: mkdocs Features pages

**Files:**
- Create: `docs-site/features/auth.md`
- Create: `docs-site/features/rbac.md`
- Create: `docs-site/features/rls.md`
- Create: `docs-site/features/async.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-09-10-auth-expansion-design.md`,
  the RLS design spec, and the async-support design spec under
  `docs/superpowers/specs/` (exact filenames — list that directory and
  confirm the real filenames, don't guess the async-support/RLS spec
  filenames' exact dates) as starting drafts; the actual current templates
  (`app/templates/Python/auth/*.jinja`, `app/templates/Python/rbac*`, the
  RLS-generating template(s), the async-conditional Jinja branches) as the
  verification source of truth.

- [ ] **Step 1: `docs-site/features/auth.md`**

Cover, each cross-checked against the live `app/templates/Python/auth/*.jinja`
templates and `app/erd/schema.py`'s `RegistrationSpec`/`JWTSpec` (not
transcribed from the spec without checking):
- The 3 registration modes (`open`, `email_verification`,
  `admin_approval`) — what each gates, referencing the real current
  `authenticate_user`/route-gating logic in `app/templates/Python/auth/service.py.jinja`
  and `routes.py.jinja`.
- The password-reset single-use mechanism (the SHA256-truncated
  password-hash-fingerprint technique) — read
  `verify_password_reset_token`'s actual current implementation directly;
  the auth-expansion spec describes the *intended* design, but the
  binding-signature correction and the final-review fix round both landed
  as real code changes after that spec was written — describe what the
  code does today, using the spec only to understand the intent behind it.
- Admin user management (list/get/set-roles/deactivate/reactivate/approve)
  — including that a bootstrap admin is now auto-approved under
  `admin_approval` mode (this was a real bug fixed in this feature's own
  final review — verify the current behavior directly against
  `register_user`'s live code rather than the spec, which predates that
  fix).
- The documented limitation that password reset does not revoke
  already-issued access/refresh tokens (this is real, current, intentional
  — carry it over from the spec's own Non-goals addendum, but verify the
  addendum is still there and still accurate).
- Link to `docs-site/erd-reference/fields.md`'s auth section for the full
  YAML field shape rather than repeating it here.

- [ ] **Step 2: `docs-site/features/rbac.md`**

Cover: the `rbac.enabled`/`rbac.roles`/`rbac.default_permissions` shape at
a feature-explanation level (not a field-by-field dump — that's the ERD
Reference's job), how `require_roles(...)` gating works in generated
routes (read the actual RBAC dependency template), and the first-user
bootstrap convention (first registered user gets every declared role) —
verify this is still accurate against the live `register_user` template
code, which now also has the `admin_approval` auto-approval addition from
Task 9's auth.md research — cross-reference rather than re-deriving twice.

- [ ] **Step 3: `docs-site/features/rls.md`**

Cover: what row-level access control does (owner-based row filtering),
how it's configured in the ERD YAML, the cascade-ownership mechanism for
related entities, and the bypass-role concept — cross-check every claim
against the actual current RLS-generating template code (find it — it
lives somewhere under `app/templates/Python/`, locate it directly rather
than assuming a path) and the RLS design spec under `docs/superpowers/specs/`.
The RLS plan's own final review caught a real Critical bug (a bypass-role
caller silently writing a NULL owner) — if that fix is visible in the
current template code (it should be, since RLS shipped and merged earlier
this session), the page's description should match the *fixed* behavior,
not the spec's pre-fix description.

- [ ] **Step 4: `docs-site/features/async.md`**

Cover: `database.async_mode: true`'s effect on generated code (async
SQLAlchemy engine/session, `await`ed queries, async Alembic migrations via
`run_sync()`), what changes for someone running the generated project
(different `DATABASE_URL` scheme, e.g. `sqlite+aiosqlite://` vs
`sqlite://` — verify the exact scheme prefixes against real generated
output, don't assume), and any caveat worth surfacing (check the
async-support spec's own Non-goals/caveats section for anything still
accurate).

- [ ] **Step 5: Build check**

```bash
uv run mkdocs build --strict 2>&1 | grep -i "features\|error"
```
Expected: no errors referencing this task's 4 files.

- [ ] **Step 6: Commit**

```bash
git add docs-site/features/
git commit -m "Add mkdocs Features pages (auth, RBAC, RLS, async), verified against live template code"
```

---

### Task 10: mkdocs Architecture pages

**Files:**
- Create: `docs-site/architecture/pipeline.md`
- Create: `docs-site/architecture/templates.md`
- Create: `docs-site/architecture/extending.md`

**Interfaces:**
- Consumes: `app/erd/loader.py`, `app/erd/translate.py`,
  `app/services/code_generator.py` (the actual, current pipeline
  implementation — this task requires real understanding of these 3
  files' current flow, not paraphrase of what they might do).

- [ ] **Step 1: `docs-site/architecture/pipeline.md`**

Read `app/erd/loader.py` (YAML → validated `ERDConfig`, including its
cross-field validation rules), `app/erd/translate.py` (`ERDConfig` →
the flat `state` dict `CodeGenerator` consumes — including what
`translate()` actually computes, e.g. `registration_mode`,
`security_config`, mode-aware `User` fields), and
`app/services/code_generator.py` (`state` dict → rendered files via
Jinja2, including the `{'project': state}` vs `{'project': state,
'module': module}` context-shape distinction that's been load-bearing in
at least one prior feature this session) — in full, not skimmed. Write a
Mermaid diagram (using the `mermaid` fenced-code-block syntax configured
in Task 7's `mkdocs.yml`) showing the real flow: `ERD YAML → loader.py
(validate) → translate.py (ERDConfig → state dict) → code_generator.py
(state → Jinja2 render) → generated FastAPI project`. Accompany the
diagram with prose describing each stage's actual responsibility, each
stage's actual input/output shape (name real function/class names:
`load_erd()`, `translate()`, `CodeGenerator.generate_project()` — verify
these are still the real current names before citing them).

- [ ] **Step 2: `docs-site/architecture/templates.md`**

Cover: where templates live (`app/templates/Python/`), the Jinja2
environment's actual configured settings (`trim_blocks=True,
lstrip_blocks=True` — verify against the real `Environment(...)` call in
`code_generator.py`), the two different context shapes a template can
receive (`{'project': state}` for most files vs `{'project': state,
'module': module}` for per-module files — verify which templates get
which by reading `code_generator.py`'s actual render calls, don't assume),
and the `modules`-loop vs `auth`-module generation distinction (both real,
both currently active, different from the now-deleted dead `services`
loop this plan's Task 3 removed).

- [ ] **Step 3: `docs-site/architecture/extending.md`**

Cover: a concrete walkthrough of "how would I add a new ERD-configurable
feature" grounded in how a real recent feature was actually built this
session (e.g. the auth-expansion feature's shape: new fields on
`app/erd/schema.py`'s Pydantic models → new validation in
`app/erd/loader.py` → new wiring in `app/erd/translate.py`'s `translate()`
→ new/modified `.jinja` templates → new tests). Keep this concrete and
short — a numbered list of the real files a contributor would touch, in
the real order they'd need to touch them, not an abstract essay.

- [ ] **Step 4: Build check**

```bash
uv run mkdocs build --strict 2>&1 | grep -i "architecture\|error"
```
Expected: no errors referencing this task's 3 files.

- [ ] **Step 5: Commit**

```bash
git add docs-site/architecture/
git commit -m "Add mkdocs Architecture pages (pipeline, template system, extending guide)"
```

---

### Task 11: Final docs verification + backlog close-out

**Files:**
- Modify: `docs/superpowers/backlog.md`

**Interfaces:** none.

- [ ] **Step 1: Full strict mkdocs build**

```bash
uv run mkdocs build --strict
```
Expected: exits 0 with no warnings/errors — every nav entry from Task 7's
`mkdocs.yml` now has a matching file (Tasks 7-10 created all of them), no
broken internal links. If anything fails, fix the actual broken
link/missing file/YAML syntax issue directly — this is the last checkpoint
before this plan is considered done, don't leave a known-broken build.

- [ ] **Step 2: Final repo-wide grep sweep**

```bash
grep -rln "backend\." --include="*.py" --include="*.toml" . | grep -v __pycache__ | grep -v "/\.venv/" | grep -v "/venv/"
grep -rln "backend/" . 2>/dev/null | grep -v __pycache__ | grep -v "/\.venv/" | grep -v "/venv/" | grep -v "\.git/"
grep -rln "\bfrontend\b\|mcp_server\|project_service\|ProjectService" --include="*.py" --include="*.md" --include="*.toml" . | grep -v __pycache__
```
Expected: zero matches across all three — this is the plan's true final
check that nothing from any of the 11 tasks was missed anywhere in the
repo, not just in the files each task directly touched.

- [ ] **Step 3: Full test suite, one final time**

Run: `uv run pytest app/tests -q`
Expected: PASS, 252.

- [ ] **Step 4: Close out the backlog item**

In `docs/superpowers/backlog.md`, find the "Repo cleanup — CLI-only"
item's `- [ ] **Strip the repo down to just the CLI tool.**` entry. Check
it off (`[x]`) and append a `Fixed 2026-09-10:` summary in the style of
the other closed-out items in this file (read 1-2 nearby closed-out items
for the exact style first). The summary must say explicitly that the
shipped scope is larger than what this backlog item originally described
— it also renamed `backend/` to `app/` (the item's original text didn't
anticipate this) and added a full `docs-site/` mkdocs documentation site
plus a rewritten front-door README (neither was part of the item's
original text either) — point to this plan
(`docs/superpowers/plans/2026-09-10-repo-restructure-and-docs.md`) and its
spec (`docs/superpowers/specs/2026-09-10-repo-restructure-and-docs-design.md`)
for the full detail, same pattern as every other closed-out item in this
file.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/backlog.md
git commit -m "Verify mkdocs strict build, final repo-wide sweep, close out the repo-cleanup backlog item"
```

---

## Final whole-branch review

Once all 11 tasks are complete and individually reviewed clean, dispatch a
final, broad review on the most capable available model, per
`superpowers:subagent-driven-development`'s standard closing step —
reviewing the *whole* diff for cross-task issues no single task's review
could see. Specific things worth checking, given this plan's particular
shape: did every one of the 24 import-rewrite files in Task 4 actually get
rewritten (a single missed file would likely surface as an import error
during Task 4's own test run, but double-check nothing was silently
caught by a `try`/`except ImportError` somewhere that could mask it); does
any docs-site page (Tasks 7-10) state a fact that was true when its task
ran but has since drifted (unlikely within this plan's own short
execution window, but the discipline the plan repeatedly enforces exists
because it has genuinely happened in this repo's history — apply the same
scrutiny to this plan's own docs pages that Task 9's own text applies to
the specs it draws from); does `mkdocs build --strict` still pass on the
final merged state; does the README (Task 6) actually link to real,
existing docs-site pages (Tasks 7-10 landing after Task 6 was written
means Task 6 wrote links to paths that didn't exist yet at the time — this
whole-branch review is the first point where every linked path is
guaranteed to actually exist, verify it). Budget for at least one fix
round afterward if anything real surfaces, same as every prior plan's
precedent this session.
