# Repo restructure, README rewrite, and mkdocs documentation site — Design

## 1. Motivation

The repo started as a UI-driven backend generator (`backend/` = the FastAPI
server + `frontend/` = the React UI + `mcp_server/`) and was pivoted this
session to an ERD-driven CLI tool. The old UI-serving subsystem was never
removed. The backlog's own "do last" cleanup item asked to strip the repo
down to just the CLI — but doing that move is also the natural moment to
fix two things that have been getting worse all session:

- The `backend/` directory name no longer makes sense once there's no
  `frontend/` to distinguish it from, and it needlessly nests every module
  one level deeper than necessary for what is now a single-purpose CLI tool.
- The root `README.md` has absorbed a full prose section for every feature
  shipped this session (RLS, async support, auth expansion) and is now
  43KB — it has become the documentation, when it should be a front door.
  There is nowhere else for deep reference material to live.

This pass does three things together, since they touch overlapping files
and would conflict if sequenced separately: rename/flatten `backend/` →
`app/` while deleting the dead UI-serving code found during survey; rewrite
the README as a short front door; and stand up an `mkdocs`-based
documentation site as the actual reference material the README links to.

## 2. Scope boundary

In scope: the repo's own structure, its own README, and a new local-only
documentation site describing how to use and how BackStudio itself works.

Out of scope: any change to what generated projects look like (their
`app/` naming is unaffected — this only renames *this* repo's own
top-level layout, not the templates' output structure, which already uses
its own separate `modules/`, `database/`, etc. layout and is untouched by
this work). No CI/deployment wiring for the docs site (local `mkdocs
serve`/`mkdocs build` only, per explicit decision). No change to any
already-shipped feature's behavior.

## 3. Package restructure: `backend/` → `app/`

### 3.1 What moves as-is

`backend/cli/`, `backend/erd/`, `backend/services/` (minus
`project_service.py`, see below), `backend/templates/` (minus 3 dead
`Python/service/*.py.jinja` files, see 3.3), `backend/tests/`,
`backend/utils/` all move to the equivalent path under `app/`, verbatim.

### 3.2 What does NOT move (deleted, confirmed dead by direct survey)

- `backend/api/` (`routes.py` — the old REST API, 500+ lines, only ever
  called by `frontend/` and `examples/example_project_generator.py`)
- `backend/main.py` (the old FastAPI app entrypoint serving `backend/api/`)
- `backend/services/project_service.py` (in-memory project-state service
  backing the old REST API — confirmed via repo-wide grep that nothing
  outside `backend/api/routes.py` and this file's own module import it)
- `backend/config/` — both `config.py` and `__init__.py` are literally
  empty (0 lines each), confirmed via direct read, referenced nowhere
- `backend/requirements.txt` — a separate, older requirements file
  (predating `pyproject.toml` as the source of truth) for standalone-
  running the old UI server; `pyproject.toml`'s own dependency list is
  authoritative and already covers everything the CLI path needs
- `backend/schemas/`, **mostly**: `data.py` alone has 16 classes; a direct
  grep of every `backend.schemas` import across the whole repo (not just
  tests) shows only 4 of those classes — `Cardinality`, `LazyStrategy`,
  `FieldType`, `ModelField` — are ever imported outside
  `backend/services/project_service.py`. The remaining 12 classes in
  `data.py`, plus all of `configuration.py`, `dependency.py`,
  `middleware.py`, `project.py`, `service.py` are old-UI request/response
  DTOs, confirmed used only by `project_service.py`/`backend/api/routes.py`
  (both being deleted). **Correction to the backlog's original survey**,
  which assumed `backend/schemas/` was fully dead — it is not; the 4
  classes above are load-bearing for the CLI's own ERD code.
  - Fix: relocate `Cardinality`, `LazyStrategy`, `FieldType`, `ModelField`
    directly into `app/erd/schema.py` (the primary consumer). Delete the
    rest of `backend/schemas/` entirely. Update the 3 other importers
    (`app/erd/visualize.py`, `app/tests/test_auth_expansion_generation.py`,
    `app/tests/test_auth_generation.py`, `app/tests/test_rls_generation.py`
    — 4 files total including the relocation target) to import from
    `app.erd.schema` instead of the deleted `backend.schemas.data`.

Also deleted, at repo root (unaffected by the rename, confirmed dead by
direct survey, same conclusions as the original backlog item):
`frontend/`, `mcp_server/`, `setup.bat`/`setup.sh`, `start.bat`/`start.sh`,
`stop.bat`/`stop.sh`, `examples/example_project_generator.py` (drives the
old REST API via the `requests` library — dead; `examples/blog.yml` stays,
it is a genuine CLI ERD example, and matches the already-generated
`workspace/BlogAPI` output sitting in this checkout), `RELEASE_NOTES.md`
(per explicit decision — deleted outright rather than pruned, since it
documents a specific past release and once that release's subsystem no
longer exists in the repo, keeping half-accurate historical notes serves
no one).

### 3.3 Dead code inside files that DO move

- `app/services/code_generator.py`: remove the `for service in
  state.get('services', [])` loop (renders `Python/service/service.py.jinja`,
  `schemas.py.jinja`, `routes.py.jinja` per-service). Confirmed dead:
  `app/erd/translate.py`'s `translate()` always emits a hardcoded
  `"services": []` — this loop has never executed for any ERD-driven
  generation. Delete those 3 templates. **Keep**
  `Python/service/module_service.py.jinja`, `module_schemas.py.jinja`,
  `module_routes.py.jinja` — these back the real, separate `modules` loop
  a few lines below and are what every ERD-driven project actually uses.
- `app/erd/translate.py`: drop the now-pointless `"services": []` key from
  `translate()`'s returned dict.
- `app/templates/Python/README.md.jinja`: remove the `{% if
  project.services %}` blocks (there are 4: two content blocks, one
  `{% for %}` each, plus one `and not project.services` clause in the
  empty-state check) — simplify back to `modules`/`auth` only, matching
  what the backlog's original note asked for.

### 3.4 Import rewrite

A direct repo-wide grep for `from backend\.` / `import backend\.` across
every `.py` file (excluding `__pycache__`/`.venv`/`venv`) finds 27 files.
3 are deleted outright (`backend/api/routes.py`, `backend/main.py`,
`backend/services/project_service.py`). The remaining 24 — every file
under `cli/`, `erd/`, `services/` (minus the deleted one), and all 19 test
files in `tests/` — need `backend.` rewritten to `app.` throughout (import
statements only; this is a mechanical, repo-wide find/replace of the
package prefix, not a logic change).

`app/cli/main.py`'s own internal imports need the same treatment; it also
becomes the new entry point.

### 3.5 `pyproject.toml`

- `[project.scripts] backstudio = "app.cli.main:app"` (was
  `"backend.cli.main:app"`)
- `[tool.hatch.build.targets.wheel] packages = ["app"]` (was `["backend"]`)
- Drop `python-multipart==0.0.6` from `dependencies` — confirmed via
  repo-wide grep for `multipart` across all `.py` files and `pyproject.toml`
  itself that nothing imports or otherwise needs it once `backend/api/` is
  gone (it exists to support FastAPI's `Form`/file-upload handling, which
  only the old UI's REST API ever used).
- Add `mkdocs`, `mkdocs-material` (theme, with its built-in Mermaid support
  via `pymdownx.superfences`) to `[project.optional-dependencies] dev` and
  the matching `[dependency-groups] dev` list (docs tooling is a dev-only
  concern, matching how `pytest`/`httpx`/etc. are already scoped there).

### 3.6 `CodeGenerator`'s `templates_dir` — fixed while touching this line anyway

`app/services/code_generator.py`'s `__init__` currently defaults
`templates_dir: str = "backend/templates"` — a path resolved against the
process's current working directory, not against the module's own
location. Every call site in the entire codebase (the CLI itself, and
every one of ~100+ test instantiations) relies on this default with no
override, meaning the installed `backstudio` CLI already only works
correctly when invoked from the repo root today — a real, pre-existing
fragility, not introduced by this restructure. Since this exact default
value has to change for the rename regardless (`"backend/templates"` →
some new value), swapping it for another CWD-relative string would just
perpetuate the same bug under a new name. Fix: resolve it relative to the
module's own file location instead —
`Path(__file__).resolve().parent.parent / "templates"` (from
`app/services/code_generator.py`, `.parent.parent` reaches `app/`, then
`/ "templates"` reaches `app/templates/`) — so the CLI works regardless of
the caller's CWD, matching how `templates_dir` is documented in its own
docstring as "Directory containing Jinja2 templates" without any stated
CWD requirement. The parameter itself, its type, and every call site's
lack of an override are all unchanged — only the default's *value* and how
it is computed change.

### 3.7 Root-level additions

New `.gitignore` at repo root (none exists today — confirmed via direct
check). Minimum entries: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`,
`workspace/`, `.pytest_cache/`, `*.egg-info/`, `.env`. (`workspace/`,
`venv/`, `.venv/`, `__pycache__/` are already untracked today — this does
not remove any tracked file, it only stops them appearing as noise in
`git status`.)

## 4. README rewrite

Current README (43KB) is replaced with a short front door. Structure:

1. **Hero** — logo (kept, unchanged asset), one-line pitch
2. **What it is / why** — ERD YAML in, FastAPI project out; short, concrete
3. **Quick start** — install, minimal ERD example, `backstudio generate`,
   run the generated project — the fastest path to a working result
4. **Feature overview** — short, scannable summaries of auth, RBAC, RLS,
   async support, admin user management — each a paragraph or two, linking
   out to the corresponding mkdocs page for full mechanics rather than
   inlining them (this is the structural change: today's README **is**
   the documentation for these features; going forward it is a pointer to
   it)
5. **CLI reference** — brief command list, links to the full mkdocs CLI
   reference page
6. **Project layout** — updated to the new `app/`-rooted structure
7. **Contributing / License** — the current README already has both
   sections (`## Contributing`, `## License`); carried over unchanged

Two small current sections don't map cleanly onto the new structure and
are resolved explicitly rather than left ambiguous: `## Legacy: Visual UI
(unmaintained)` is deleted outright (describes the exact subsystem being
removed in Section 3); `## Checksum system` is a 2-line stub that itself
references "the legacy paths" and doesn't describe an actual checksum
mechanism — its one real point (generation is deterministic) is folded
into the "What it is / why" section instead of staying a standalone
heading.

Every factual claim in the new README (commands, flags, example ERD
snippets) gets verified against the actual current CLI/code before being
written, not carried over from the old README's prose by assumption —
matching the verification discipline already established this session for
docs work (this exact discipline caught real doc inaccuracies in three
separate features' final reviews earlier this session).

## 5. Documentation site (`docs-site/`, mkdocs)

### 5.1 Directory naming

This repo already has a `docs/` folder — `docs/superpowers/` — used all
session for this project's own internal specs/plans/backlog archive
(including this very document). It is unrelated to end-user documentation
and stays exactly where it is, untouched. mkdocs' own source content goes
in a new, separate `docs-site/` folder at repo root, with `mkdocs.yml`
setting `docs_dir: docs-site`.

### 5.2 Tooling

`mkdocs` + the `mkdocs-material` theme. Enables: search, light/dark mode,
admonitions, and Mermaid diagram rendering (via
`pymdownx.superfences`/`pymdownx.highlight`, both bundled with
`mkdocs-material`) — used for the architecture pipeline diagram in
particular. No `mkdocstrings`/autodoc: the codebase's docstrings were not
written with autodoc in mind, and curated, hand-written guides communicate
"how this works" better than a raw docstring dump for a code-generator
project like this one.

### 5.3 Navigation / content plan

```
Home                        (docs-site/index.md)
Getting Started
  Installation               (docs-site/getting-started/installation.md)
  Quick start                (docs-site/getting-started/quick-start.md)
ERD Reference
  Schema overview             (docs-site/erd-reference/overview.md)
  Full field reference        (docs-site/erd-reference/fields.md)
Features
  Auth                        (docs-site/features/auth.md)
  RBAC                        (docs-site/features/rbac.md)
  Row-Level Security          (docs-site/features/rls.md)
  Async database support      (docs-site/features/async.md)
Architecture
  Pipeline overview            (docs-site/architecture/pipeline.md)
  Template system              (docs-site/architecture/templates.md)
  Adding a new feature         (docs-site/architecture/extending.md)
CLI Reference                  (docs-site/cli-reference.md)
```

### 5.4 Content sourcing

Rather than writing every page from scratch, content is mined from
existing, already-accurate sources in this repo: the feature design specs
under `docs/superpowers/specs/` (RLS, async-support, auth-expansion each
already have detailed, previously-reviewed-accurate mechanics written
down), the current README's feature sections (before they're trimmed out
of it), and the ERD schema/loader/translate source itself for the field
reference. Every ported claim is checked against the actual current code
or actual rendered output before being written into a docs-site page —
specs written mid-session can drift from what a later fix round changed
(the auth-expansion plan's own final review is a concrete example: it
fixed real behavior after the spec was written), so the spec is a
starting draft for docs content, not a citable source of truth on its own.

### 5.5 Build verification

`mkdocs build --strict` (fails on broken internal links / nav references,
not just warns) run as part of this work's own verification, not left for
a later discovery.

## 6. Testing plan

- Full existing suite (`app/tests/`, 252 tests today) must pass unchanged
  after the `backend.` → `app.` import rewrite — this is a pure rename at
  the test level; no test's assertions change, only the module paths they
  import from.
- The `templates_dir` fix (3.6) needs one direct check: run the CLI (or
  the equivalent test path) from a working directory that is *not* the
  repo root, and confirm generation still finds
  `app/templates/Python/...` correctly — this is the concrete regression
  test that proves the fix is real, not just "the existing suite still
  passes" (which would pass even with the old CWD-relative bug, since
  pytest's CWD happens to already be the repo root in this workflow).
- CLI smoke test: `backstudio generate examples/blog.yml` (or equivalent
  current invocation) against a scratch output directory, confirm the
  generated project still renders and (if quick to check) starts up,
  proving the rename didn't silently break the real end-to-end path outside
  of pytest.
- Repo-wide grep sweep, post-change, for any remaining reference to
  `backend.`, `backend/`, `frontend`, `mcp_server`, or any other deleted
  path/module — across `.py`, `.md`, `.toml`, `.jinja` files — to catch
  anything the file-by-file plan missed.
- `mkdocs build --strict` passes (5.5).

## 7. Non-goals

- No change to generated projects' own output structure, naming, or
  templates' rendered code (this restructure only touches this repo's own
  layout, not what it produces).
- No CI/deployment wiring for the docs site (explicit decision — local
  `mkdocs serve`/`build` only; GitHub Pages or similar can be a later,
  separate step once the content itself exists and is reviewed).
- No `mkdocstrings`/autodoc-generated API reference pages.
- No rewrite of `docs/superpowers/` (this project's own internal
  specs/plans/backlog archive) — it stays exactly as-is and is unrelated
  to this work beyond being a content source for the new docs site.
- No behavior change to any already-shipped feature (auth, RBAC, RLS,
  async) — this is a structural/documentation pass only.
