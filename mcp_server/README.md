<div align="center">
  <img src="../assets/logo.svg" alt="BackStudio Logo" width="200"/>

  # BackStudio MCP Server

  **Model Context Protocol Server for BackStudio - Build FastAPI backends through AI assistants**
</div>

## Overview

The BackStudio MCP Server is a [Model Context Protocol](https://modelcontextprotocol.io) server that enables AI assistants (like Claude Desktop, Cline, and other MCP clients) to interact with BackStudio programmatically. Using natural language, you can design complete FastAPI backends by creating projects, defining data models, services, endpoints, and dependencies—all through your AI assistant.

## Features

- **30+ MCP Tools** - Complete API coverage for all BackStudio functionality
- **Natural Language Interface** - Build backends by describing what you want
- **Full CRUD Operations** - Create, read, update, and delete all project components
- **Code Generation** - Generate complete FastAPI applications from specifications
- **Dependency Injection** - Define guards (authorization) and providers (value injection)
- **Relationship Management** - Create one-to-many, many-to-many relationships between models
- **Project State Management** - View and download complete project specifications

## Installation

### Prerequisites

- Python 3.11+
- BackStudio API running on `http://localhost:8000` (see main README.md)
- An MCP-compatible client (Claude Desktop, Cline, etc.)

### Option 1: Using pip

```bash
cd mcp_server
pip install -e .
```

### Option 2: Using uv (Recommended)

```bash
cd mcp_server
uv pip install -e .
```

## Configuration

### Claude Desktop

Add the following to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "backstudio": {
      "command": "python",
      "args": [
        "-m",
        "backstudio_mcp.server"
      ],
      "env": {
        "BACKSTUDIO_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

### Other MCP Clients

The server uses stdio transport. Configure your client to run:

```bash
python -m backstudio_mcp.server
```

Set environment variable `BACKSTUDIO_API_URL` if your BackStudio API is not at `http://localhost:8000`.

## Available Tools

### Project Management (5 tools)

| Tool | Description |
|------|-------------|
| `create_project` | Create a new BackStudio project |
| `list_projects` | List all projects |
| `get_project` | Get detailed information about a project |
| `update_project` | Update project metadata |
| `delete_project` | Delete a project and all its components |

### Data Models (6 tools)

| Tool | Description |
|------|-------------|
| `create_data_model` | Create a database model with fields and constraints |
| `list_data_models` | List all models in a project |
| `get_data_model` | Get detailed information about a model |
| `update_data_model` | Update an existing model |
| `delete_data_model` | Delete a model |
| `create_relationship` | Create relationships between models (one-to-many, many-to-many, etc.) |

### Services (9 tools)

| Tool | Description |
|------|-------------|
| `create_service` | Create a service layer for business logic |
| `list_services` | List all services in a project |
| `get_service` | Get detailed information about a service |
| `update_service` | Update an existing service |
| `delete_service` | Delete a service |
| `create_service_schema` | Create DTOs for request/response validation |
| `list_service_schemas` | List all schemas for a service |
| `create_service_function` | Create service methods/functions |
| `list_service_functions` | List all functions for a service |

### Endpoints (4 tools)

| Tool | Description |
|------|-------------|
| `create_endpoint` | Create API endpoints with paths, methods, parameters |
| `list_endpoints` | List all endpoints for a service |
| `get_endpoint` | Get detailed information about an endpoint |
| `update_endpoint` | Update an existing endpoint |
| `delete_endpoint` | Delete an endpoint |

### Dependencies (5 tools)

| Tool | Description |
|------|-------------|
| `create_dependency` | Create guards (authorization) or providers (value injection) |
| `list_dependencies` | List all dependencies in a project |
| `get_dependency` | Get detailed information about a dependency |
| `update_dependency` | Update an existing dependency |
| `delete_dependency` | Delete a dependency |

### Code Generation (4 tools)

| Tool | Description |
|------|-------------|
| `generate_code` | Generate complete FastAPI codebase from specification |
| `sync_project` | Sync generated code with current project state |
| `get_project_state` | Get complete project specification as JSON |
| `get_generated_code_path` | Get file system path to generated code |
| `download_project` | Download generated code as ZIP file |

## Usage Examples

### Example 1: Simple User API

```
You: "Create a user management API with CRUD endpoints"

Claude will use MCP tools to:
1. create_project - Create new project
2. create_data_model - Define User model with email, username, password fields
3. create_service - Create UserService
4. create_service_schema - Create UserCreate and UserResponse DTOs
5. create_service_function - Create get_user, create_user, update_user functions
6. create_endpoint - Create GET/POST/PUT/DELETE endpoints
7. generate_code - Generate the complete FastAPI application
```

### Example 2: Blog API with Authentication

```
You: "Create a blog API where authenticated users can create posts"

Claude will:
1. Create User and Post models
2. Create relationship between User and Post (one-to-many)
3. Create get_current_user provider dependency
4. Create AuthService and PostService
5. Create endpoints with provider injection for authentication
6. Generate complete code with JWT authentication
```

### Example 3: E-commerce API

```
You: "Build an e-commerce API with products, categories, orders, and admin-only product management"

Claude will:
1. Create Product, Category, Order, OrderItem, User models
2. Create relationships (Category→Products, User→Orders, Order→OrderItems)
3. Create require_admin guard dependency
4. Create get_current_user provider dependency
5. Create services for each domain
6. Create public and protected endpoints
7. Generate complete FastAPI application
```

## Key Concepts

### Guards vs Providers

**Guards**: Dependencies that validate/authorize requests and throw exceptions to block access
- Example: `verify_admin`, `check_permissions`, `rate_limit`
- Applied at the decorator/middleware level
- Block request execution if validation fails

**Providers**: Dependencies that inject values into endpoint functions
- Example: `get_current_user`, `get_db_session`, `get_config`
- Create variables you can use in your endpoint logic
- Must specify `variable_name` when adding to endpoint

### Workflow

1. **Define**: Use MCP tools to define project specifications (models, services, endpoints)
2. **Generate**: Call `generate_code` to create the FastAPI boilerplate
3. **Implement**: Write business logic in service function bodies (only code you write!)
4. **Iterate**: Update specs and use `sync_project` to regenerate
5. **Deploy**: Download and deploy your FastAPI application

## Architecture

```
backstudio_mcp/
├── __init__.py
├── server.py          # MCP server with 30+ tools
├── client.py          # BackStudio API client
└── __main__.py        # Entry point for running server
```

The MCP server communicates with the BackStudio API at `http://localhost:8000` to manage projects and generate code.

## Detailed Examples

See [EXAMPLES.md](EXAMPLES.md) for comprehensive examples including:
- Simple user management API
- Blog API with authentication and relationships
- E-commerce API with complex relationships and role-based access control
- Common patterns and best practices

## Troubleshooting

### Connection Issues

**Problem**: MCP client can't connect to server
**Solution**: Ensure BackStudio API is running on `http://localhost:8000`

```bash
# Start BackStudio API
cd BackStudio
./start.sh
```

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'backstudio_mcp'`
**Solution**: Install the package in editable mode

```bash
cd mcp_server
pip install -e .
```

### API Errors

**Problem**: Tools return 404 or connection errors
**Solution**: Check `BACKSTUDIO_API_URL` environment variable and ensure API is accessible

```bash
curl http://localhost:8000/api/projects/
```

## Development

### Running the Server Standalone

```bash
cd mcp_server
python -m backstudio_mcp.server
```

### Testing with MCP Inspector

```bash
npm install -g @modelcontextprotocol/inspector
mcp-inspector python -m backstudio_mcp.server
```

## Resources

- [Model Context Protocol Specification](https://modelcontextprotocol.io)
- [BackStudio Main Documentation](../README.md)
- [Claude Desktop MCP Guide](https://docs.anthropic.com/claude/docs/model-context-protocol)
- [MCP Examples](EXAMPLES.md)

## Contributing

Contributions are welcome! Areas for enhancement:
- Additional MCP tools for configuration management
- Middleware and database configuration tools
- Code template customization
- Enhanced error handling and validation

## License

MIT License - see LICENSE file for details

---

**Build FastAPI backends through natural language with BackStudio MCP Server** 🚀
