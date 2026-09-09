# Async Support — Design Spec

Date: 2026-09-09
Status: Approved for implementation planning
Extends: `docs/superpowers/specs/2026-09-08-erd-cli-design.md`,
`docs/superpowers/specs/2026-09-09-modular-services-design.md`,
`docs/superpowers/specs/2026-09-09-relationship-crud-exposure-design.md`
Precedes: a follow-up spec for row-level access control (RLS), deliberately
designed against the async shape this spec produces — see §7.

## 1. Motivation

Every generated project today uses SQLAlchemy's legacy sync `Session`/`Query`
API end to end: `database/base.py`'s `get_db()`, every `repo.py` function,
every module's `service.py`/`routes.py`, and the auth module's
`register_user`/`authenticate_user`/`get_current_user`. Route handlers are
plain `def` (not `async def`) — correct today, since FastAPI automatically
runs sync route functions in a threadpool, but it means the generated
backend can never do genuine non-blocking DB I/O, and a user who wants to
`await` something else (an external async API call, say) inside their own
custom `service.py` logic can't, without reaching for their own threadpool
tricks.

This spec adds real, whole-stack async support: an async SQLAlchemy engine
and session, a rewritten repo layer on the 2.0-style `select()`/`execute()`
API (the only query API `AsyncSession` supports), and `async def`/`await`
propagated through service methods, route handlers, and the auth module.
Route handlers wrapping an awaited async DB call and calling it
"concurrency" while everything underneath is still sync would be worse than
not building this at all — half-async is not a smaller version of this
feature, it's a different (and pointless) one. Async-shaped signatures with
a sync engine and threadpool dispatch underneath were considered and
rejected for exactly that reason (see the design conversation this spec
comes from) — that gets you nothing over what FastAPI already does
automatically for a plain `def` route today.

## 2. Scope boundary

**In scope:**
- A new opt-in ERD field, `database.async_mode: true` (default `false` —
  every existing ERD/fixture/generated project keeps producing today's sync
  output unchanged). This is a **whole-project** toggle, not per-entity —
  one engine, one session type, one `get_db()` per generated project.
  (Named `async_mode`, not `async` — `async` is a reserved Python keyword
  since 3.7 and can't be used as an attribute name via dot notation, which
  every consumer of this field — the Pydantic schema, `translate.py`,
  every Jinja template — needs to do.)
- `database/base.py.jinja`: async engine (`create_async_engine`),
  `AsyncSession`/`async_sessionmaker`, async `get_db()`, async `init_db()`.
- `database/repo.py.jinja`: every function rewritten onto `select()` +
  `await db.execute(...)` + `.scalar_one_or_none()`/`.scalars().all()`,
  `await db.commit()`/`await db.refresh()`.
- `service/module_service.py.jinja`: every method `async def`, every
  `repo.xxx(...)` call `await`ed.
- `service/module_routes.py.jinja`: every route handler `async def`,
  `db: Session` → `db: AsyncSession`, every `service.xxx(...)` call
  `await`ed.
- `auth/service.py.jinja`: `register_user`/`authenticate_user` become
  `async def` with the same query rewrite as repo.py; `get_current_user`
  (already `async def` today) gets its internal `db.query(User)...` call
  rewritten the same way.
- `alembic/env.py.jinja`: async-aware migration running (§7), gated on the
  same `database.async_mode` flag.
- `requirements.txt.jinja`: the correct async driver per `database.type`,
  only when `database.async_mode: true`.
- `config.py.jinja` / the generated README: the async-driver-qualified
  `DATABASE_URL` scheme (§3), only when async.

**Explicitly out of scope:**
- Row-level access control (RLS) — a separate follow-up spec, deliberately
  sequenced after this one so it's designed directly against the async
  shape rather than built once for sync and reworked for async.
- The legacy per-entity UI-driven flow (`service.py.jinja`/
  `schemas.py.jinja`/`routes.py.jinja` — distinct from the `module_*`
  versions this spec touches) — flagged for deletion in the repo-cleanup
  backlog item; not worth making async.
- `translate.py` and `database/models.py.jinja` — confirmed to need **zero**
  changes. `declarative_base()`/model classes aren't sync-or-async-specific;
  the async-ness lives entirely in the engine/session/query layer above
  them. Every relationship-derivation change from the last two sessions
  (`owned_relationships`, `many_to_many_relationships`, self-referential
  handling) is untouched by this spec.
- Streaming responses, background tasks, or any async pattern beyond
  standard CRUD request/response.
- `rbac/dependency.py.jinja` needs no logic changes — `require_roles`'s
  inner dependency is already `async def` and does no DB access of its own
  (it reads `current_user.roles`, already loaded by `get_current_user`).

## 3. ERD schema and data flow

Add `async_mode: bool = False` to `DatabaseSpec` in `backend/erd/schema.py`.
`translate.py` already passes the whole spec through untouched
(`"database_config": erd.database.model_dump(mode='json')`), so this flows
into every template as `project.database_config.async_mode` with no
`translate.py` changes — `translate.py`'s zero-change status from §2
already accounts for this.

**`DATABASE_URL` scheme.** Async requires the driver named in the URL
scheme, not the bare scheme SQLAlchemy defaults to a sync driver for:

| `database.type` | sync scheme (today) | async scheme |
|---|---|---|
| `sqlite` | `sqlite:///...` | `sqlite+aiosqlite:///...` |
| `postgresql` | `postgresql://...` | `postgresql+asyncpg://...` |
| `mysql` | `mysql://...` (or `mysql+pymysql://...`) | `mysql+aiomysql://...` |

`config.py.jinja`'s default `DATABASE_URL` fallback
(`"sqlite:///./{{ project.name|snake_case }}.db"`) becomes
`"sqlite+aiosqlite:///./{{ project.name|snake_case }}.db"` when
`project.database_config.async_mode` is true. The generated README's
`DATABASE_URL` example (currently built from
`project.database_config.type` directly, giving the bare scheme) needs the
same conditional.

## 4. Database engine/session layer (`database/base.py.jinja`)

```python
{% if project.database_config.async_mode %}
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=settings.DEBUG)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
{% else %}
# ... today's sync engine/SessionLocal/get_db/init_db, unchanged ...
{% endif %}
```

`expire_on_commit=False` on the async sessionmaker is necessary, not
cosmetic: without it, accessing an attribute on a committed object outside
an active `async with` block (e.g. after `await db.refresh(x)` returns) can
trigger SQLAlchemy's implicit-IO-on-attribute-access path, which raises
under `AsyncSession` (no implicit greenlet-free IO is allowed) instead of
transparently re-fetching the way sync `Session` would.

**Async drivers per database type** (added to `requirements.txt.jinja` only
when `database.async_mode: true`):
- `sqlite` → `aiosqlite` (already present in `requirements.txt.jinja`
  unconditionally today — dead weight for the sync path since nothing uses
  it; move it under the `async_mode` conditional as part of this work)
- `postgresql` → `asyncpg` (replaces `psycopg2-binary` for the async
  branch; the sync branch keeps `psycopg2-binary` unchanged)
- `mysql` → `aiomysql` (replaces `pymysql`/`cryptography` for the async
  branch; sync branch unchanged)

## 5. Repo layer rewrite (`database/repo.py.jinja`)

Every function gets a full `{% if project.database_config.async_mode %}...
{% else %}...{% endif %}` pair — no macros (this codebase has never used
Jinja macros; explicit duplicate branches match its existing convention of
favoring readability-in-isolation over cleverness, even at the cost of
roughly doubling this file's line count).

```python
{% if project.database_config.async_mode %}
async def get_{{ model.name|snake_case }}_by_id(db: AsyncSession, {{ model.name|snake_case }}_id: int) -> Optional[{{ model.name|pascal_case }}]:
    """Get {{ model.name }} by ID"""
    stmt = select({{ model.name|pascal_case }})
{% for rel in model.many_to_many_relationships %}
    stmt = stmt.options(selectinload({{ model.name|pascal_case }}.{{ rel.attribute }}))
{% endfor %}
    {% set pk_field = model.fields|selectattr('primary_key')|first %}
    stmt = stmt.where({{ model.name|pascal_case }}.{{ pk_field.name if pk_field else 'id' }} == {{ model.name|snake_case }}_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
{% else %}
def get_{{ model.name|snake_case }}_by_id(db: Session, {{ model.name|snake_case }}_id: int) -> Optional[{{ model.name|pascal_case }}]:
    ... # today's implementation, unchanged
{% endif %}
```

The same transformation pattern applies to `create_<x>` (`db.add()` stays
sync — it only stages the object in the session's identity map, no IO —
but `db.commit()`/`db.refresh()` become `await`ed), `get_all_<plural>`
(`.filter().offset().limit().all()` → `select().where().offset().limit()`
fed through `await db.execute(...)`, unpacked via
`.scalars().all()`), `update_<x>` and `delete_<x>` (both call the
already-async `get_<x>_by_id` internally, so gain `await` at that call
site plus on their own `commit()`/`refresh()`/`delete()`). `selectinload`
for many-to-many relationships (from the relationship-CRUD-exposure work)
carries over unchanged in shape — it's a query-building option, not a
sync/async-specific construct — just gets attached to a `select()` `stmt`
instead of a `Query` object. `db.delete(x)` itself is a synchronous call in
both APIs (only its associated `commit()` is async) — do not add a stray
`await` there.

## 6. Service, routes, auth — mechanical propagation

`module_service.py.jinja`, `module_routes.py.jinja`: same
`{% if project.database_config.async_mode %}` branching, but here it's
mechanical — every function signature gains `async def`, `Session` becomes
`AsyncSession` in type hints, and every call into the layer below gains
`await`. No new query logic at this level (that's confined to §5). The
existing `try/except ValueError → HTTPException(400)` pattern from the
relationship-CRUD-exposure work is untouched in shape, just living inside
an `async def`.

`auth/service.py.jinja`: `register_user`/`authenticate_user` get the same
query-rewrite treatment as repo.py (they run their own `db.query(User)...`
calls directly rather than going through `repo.py`). `get_current_user` is
already declared `async def` in both branches today (a FastAPI-dependency
convention, independent of this spec) — only its internal
`db.query(User).filter(...).first()` needs the `select()`/`execute()`
rewrite when `database.async_mode` is true.

## 7. Alembic migrations (`alembic/env.py.jinja`)

Alembic itself runs synchronously — rather than requiring a second,
sync-only driver installed alongside the async one purely for migrations,
use SQLAlchemy's documented async-Alembic pattern: build the async engine,
and inside `run_migrations_online`, open an async connection and drive the
actual (synchronous, Alembic-internal) migration logic through
`await connection.run_sync(...)`, with the whole online path invoked via
`asyncio.run(...)`. One driver installed either way (the async one),
matching whichever branch `database.async_mode` selects — never both.

```python
{% if project.database_config.async_mode %}
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

asyncio.run(run_migrations_online())
{% else %}
# ... today's sync run_migrations_online, unchanged ...
{% endif %}
```

The offline path (`run_migrations_offline`, used for generating SQL scripts
without a live DB connection) needs no changes in either branch — it never
touches the engine/driver at all.

This must be proven against a **real** `alembic revision --autogenerate`
invocation (§8), not just read — the existing sync equivalent test already
does exactly this, and this pattern has a well-earned reputation for
looking right and failing at the `asyncio.run()`-inside-a-context boundary
in practice.

## 8. Testing plan

- **Regression test**: `database.async_mode` omitted/`false` still renders
  byte-identical output to pre-this-spec templates, for at least one
  existing fixture — the load-bearing guarantee behind calling this
  "opt-in."
- **Generation-level tests**, one fixture per `database.type` ×
  `async_mode: true` (sqlite/postgresql/mysql): correct async imports in
  `base.py`/`repo.py`, correct driver package present (and the *other*
  type's driver absent) in `requirements.txt`, no leftover
  `db.query(...)`/`Query`-API calls anywhere in the async branch's
  rendered output, `py_compile` clean.
- **Real HTTP+DB round-trip test(s)** against `sqlite+aiosqlite` — every
  runtime test in this repo already overrides `DATABASE_URL` to a real
  `tmp_path` SQLite file regardless of the fixture's nominal
  `database.type` (auth secrets aside, nothing in the existing suite talks
  to a real Postgres/MySQL server), so this needs no new test
  infrastructure. Re-run the key existing scenarios — create/list/get/
  update/delete, FK validation returning 400, the many-to-many read-only id
  list, an RBAC-gated route, and auth register/login/me — through an
  `async_mode: true`-generated project, proving routes → service → repo →
  DB compose correctly end to end.
- **A real `alembic revision --autogenerate` invocation** against an
  `async_mode: true`-generated project (mirroring the existing sync-path
  test), to prove §7's `run_sync()` pattern actually runs, not just
  compiles.

## 9. Non-goals / follow-ups

- RLS (next spec, built directly against this one's async shape).
- Async support for the legacy per-entity generation flow (dead once the
  repo-cleanup backlog item removes it).
- Any per-entity or per-relationship async override — this is a
  whole-project decision by design (§2).
