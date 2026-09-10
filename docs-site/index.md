# BackStudio

**Generate a production-ready FastAPI backend from a YAML file describing your data model.**

## What it is

BackStudio's `backstudio` CLI reads a single YAML file describing your entities (an "ERD" —
entity-relationship definition) and generates a complete, runnable FastAPI backend: SQLAlchemy
models, a full CRUD REST API per entity, optional JWT authentication, role-based access control
(RBAC), row-level security, and Alembic migration scaffolding. No server to run, no UI to click
through — write a YAML file, run one command, get a codebase. Generation is also deterministic:
the same ERD always produces the same generated code.

## Why ERD-driven

Most backend scaffolding tools either generate code once and leave you to diverge from it, or
wrap your data model in a framework you have to keep feeding forever. BackStudio takes a
different shape: the ERD YAML file is the single source of truth for your data model, and the
generated backend is plain, readable FastAPI/SQLAlchemy code you own outright — no runtime
dependency on BackStudio itself, no generated-code "magic" to reverse-engineer. Because
generation is deterministic, the same ERD always reproduces the same codebase, so the YAML file
also doubles as living documentation of your API: read it once and you know every entity, every
field, every relationship, and every access rule the generated backend enforces.

## Next step

Ready to try it? Start with **[Getting Started → Installation](getting-started/installation.md)**,
then walk through the **[Quick start](getting-started/quick-start.md)** to generate and run your
first backend in a few minutes.
