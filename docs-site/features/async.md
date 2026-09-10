# Async database support

`database.async_mode: true` is a whole-project, opt-in toggle (default `false` — every existing
ERD keeps producing today's sync output unchanged) that switches the entire generated stack from
SQLAlchemy's legacy sync `Session`/`Query` API to the async engine, `AsyncSession`, and the
2.0-style `select()`/`execute()` API — not a partial or per-entity setting. See the
[Full field reference → `database`](../erd-reference/fields.md#database-databasespec) for the
field's exact type/default; this page covers what turning it on changes in the generated code and
what changes for whoever runs the generated project.

## What changes in generated code

Verified by generating a real fixture
(`app/tests/fixtures/erd/async_minimal.yml`, `database.async_mode: true`) and reading the actual
output, not just the templates:

- **`database/base.py`** — `create_async_engine(settings.DATABASE_URL, ...)`, an
  `async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)`, an `async def
  get_db()` that yields inside `async with AsyncSessionLocal() as session:`, and an `async def
  init_db()` that runs `await conn.run_sync(Base.metadata.create_all)` inside `async with
  engine.begin() as conn:`.

  `expire_on_commit=False` isn't cosmetic: without it, accessing an attribute on a committed
  object outside an active `async with` block (e.g. right after `await db.refresh(x)` returns)
  can trigger SQLAlchemy's implicit-IO-on-attribute-access path, which *raises* under
  `AsyncSession` (no implicit greenlet-free IO is permitted) instead of transparently re-fetching
  the way sync `Session` does.

- **`database/repo.py`** — every function rewritten onto `select()`/`await db.execute(...)` +
  `.scalar_one_or_none()` / `.scalars().all()`, with `await db.commit()`/`await db.refresh()`.
  `db.add()` stays a plain synchronous call in both branches (it only stages the object in the
  session's identity map — no IO), but `await db.delete(x)` **is** required in async mode
  (`AsyncSession.delete()` is a coroutine; calling it without `await` silently no-ops the delete
  — Python only raises a `RuntimeWarning` for an un-awaited coroutine, never an error).

- **`service/module_service.py` and `service/module_routes.py`** — every method/handler becomes
  `async def`, every `Session` type hint becomes `AsyncSession`, every call into the layer below
  gains `await`. No new query logic at this level — purely mechanical propagation.

- **`auth/service.py` and `auth/routes.py`** — `register_user`/`authenticate_user` get the same
  query rewrite as `repo.py` (they run their own queries directly rather than going through
  `repo.py`). `get_current_user` was already `async def` in both branches (a FastAPI-dependency
  convention, independent of async mode) — only its internal user lookup gets rewritten. The
  bootstrap `is_first_user` count becomes
  `(await db.scalar(select(func.count()).select_from(User))) == 0`. `register`/`login`/
  `refresh`/`me` all become `async def`, including `refresh`'s own raw user lookup.

- **`alembic/env.py`** — confirmed in the generated fixture's output:

  ```python
  from sqlalchemy.ext.asyncio import async_engine_from_config
  import asyncio
  ...
  async def run_migrations_online() -> None:
      connectable = async_engine_from_config(...)
      async with connectable.connect() as connection:
          await connection.run_sync(do_run_migrations)
      await connectable.dispose()

  asyncio.run(run_migrations_online())
  ```

  Alembic itself runs synchronously — rather than requiring a second, sync-only driver installed
  purely for migrations, the async engine opens a connection and drives Alembic's actual
  (synchronous, Alembic-internal) migration logic through `await connection.run_sync(...)`, with
  the whole online path invoked via `asyncio.run(...)`. Only one driver is ever installed, never
  both.

- **`server.py`**'s `lifespan` shutdown section calls `await engine.dispose()`. This is a
  correctness requirement, not optional cleanup: the async engine's underlying driver (`aiosqlite`
  in particular keeps a per-connection background thread) does not get cleanly torn down when the
  process's async work finishes on its own — without an explicit dispose, the *process* never
  exits, which would hang an entire test suite at the very end, after every individual test has
  already passed.

## `DATABASE_URL` scheme — confirmed against real generated output

Async mode requires the driver named directly in the URL scheme (SQLAlchemy defaults the bare
scheme to a sync driver). Generating `async_minimal.yml` and reading the actual
`config.py`/`README.md`/`requirements.txt` output confirms:

| `database.type` | sync scheme | async scheme | async driver added to `requirements.txt` |
|---|---|---|---|
| `sqlite` | `sqlite:///...` | `sqlite+aiosqlite:///...` | `aiosqlite` |
| `postgresql` | `postgresql://...` | `postgresql+asyncpg://...` | `asyncpg` (replaces `psycopg2-binary`) |
| `mysql` | `mysql://...` | `mysql+aiomysql://...` | `aiomysql` (replaces `pymysql`) |

The generated fixture's `config.py` default fallback and `README.md`'s example both rendered
exactly as `sqlite+aiosqlite:///./async_minimal.db` / `sqlite+aiosqlite:///./app.db` — the
`postgresql+asyncpg://...` and `mysql+aiomysql://...` forms come from the same conditional in
`README.md.jinja`, verified by reading the template's generation logic directly (both schemes are
built from `project.database_config.type` plus a hardcoded `+asyncpg`/`+aiomysql` driver suffix,
gated on `async_mode`, alongside the equivalent unqualified schemes for the sync branch).

## What changes for someone running the generated project

Nothing beyond installing the async driver (already the right one in `requirements.txt` — no
manual step) and using the async-qualified `DATABASE_URL` from `.env`/the README example above.
Route handlers, service methods, and repo functions are `async def` throughout, so no threadpool
dispatch is happening under the hood the way it silently does for a plain sync `def` FastAPI
route — genuine non-blocking DB I/O, and custom code added to a generated `service.py` can freely
`await` other async work (an external API call, say) without reaching for threadpool tricks.

## Caveats carried over from the design spec

From the async-support spec's own Non-goals/scope boundary (§2, §9), still accurate against the
current templates:

- This is a **whole-project** decision — there is no per-entity or per-relationship async
  override; one engine, one session type, one `get_db()` per generated project.
- Streaming responses and background tasks are out of scope — this covers standard CRUD
  request/response only.
- The legacy per-entity generation flow (distinct from the `module_*` templates this feature
  touches) was never made async, and is flagged for eventual removal rather than being extended.
