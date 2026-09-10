# Quick start

This page is self-contained — copy each command block in order from a repo you've already
installed (see [Installation](installation.md)) and you'll end up with a running FastAPI
backend generated from a two-field ERD.

## 1. Write the ERD

Save this as `blog.yml` in the repo root:

```yaml
project:
  name: BlogAPI
  version: "1.0.0"

database:
  type: sqlite
  database_name: blog.db

entities:
  - name: Post
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: title, type: string, max_length: 200}

services:
  - name: posting
    entities: [Post]
```

This mirrors the repo's own `examples/blog.yml` in spirit — one entity (`Post`), two fields, one
service grouping it. For a fuller example with a relationship, JWT auth, and RBAC, see
`examples/blog.yml` in the repo.

## 2. Validate it

```bash
$ uv run backstudio validate blog.yml
OK: 1 entities, 0 relationships, auth=off, rbac=off
```

`validate` parses and semantically checks the ERD without writing anything to disk — a fast way
to catch schema mistakes before generating code.

## 3. Generate it

```bash
$ uv run backstudio generate blog.yml --output workspace
Generated at: workspace/BlogAPI/codebase
Copy this directory into your project.
```

`generate` writes a full FastAPI project under `<output>/<project.name>/codebase`. Because
`auth` is off in this ERD, no `.env` secret is generated; because a SQLite database is
declared, `generate` also runs `alembic revision --autogenerate` for you, producing an initial
migration.

### What actually gets produced

Running the command above produces this tree under `workspace/BlogAPI/codebase/`
(captured from a real run; `__pycache__` directories omitted):

```
workspace/BlogAPI/codebase/
├── .gitignore
├── README.md
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── <hash>_initial.py      # e.g. 1d8eaf67161f_initial.py — hash varies per run
├── blog_api.db                    # SQLite DB created by generate's autogenerate step
├── config.py
├── database/
│   ├── __init__.py
│   ├── base.py
│   ├── models.py
│   └── repo.py
├── dependencies.py
├── middleware.py
├── modules/
│   ├── __init__.py
│   └── posting/                   # one module per service in the ERD
│       ├── __init__.py
│       ├── routes.py
│       ├── schemas.py
│       └── service.py
├── requirements.txt
└── server.py
```

## 4. Run the generated project

```bash
cd workspace/BlogAPI/codebase
python -m venv venv
```

Activate the venv, then install and run:

```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn server:app --reload
```

Then visit `http://localhost:8000/docs` for interactive Swagger docs covering the full CRUD API
generated for `Post` (`POST /posts`, `GET /posts`, `GET /posts/{id}`, `PUT /posts/{id}`,
`DELETE /posts/{id}`).

!!! note "Verified"
    Every command on this page — `validate`, `generate`, and booting the generated
    `server:app` with uvicorn — was run end-to-end while writing this page, using the exact
    `blog.yml` content shown above. The generated server started successfully and
    `GET /docs` returned `200` with a valid OpenAPI document listing the `/posts` routes.

## Next steps

- Full flag-by-flag CLI details: [CLI Reference](../cli-reference.md)
- Every field the ERD YAML format supports: [Full field reference](../erd-reference/fields.md)
- Turning on auth, RBAC, row-level security, or async database support: the
  [Authentication](../features/auth.md), [RBAC](../features/rbac.md),
  [Row-Level Security](../features/rls.md), and [Async database support](../features/async.md)
  pages
