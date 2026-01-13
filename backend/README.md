<div align="center">
  <img src="../assets/logo.svg" alt="BackStudio Logo" width="150"/>

  # BackStudio Backend

  **FastAPI Code Generation Engine**
</div>

## Overview

The BackStudio backend is a FastAPI-based REST API that handles project state management and code generation. It provides endpoints for defining backend specifications and generates production-ready FastAPI code through Jinja2 templates.

## Features

- **Project Management** - Create, update, and manage backend projects
- **Data Model Designer** - Define database models with fields, constraints, and relationships
- **Service Architecture** - Configure services with business logic functions
- **Endpoint Configuration** - Set up REST API endpoints with HTTP methods and parameters
- **Dependency Injection** - Define guards and providers for authentication and data injection
- **Code Generation** - Generate clean, deterministic FastAPI code from specifications
- **State Persistence** - Store project state as JSON with SHA256 checksum validation
- **Template System** - Flexible Jinja2-based code generation
- **Multiple Databases** - Support for PostgreSQL, MySQL, SQLite, and MongoDB

## Installation

### Prerequisites
- Python 3.11 or higher
- One of: uv, pip, or conda

### Option 1: Using uv (Recommended)
```bash
cd BackStudio
uv sync
```

### Option 2: Using pip
```bash
cd BackStudio
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
```

### Option 3: Using conda
```bash
conda create -n backstudio python=3.11
conda activate backstudio
pip install -r backend/requirements.txt
```

## Running the Server

### Development Mode
```bash
# With uv
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# With pip/conda
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

##Access Points

- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## Project Structure

```
backend/
├── api/
│   └── routes.py              # All REST API endpoints
├── schemas/
│   ├── project.py             # Project schemas
│   ├── data.py                # Data model schemas
│   ├── service.py             # Service & endpoint schemas
│   ├── dependency.py          # Dependency injection schemas
│   └── configuration.py       # Configuration schemas
├── services/
│   ├── project_service.py     # Project state management
│   └── code_generator.py      # Code generation logic
├── templates/
│   └── Python/
│       └── service/           # Jinja2 templates for FastAPI
├── utils/
│   ├── checksum.py            # SHA256 checksum calculation
│   ├── file_ops.py            # File operations
│   └── id_generator.py        # Unique ID generation
├── config/
│   └── config.py              # Application configuration
├── main.py                    # FastAPI application entry
└── requirements.txt           # Python dependencies
```

## API Endpoints

### Project Management
- `POST /api/projects/` - Create new project
- `GET /api/projects/` - List all projects
- `GET /api/projects/{id}/` - Get project details
- `PUT /api/projects/{id}/` - Update project
- `DELETE /api/projects/{id}/` - Delete project

### Data Models
- `POST /api/projects/{id}/models/` - Create model
- `GET /api/projects/{id}/models/` - List models
- `PUT /api/projects/{id}/models/{model_id}/` - Update model
- `DELETE /api/projects/{id}/models/{model_id}/` - Delete model

### Services
- `POST /api/projects/{id}/services/` - Create service
- `GET /api/projects/{id}/services/` - List services
- `PUT /api/projects/{id}/services/{service_id}/` - Update service
- `DELETE /api/projects/{id}/services/{service_id}/` - Delete service

### Endpoints
- `POST /api/projects/{id}/services/{service_id}/endpoints/` - Create endpoint
- `GET /api/projects/{id}/services/{service_id}/endpoints/` - List endpoints
- `PUT /api/projects/{id}/services/{service_id}/endpoints/{endpoint_id}/` - Update endpoint
- `DELETE /api/projects/{id}/services/{service_id}/endpoints/{endpoint_id}/` - Delete endpoint

### Dependencies
- `POST /api/projects/{id}/dependencies/` - Create dependency
- `GET /api/projects/{id}/dependencies/` - List dependencies
- `PUT /api/projects/{id}/dependencies/{dep_id}/` - Update dependency
- `DELETE /api/projects/{id}/dependencies/{dep_id}/` - Delete dependency

### Code Generation
- `POST /api/projects/{id}/generate` - Generate code
- `POST /api/projects/{id}/sync` - Sync with updated specs
- `GET /api/projects/{id}/download` - Download as ZIP

### Configuration
- `GET/POST/PUT /api/projects/{id}/config/database/` - Database config
- `GET/POST/PUT /api/projects/{id}/config/framework/` - Framework config
- `GET/POST/PUT /api/projects/{id}/config/security/` - Security config

## Configuration

### Environment Variables
```bash
# Server
HOST=0.0.0.0
PORT=8000

# Workspace
WORKSPACE_DIR=./workspace

# CORS
CORS_ORIGINS=["http://localhost:5173"]
```

## Code Generation

### Template System

BackStudio uses Jinja2 templates to generate code. Templates are located in `backend/templates/Python/`.

### Generated Project Structure
```
YourProject/
├── server.py                  # FastAPI application
├── dependencies.py            # Guards and providers
├── database/
│   ├── models.py             # SQLAlchemy models
│   └── base.py               # Database connection
├── {service}_service/
│   ├── service.py            # Business logic
│   ├── schemas.py            # Pydantic DTOs
│   └── routes.py             # API endpoints
└── requirements.txt           # Dependencies
```

## Development

### Adding New Templates
1. Create template in `backend/templates/{Language}/{Framework}/`
2. Use Jinja2 syntax for dynamic generation
3. Access project state via template variables

### Custom Validators
Add custom validators in `backend/schemas/` using Pydantic.

### Extending the API
Add new endpoints in `backend/api/routes.py` following the existing pattern.

## Troubleshooting

### Port Already in Use
```bash
lsof -ti:8000 | xargs kill -9
```

### Module Not Found
```bash
# Ensure you're in the project root and PYTHONPATH is set
export PYTHONPATH=/path/to/BackStudio
```

### Database Connection Issues
Check the generated project's database configuration in the workspace.

## License

MIT License - see LICENSE file for details.

---

<div align="center">
  Part of the BackStudio Project
</div>
