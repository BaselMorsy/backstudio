# Template system

Every file in a generated project comes from a Jinja2 template under `app/templates/Python/`,
rendered by `CodeGenerator` (`app/services/code_generator.py`) — see
[Pipeline overview](pipeline.md) for how the `state` dict each template renders against gets
built. This page covers where templates live, how the Jinja2 environment is configured, the two
context shapes a template can receive, and the two live per-service generation paths.

## Where templates live

All templates live under `app/templates/Python/` (the `CodeGenerator.__init__` default,
`_DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"`, i.e.
`app/templates/`; only `Python/` exists today — `framework` is checked against `'fastapi'` and
no other value is supported). The current tree:

```
app/templates/Python/
├── README.md.jinja
├── config.py.jinja
├── dependencies.py.jinja
├── gitignore.jinja
├── middleware.py.jinja
├── requirements.txt.jinja
├── server.py.jinja
├── alembic/
│   ├── alembic.ini.jinja
│   ├── env.py.jinja
│   └── script.py.mako.jinja   # copied verbatim, never rendered through Jinja2
├── auth/
│   ├── email.py.jinja
│   ├── routes.py.jinja
│   ├── schemas.py.jinja
│   └── service.py.jinja
├── database/
│   ├── base.py.jinja
│   ├── models.py.jinja
│   └── repo.py.jinja
├── rbac/
│   └── dependency.py.jinja
└── service/
    ├── module_routes.py.jinja
    ├── module_schemas.py.jinja
    └── module_service.py.jinja
```

## The Jinja2 environment

`CodeGenerator.__init__` constructs the environment exactly once, per `CodeGenerator` instance:

```python
self.jinja_env = Environment(
    loader=FileSystemLoader(str(self.templates_dir)),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True
)
```

`autoescape` is scoped to `html`/`xml` extensions only — every generated file here is `.py`,
`.ini`, `.txt`, `.md`, or extension-less (`.gitignore`), so autoescaping never actually engages;
it's a defensive default, not something the Python-code templates depend on. `trim_blocks=True`
and `lstrip_blocks=True` are what keep the generated Python's indentation and blank lines clean
despite Jinja control tags (`{% if %}`, `{% for %}`, …) living on their own source lines in the
`.jinja` files — without them, every `{% %}` line would leave a stray blank line or leading
whitespace in the rendered `.py` file. `keep_trailing_newline=True` preserves the template's own
trailing newline instead of Jinja's default of stripping it (so generated files reliably end
with exactly one newline, not zero).

`_register_filters()` (called from `__init__`) adds custom filters — `snake_case`,
`pascal_case`, `camel_case`, `kebab_case`, `python_value` — and two globals,
`get_sqlalchemy_type` and `get_python_type` (both used by `database/models.py.jinja` and friends
to map an ERD `FieldType` to a SQLAlchemy column type / Python type annotation). The
`snake_case` filter's implementation is a byte-for-byte duplicate of `_snake_case()` in
`app/erd/translate.py` — a comment at both call sites flags that the two must stay identical,
since generated code mixes names computed by `translate.py` (e.g. `repo.get_<target_snake>_by_id`
calls baked into `crud_entities`/relationship dicts) with names the `snake_case` filter computes
live inside a template; drift between the two would generate a call to a repo function that
doesn't exist.

## The two context shapes

`_generate_fastapi_project()` renders every template with one of exactly two context shapes —
verified against its actual `_render_template(...)` call sites:

**`{'project': state}`** — the whole `state` dict under the `project` key, nothing else. Used
for every template that isn't specific to one module:

| Template | Rendered when |
|---|---|
| `database/base.py.jinja` | always |
| `database/models.py.jinja` | always |
| `database/repo.py.jinja` | always |
| `auth/schemas.py.jinja` | `state['auth_enabled']` |
| `auth/service.py.jinja` | `state['auth_enabled']` |
| `auth/routes.py.jinja` | `state['auth_enabled']` |
| `auth/email.py.jinja` | `state['auth_enabled']` |
| `rbac/dependency.py.jinja` | `state['rbac_enabled']` |
| `alembic/alembic.ini.jinja` | always |
| `alembic/env.py.jinja` | always |
| `config.py.jinja` | always |
| `server.py.jinja` | always |
| `middleware.py.jinja` | always |
| `dependencies.py.jinja` | always |
| `requirements.txt.jinja` | always |
| `README.md.jinja` | always |
| `gitignore.jinja` | always |

(`alembic/script.py.mako.jinja` is read and copied with `Path.read_text()` / `_write_file()` —
never passed through `self.jinja_env` at all, so it has no context shape.)

**`{'project': state, 'module': module}`** — the whole `state` dict *plus* one entry of
`state['modules']` under the `module` key. Used only for the three per-module templates, each
rendered once per entry in `state['modules']`, inside `modules/{module['snake_name']}/`:

| Template | Rendered for |
|---|---|
| `service/module_schemas.py.jinja` | each entry in `state['modules']` |
| `service/module_service.py.jinja` | each entry in `state['modules']` |
| `service/module_routes.py.jinja` | each entry in `state['modules']` |

Getting this distinction backwards is the concrete failure mode: a template written expecting
`module` (e.g. one iterating `module.entities` to emit CRUD routes for exactly one service) will
raise `jinja2.exceptions.UndefinedError` on `module` if it's ever wired to the `{'project':
state}` call path instead — or, worse, a template that *should* be module-scoped but gets the
whole-project context instead will silently emit routes/schemas for every entity in the project
into every module's file, rather than just that module's own entities. This is why the auth
templates (below) deliberately do **not** use the per-module context shape even though they also
render into a `modules/{name}/` directory — the auth "module" isn't an entry in
`state['modules']` at all, so there is no `module` dict to pass it.

## `modules`-loop vs. `auth`-module generation

Two separate, real, currently-active code paths generate per-service directories under
`modules/`. An earlier task in this plan removed a third, dead `services`-loop that used to
exist alongside these two (generating from a `state['services']`-shaped list that no longer
exists) — that code is gone from `app/services/code_generator.py` and is **not** documented
here or anywhere else in this site.

**1. The `modules`-loop** — for every entry in `state['modules']` (built by `translate.py`'s
`_resolve_modules()`, which excludes the auth `User`-only service entirely):

```python
for module in state.get('modules', []):
    module_dir = output_dir / "modules" / module['snake_name']
    ...
    module_context = {'project': state, 'module': module}
    self._write_file(module_dir / "schemas.py",
                      self._render_template("Python/service/module_schemas.py.jinja", module_context))
    self._write_file(module_dir / "service.py",
                      self._render_template("Python/service/module_service.py.jinja", module_context))
    self._write_file(module_dir / "routes.py",
                      self._render_template("Python/service/module_routes.py.jinja", module_context))
```

This is the CRUD generation path: one `schemas.py`/`service.py`/`routes.py` triple per
ERD-declared `services:` entry (other than the auth one), built from the `service/*.jinja`
templates with the per-module context.

**2. The `auth`-module generation** — gated on `state['auth_enabled']`, independent of the
`modules` loop entirely:

```python
if state.get('auth_enabled'):
    ...
    auth_dir = output_dir / "modules" / state.get('auth_module_name', 'auth')
    ...
    self._write_file(auth_dir / "schemas.py", self._render_template("Python/auth/schemas.py.jinja", context))
    self._write_file(auth_dir / "service.py", self._render_template("Python/auth/service.py.jinja", context))
    self._write_file(auth_dir / "routes.py", self._render_template("Python/auth/routes.py.jinja", context))
    self._write_file(auth_dir / "email.py", self._render_template("Python/auth/email.py.jinja", context))
```

This writes into `modules/{auth_module_name}/` too (so, from the filesystem's point of view, it
looks like just another module directory), but it uses the dedicated `auth/*.jinja` templates —
not `service/module_*.jinja` — and the whole-project `context`, not `module_context`, since
there is no `state['modules']` entry representing auth to pass in. The two paths are
independent: an ERD with `auth.enabled: true` but zero non-auth `services:` entries generates
only `modules/{auth_module_name}/`; an ERD with several `services:` entries but
`auth.enabled: false` generates only the `modules`-loop's directories and skips auth entirely.

**Route mounting has no implicit service-name prefix.** `server.py.jinja` includes each
CRUD module's router with `app.include_router({{ module.snake_name }}_router)` — no `prefix=`
argument at all — so with no `prefix` set on a service and no `base_path` set on an entity,
that entity's routes are mounted directly at the API root (`/{plural-of-entity-name}`), not
under `/{service-name}` or any other implicit namespace. The **only** router that gets an
automatic prefix is the auth module's, via `app.include_router(auth_router, prefix="/{{
project.auth_module_name }}", ...)`, which defaults to `/auth` (`_resolve_auth_module_name()`
in `translate.py`). To opt a whole service's entities into a shared URL namespace, set that
service's `prefix` in the ERD — see [`services[].prefix`](../erd-reference/fields.md#services-listservicedecl)
for the full field details, including how an entity's own `endpoints.base_path` always wins
outright over the service `prefix` rather than being combined with it.
