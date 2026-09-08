<div align="center">
  <img src="./assets/logo.svg" alt="BackStudio Logo" width="200"/>

  # BackStudio

  **Visual Backend Code Generator - Build FastAPI backends through an intuitive UI**

  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
  [![React](https://img.shields.io/badge/React-18.2+-blue.svg)](https://reactjs.org/)
  [![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
</div>

## Overview

BackStudio is a powerful visual backend code generator that lets you design and build production-ready FastAPI backends through an intuitive web interface. Define your data models, services, endpoints, and dependencies visually, then generate clean, deterministic Python code ready for deployment.

### Key Features

- **Visual Design Interface** - Build your backend architecture through an intuitive React-based UI
- **Model-First Approach** - Define database models with relationships, validations, and constraints
- **Service Architecture** - Create modular services with custom business logic
- **Endpoint Designer** - Configure REST API endpoints with proper HTTP methods, parameters, and schemas
- **Dependency Injection** - Set up guards (auth/validation) and providers (data injection) visually
- **Deterministic Code Generation** - Same specs = same code, guaranteed by SHA256 checksums
- **Complete Specification Model**: Define data models, relationships, services, endpoints, middlewares, and dependencies
- **Service-Oriented Architecture**: Generated code provides complete boilerplate - you only write service function bodies
- **State Management**: Project state stored as JSON with checksum validation
- **Template-Based**: Uses Jinja2 templates for flexible, customizable code generation

- **Code Generation** - Generate clean, production-ready FastAPI code with proper structure
- **Multiple Databases** - Support for PostgreSQL, MySQL, SQLite, and MongoDB
- **JWT Authentication** - Built-in JWT auth with customizable token configuration
- **API Documentation** - Auto-generated OpenAPI/Swagger docs
- **MCP Server Support** - Extend functionality through Model Context Protocol

## `backstudio` CLI

Alongside the visual web UI, this repo ships a `backstudio` CLI that generates a FastAPI backend
directly from a single YAML file describing your entities (an "ERD" - entity-relationship
definition) - no server, no clicking through a UI.

### Install

```bash
# uv (recommended)
uv sync

# pip
pip install -e .
```

Either way, this installs a `backstudio` console script (see `[project.scripts]` in
`pyproject.toml`).

### Commands

| Command | What it does | Example |
|---|---|---|
| `validate` | Checks an ERD YAML file for schema and semantic errors (unknown relationship targets, RBAC roles, etc.) without generating anything. | `backstudio validate erd.yml` |
| `visualize` | Renders an HTML entity-relationship diagram (Mermaid) for an ERD file and opens it in a browser. | `backstudio visualize erd.yml -o diagram.html` |
| `generate` | Generates a complete, runnable FastAPI project (models, CRUD routes, auth, RBAC, Alembic migrations) from an ERD file. | `backstudio generate erd.yml --output workspace` |

Run `backstudio --help` or `backstudio <command> --help` for full option lists.

### Example ERD

```yaml
project:
  name: BlogAPI
  version: "1.0.0"

database:
  type: sqlite
  database_name: blog.db

auth:
  enabled: true          # adds /auth/register, /auth/login, /auth/refresh, /auth/me

entities:
  - name: Post
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: title, type: string, max_length: 200}
      - {name: body, type: text}
```

Running `backstudio generate blog.yml` produces a ready-to-run FastAPI project (SQLAlchemy
models, Pydantic schemas, CRUD routes for `Post`, JWT auth routes, and an Alembic migration
setup) under `workspace/BlogAPI/codebase`. When `auth.enabled: true`, the generated `config.py`
requires the JWT secret env var (`JWT_SECRET` above, or whatever `auth.jwt.secret_env_var` names)
to be set - export it (or put it in a `.env` file inside the generated project) before running
the project or its Alembic migrations.

## Architecture

```
BackStudio/
├── backend/           # FastAPI code generation engine
│   ├── api/          # REST API endpoints
│   ├── schemas/      # Pydantic models
│   ├── services/     # Business logic
│   └── templates/    # Jinja2 code templates
├── frontend/         # React UI for visual design
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── services/    # API clients
│   │   └── utils/       # Helper functions
├── mcp_server/       # Model Context Protocol server
├── examples/         # Example projects
└── workspace/        # Generated projects output
```

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11 or higher** - [Download Python](https://www.python.org/downloads/)
- **Node.js 16 or higher** - [Download Node.js](https://nodejs.org/)
- **Package Manager** - Choose one:
  - [uv](https://docs.astral.sh/uv/) (recommended for speed)
  - pip (comes with Python)
  - [Conda/Miniconda](https://docs.conda.io/en/latest/miniconda.html)

### Optional
- **Git** - For version control of generated projects
- **Docker** - For containerizing generated backends

## Quick Start

### Option 1: Automated Setup (Recommended)

#### Linux/macOS
```bash
# Clone the repository
git clone https://github.com/yourusername/BackStudio.git
cd BackStudio

# Run setup script (installs dependencies)
chmod +x setup.sh
./setup.sh

# Start BackStudio
./start.sh
```

#### Windows
```cmd
REM Clone the repository
git clone https://github.com/yourusername/BackStudio.git
cd BackStudio

REM Run setup script
setup.bat

REM Start BackStudio
start.bat
```

### Option 2: Manual Setup

#### 1. Install Backend Dependencies

**Using uv (fastest)**
```bash
cd BackStudio
uv sync
```

**Using pip**
```bash
cd BackStudio
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
```

**Using conda**
```bash
cd BackStudio
conda create -n backstudio python=3.11
conda activate backstudio
pip install -r backend/requirements.txt
```

#### 2. Install Frontend Dependencies
```bash
cd frontend
npm install
```

#### 3. Start the Services

**Terminal 1 - Backend**
```bash
# From project root
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# Or with pip/conda: python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend**
```bash
cd frontend
npm run dev
```

### Access the Application

- **Frontend UI**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc

## Usage Example

### 1. Create a Project

```bash
curl -X POST http://localhost:8000/api/projects/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MyBlogAPI",
    "description": "A blog API with posts and comments",
    "version": "1.0.0",
    "framework": "fastapi"
  }'
```

Response includes project ID and initial checksum.

### 2. Define Data Models

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/models/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Post",
    "table_name": "posts",
    "fields": [
      {"name": "id", "type": "integer", "primary_key": true},
      {"name": "title", "type": "string", "max_length": 200},
      {"name": "content", "type": "text"},
      {"name": "created_at", "type": "datetime"}
    ]
  }'
```

### 3. Define Services

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/services/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PostService",
    "description": "Service for managing blog posts"
  }'
```

### 4. Configure Database

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/config/database/ \
  -H "Content-Type: application/json" \
  -d '{
    "type": "postgresql",
    "host": "localhost",
    "database_name": "myblog",
    "pool_size": 10
  }'
```

### 5. Generate Code

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/generate
```

### 6. Download Generated Code

```bash
curl -X GET http://localhost:8000/api/projects/{project_id}/download \
  --output myblog.zip
```

## API Endpoints

### Project Management

- `GET /api/projects/` - List all projects
- `POST /api/projects/` - Create new project
- `GET /api/projects/{project_id}/` - Get project details
- `PUT /api/projects/{project_id}/` - Update project
- `DELETE /api/projects/{project_id}/` - Delete project

### Code Generation

- `POST /api/projects/{project_id}/generate` - Generate codebase
- `POST /api/projects/{project_id}/sync` - Sync with updated specs
- `GET /api/projects/{project_id}/download` - Download as ZIP
- `GET /api/projects/{project_id}/state` - Get JSON state

### Data Models

- `GET /api/projects/{project_id}/models/` - List models
- `POST /api/projects/{project_id}/models/` - Create model
- `GET /api/projects/{project_id}/models/{model_id}/` - Get model
- `PUT /api/projects/{project_id}/models/{model_id}/` - Update model
- `DELETE /api/projects/{project_id}/models/{model_id}/` - Delete model

### Relationships

- `GET /api/projects/{project_id}/models/{model_id}/relations/` - List relationships
- `POST /api/projects/{project_id}/models/{model_id}/relations/` - Create relationship
- `GET /api/projects/{project_id}/models/{model_id}/relations/{relation_id}/` - Get relationship
- `PUT /api/projects/{project_id}/models/{model_id}/relations/{relation_id}/` - Update relationship
- `DELETE /api/projects/{project_id}/models/{model_id}/relations/{relation_id}/` - Delete relationship

### Services

- `GET /api/projects/{project_id}/services/` - List services
- `POST /api/projects/{project_id}/services/` - Create service
- `GET /api/projects/{project_id}/services/{service_id}/` - Get service
- `PUT /api/projects/{project_id}/services/{service_id}/` - Update service
- `DELETE /api/projects/{project_id}/services/{service_id}/` - Delete service

### Middlewares

- `GET /api/projects/{project_id}/middlewares/` - List middlewares
- `POST /api/projects/{project_id}/middlewares/` - Create middleware

### Dependencies

- `GET /api/projects/{project_id}/dependencies/` - List dependencies
- `POST /api/projects/{project_id}/dependencies/` - Create dependency

### Configuration

- `GET/POST/PUT /api/projects/{project_id}/config/database/` - Database config
- `GET/POST/PUT /api/projects/{project_id}/config/framework/` - Framework config
- `GET/POST/PUT /api/projects/{project_id}/config/security/` - Security config

## Project Structure

```
BackStudio/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py           # All API endpoints
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── project.py          # Project schemas
│   │   ├── data.py             # Data model schemas
│   │   ├── service.py          # Service schemas
│   │   ├── middleware.py       # Middleware schemas
│   │   ├── dependency.py       # Dependency injection schemas
│   │   └── configuration.py    # Configuration schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── project_service.py  # Project state management
│   │   └── code_generator.py   # Code generation logic
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── checksum.py         # Checksum computation
│   │   ├── file_ops.py         # File operations
│   │   └── id_generator.py     # ID generation
│   ├── config/
│   │   ├── __init__.py
│   │   └── config.py           # Application configuration
│   └── main.py                 # FastAPI application entry
├── templates/                  # Jinja2 templates (future)
├── workspace/                  # Generated projects
├── requirements.txt
└── README.md
```

## Supported Frameworks

### FastAPI (Python)
- Complete REST API structure
- SQLAlchemy models with relationships
- Pydantic schemas for validation
- Service layer with async functions
- Configuration via environment variables

### Express.js (Node/JavaScript)
- Express router setup
- Mongoose/Sequelize models
- Middleware configuration
- Service modules

### NestJS (Node/TypeScript)
- Module-based architecture
- TypeORM entities
- DTOs and validation
- Dependency injection
- Guards and interceptors

### Next.js (React/TypeScript)
- API routes
- Server-side rendering setup
- Type definitions
- API client utilities

## Checksum System

Every project has a SHA256 checksum computed from its complete specification. This ensures:

1. **Determinism**: Same specs always produce same code
2. **Verification**: Detect if specs have changed
3. **Reproducibility**: Regenerate exact same codebase anytime

The checksum is computed from the normalized JSON state (excluding the checksum field itself), ensuring consistent results.

## Development Workflow

1. **Define**: Use the API to define your project specifications
2. **Generate**: Run code generation to create boilerplate
3. **Implement**: Write service function bodies (the only code you write!)
4. **Iterate**: Update specs and regenerate as needed
5. **Download**: Get complete, runnable codebase

## Key Concepts

### Data Models
Define database schemas with fields, types, constraints, and relationships (one-to-many, many-to-many, etc.).

### Services
Logical groupings of business logic. Each service contains:
- **Schemas**: DTOs for request/response validation
- **Functions**: Business logic with parameters and return types
- **Endpoints**: HTTP routes that map to service functions

### Middlewares
Cross-cutting concerns like authentication, logging, rate limiting, etc.

### Dependencies
Dependency injection specifications for:
- **Guards**: Decorator-level dependencies (e.g., auth guards)
- **Providers**: Function argument dependencies (e.g., database session)

### Configuration
- **Database**: Connection settings, pool size, etc.
- **Framework**: Language, framework version, async settings
- **Security**: JWT settings, CORS origins, rate limiting

## Future Enhancements

- [ ] More comprehensive Jinja2 templates for each framework
- [ ] Database migration generation
- [ ] API documentation generation (OpenAPI/Swagger)
- [ ] Test generation
- [ ] Docker configuration generation
- [ ] CI/CD pipeline templates
- [ ] Frontend integration templates
- [ ] GraphQL support
- [ ] WebSocket endpoint generation

## Contributing

Contributions are welcome! Areas for contribution:
- Additional framework templates
- Enhanced code generation logic
- More sophisticated relationship handling
- Template improvements
- Documentation

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or suggestions, please open an issue on the project repository.

---

**BackStudio** - Generate once, deploy anywhere. Same specs, same code, guaranteed.
