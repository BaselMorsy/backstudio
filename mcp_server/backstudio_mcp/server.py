"""BackStudio MCP Server - Main server implementation."""

import os
import json
from typing import Any, Sequence
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import BackStudioClient


# Initialize server and client
server = Server("backstudio-mcp")
client = BackStudioClient()


# ==================== Tool Definitions ====================

TOOLS: list[Tool] = [
    # Project Management
    Tool(
        name="create_project",
        description="Create a new BackStudio project for generating a FastAPI backend",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Project name (will be used as directory name)"
                },
                "description": {
                    "type": "string",
                    "description": "Project description"
                },
                "framework": {
                    "type": "string",
                    "enum": ["fastapi", "flask", "django"],
                    "default": "fastapi",
                    "description": "Backend framework to use"
                }
            },
            "required": ["name"]
        }
    ),
    Tool(
        name="list_projects",
        description="List all BackStudio projects",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    Tool(
        name="get_project",
        description="Get detailed information about a project including all models, services, and endpoints",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID"
                }
            },
            "required": ["project_id"]
        }
    ),
    Tool(
        name="delete_project",
        description="Delete a project and all its associated data",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID to delete"
                }
            },
            "required": ["project_id"]
        }
    ),

    # Data Models
    Tool(
        name="create_data_model",
        description="Create a data model (database entity/table) with fields, indexes, and constraints",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID"
                },
                "name": {
                    "type": "string",
                    "description": "Model name (e.g., 'User', 'Product')"
                },
                "description": {
                    "type": "string",
                    "description": "Model description"
                },
                "fields": {
                    "type": "array",
                    "description": "List of model fields",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "description": "Python/SQL type: str, int, float, bool, datetime, etc."
                            },
                            "nullable": {"type": "boolean", "default": False},
                            "unique": {"type": "boolean", "default": False},
                            "index": {"type": "boolean", "default": False},
                            "default": {"description": "Default value"},
                            "description": {"type": "string"}
                        },
                        "required": ["name", "type"]
                    }
                }
            },
            "required": ["project_id", "name", "fields"]
        }
    ),
    Tool(
        name="list_data_models",
        description="List all data models in a project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID"
                }
            },
            "required": ["project_id"]
        }
    ),
    Tool(
        name="update_data_model",
        description="Update an existing data model",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "model_id": {"type": "string"},
                "name": {"type": "string", "description": "New model name"},
                "description": {"type": "string", "description": "New description"},
                "fields": {
                    "type": "array",
                    "description": "Updated list of model fields",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "nullable": {"type": "boolean", "default": False},
                            "unique": {"type": "boolean", "default": False},
                            "index": {"type": "boolean", "default": False},
                            "default": {"description": "Default value"},
                            "description": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["project_id", "model_id"]
        }
    ),
    Tool(
        name="get_data_model",
        description="Get detailed information about a specific data model",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "model_id": {"type": "string"}
            },
            "required": ["project_id", "model_id"]
        }
    ),
    Tool(
        name="delete_data_model",
        description="Delete a data model from the project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "model_id": {"type": "string"}
            },
            "required": ["project_id", "model_id"]
        }
    ),
    Tool(
        name="create_relationship",
        description="Create a relationship between two data models (one-to-many, many-to-many, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "source_model_id": {
                    "type": "string",
                    "description": "Source model ID"
                },
                "target_model_name": {
                    "type": "string",
                    "description": "Target model name"
                },
                "type": {
                    "type": "string",
                    "enum": ["one_to_many", "many_to_one", "many_to_many", "one_to_one"],
                    "description": "Relationship type"
                },
                "foreign_key": {
                    "type": "string",
                    "description": "Foreign key field name (optional)"
                }
            },
            "required": ["project_id", "source_model_id", "target_model_name", "type"]
        }
    ),

    # Services
    Tool(
        name="create_service",
        description="Create a service layer containing business logic and database operations",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "name": {
                    "type": "string",
                    "description": "Service name (e.g., 'UserService', 'AuthService')"
                },
                "description": {"type": "string"},
                "is_singleton": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether service should be a singleton"
                }
            },
            "required": ["project_id", "name"]
        }
    ),
    Tool(
        name="list_services",
        description="List all services in a project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"}
            },
            "required": ["project_id"]
        }
    ),
    Tool(
        name="get_service",
        description="Get detailed information about a specific service",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"}
            },
            "required": ["project_id", "service_id"]
        }
    ),
    Tool(
        name="update_service",
        description="Update an existing service",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "is_singleton": {"type": "boolean"}
            },
            "required": ["project_id", "service_id"]
        }
    ),
    Tool(
        name="delete_service",
        description="Delete a service from the project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"}
            },
            "required": ["project_id", "service_id"]
        }
    ),
    Tool(
        name="list_service_schemas",
        description="List all schemas (DTOs) for a service",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"}
            },
            "required": ["project_id", "service_id"]
        }
    ),
    Tool(
        name="create_service_schema",
        description="Create a DTO (Data Transfer Object) schema for request/response validation",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"},
                "name": {
                    "type": "string",
                    "description": "Schema name (e.g., 'UserCreateRequest', 'UserResponse')"
                },
                "description": {"type": "string"},
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "required": {"type": "boolean", "default": True},
                            "description": {"type": "string"}
                        },
                        "required": ["name", "type"]
                    }
                }
            },
            "required": ["project_id", "service_id", "name", "fields"]
        }
    ),
    Tool(
        name="list_service_functions",
        description="List all functions for a service",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"}
            },
            "required": ["project_id", "service_id"]
        }
    ),
    Tool(
        name="create_service_function",
        description="Create a service method/function that implements business logic",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"},
                "name": {
                    "type": "string",
                    "description": "Function name (e.g., 'get_user_by_id', 'create_user')"
                },
                "description": {"type": "string"},
                "parameters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "required": {"type": "boolean", "default": True}
                        }
                    }
                },
                "return_type": {
                    "type": "string",
                    "description": "Return type (e.g., 'User', 'List[User]', 'None')"
                },
                "is_async": {
                    "type": "boolean",
                    "default": True
                }
            },
            "required": ["project_id", "service_id", "name"]
        }
    ),

    # Endpoints
    Tool(
        name="create_endpoint",
        description="Create an API endpoint with path, method, parameters, and dependencies",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"},
                "path": {
                    "type": "string",
                    "description": "API path (e.g., '/users', '/users/{user_id}')"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "description": "HTTP method"
                },
                "function_name": {
                    "type": "string",
                    "description": "Service function to call"
                },
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "API tags for grouping in docs"
                },
                "parameters": {
                    "type": "array",
                    "description": "Endpoint parameters (path, query, body)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "location": {
                                "type": "string",
                                "enum": ["path", "query", "body", "header"]
                            },
                            "type": {"type": "string"},
                            "required": {"type": "boolean", "default": False},
                            "description": {"type": "string"}
                        }
                    }
                },
                "request_schema": {
                    "type": "string",
                    "description": "Request body schema name"
                },
                "response_schema": {
                    "type": "string",
                    "description": "Response schema name"
                },
                "status_code": {
                    "type": "integer",
                    "default": 200
                },
                "middlewares": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Guard dependency IDs to apply"
                },
                "providers": {
                    "type": "array",
                    "description": "Provider dependencies with variable names",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dependency_id": {
                                "type": "string",
                                "description": "Provider dependency ID"
                            },
                            "variable_name": {
                                "type": "string",
                                "description": "Variable name to use in endpoint (e.g., 'current_user')"
                            }
                        },
                        "required": ["dependency_id", "variable_name"]
                    }
                }
            },
            "required": ["project_id", "service_id", "path", "method", "function_name"]
        }
    ),
    Tool(
        name="list_endpoints",
        description="List all endpoints for a service",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"}
            },
            "required": ["project_id", "service_id"]
        }
    ),
    Tool(
        name="get_endpoint",
        description="Get detailed information about a specific endpoint",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"},
                "endpoint_id": {"type": "string"}
            },
            "required": ["project_id", "service_id", "endpoint_id"]
        }
    ),
    Tool(
        name="update_endpoint",
        description="Update an existing endpoint",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"},
                "endpoint_id": {"type": "string"},
                "path": {"type": "string"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]
                },
                "function_name": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "parameters": {"type": "array"},
                "request_schema": {"type": "string"},
                "response_schema": {"type": "string"},
                "status_code": {"type": "integer"},
                "middlewares": {"type": "array", "items": {"type": "string"}},
                "providers": {"type": "array"}
            },
            "required": ["project_id", "service_id", "endpoint_id"]
        }
    ),
    Tool(
        name="delete_endpoint",
        description="Delete an endpoint from the service",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"},
                "endpoint_id": {"type": "string"}
            },
            "required": ["project_id", "service_id", "endpoint_id"]
        }
    ),

    # Dependencies
    Tool(
        name="create_dependency",
        description="Create a dependency (guard for authorization/validation, or provider for injecting values)",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["guard", "provider"],
                    "description": "guard: validates/authorizes, provider: injects values"
                },
                "name": {
                    "type": "string",
                    "description": "Dependency function name (e.g., 'verify_token', 'get_current_user')"
                },
                "description": {"type": "string"},
                "parameters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "default": {"description": "Default value"}
                        }
                    }
                },
                "return_type": {
                    "type": "string",
                    "description": "Return type (for providers, e.g., 'User', 'dict')"
                },
                "raises_exception": {
                    "type": "boolean",
                    "description": "Whether this dependency raises exceptions (for guards)"
                },
                "code": {
                    "type": "string",
                    "description": "Python code implementation (optional, will be generated if not provided)"
                }
            },
            "required": ["project_id", "type", "name"]
        }
    ),
    Tool(
        name="list_dependencies",
        description="List all dependencies (guards and providers) in a project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"}
            },
            "required": ["project_id"]
        }
    ),
    Tool(
        name="get_dependency",
        description="Get detailed information about a specific dependency",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "dependency_id": {"type": "string"}
            },
            "required": ["project_id", "dependency_id"]
        }
    ),
    Tool(
        name="update_dependency",
        description="Update an existing dependency",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "dependency_id": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["guard", "provider"]
                },
                "name": {"type": "string"},
                "description": {"type": "string"},
                "parameters": {"type": "array"},
                "return_type": {"type": "string"},
                "raises_exception": {"type": "boolean"},
                "code": {"type": "string"}
            },
            "required": ["project_id", "dependency_id"]
        }
    ),
    Tool(
        name="delete_dependency",
        description="Delete a dependency from the project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "dependency_id": {"type": "string"}
            },
            "required": ["project_id", "dependency_id"]
        }
    ),

    # Code Generation
    Tool(
        name="generate_code",
        description="Generate the complete FastAPI codebase from the project specification",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force regeneration even if code exists"
                }
            },
            "required": ["project_id"]
        }
    ),
    Tool(
        name="sync_project",
        description="Sync generated code with current project state (regenerate changed files)",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"}
            },
            "required": ["project_id"]
        }
    ),
    Tool(
        name="get_project_state",
        description="Get the complete project state as JSON (useful for debugging or reviewing configuration)",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"}
            },
            "required": ["project_id"]
        }
    ),
    Tool(
        name="get_generated_code_path",
        description="Get the file system path where the generated code is located on the server",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"}
            },
            "required": ["project_id"]
        }
    ),
    Tool(
        name="download_project",
        description="Download the generated code as a ZIP file to the local Downloads folder",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "destination": {
                    "type": "string",
                    "description": "Local path to save the ZIP file (optional, defaults to Downloads folder)",
                    "default": None
                }
            },
            "required": ["project_id"]
        }
    ),
]


# ==================== Tool Handlers ====================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls."""

    try:
        # Project Management
        if name == "create_project":
            result = await client.create_project(arguments)
            return [TextContent(
                type="text",
                text=f"✅ Project created successfully!\n\n"
                     f"Project ID: {result['id']}\n"
                     f"Name: {result['name']}\n"
                     f"Framework: {result.get('framework', 'fastapi')}\n\n"
                     f"Next steps:\n"
                     f"1. Create data models with create_data_model\n"
                     f"2. Create services with create_service\n"
                     f"3. Create endpoints with create_endpoint\n"
                     f"4. Generate code with generate_code"
            )]

        elif name == "list_projects":
            projects = await client.list_projects()
            if not projects:
                return [TextContent(type="text", text="No projects found. Create one with create_project.")]

            text = f"📦 Found {len(projects)} project(s):\n\n"
            for p in projects:
                text += f"• {p['name']} (ID: {p['id']})\n"
                if p.get('description'):
                    text += f"  {p['description']}\n"
            return [TextContent(type="text", text=text)]

        elif name == "get_project":
            project = await client.get_project(arguments["project_id"])
            return [TextContent(
                type="text",
                text=f"📋 Project Details:\n\n{json.dumps(project, indent=2)}"
            )]

        elif name == "delete_project":
            await client.delete_project(arguments["project_id"])
            return [TextContent(
                type="text",
                text=f"🗑️  Project {arguments['project_id']} deleted successfully"
            )]

        # Data Models
        elif name == "create_data_model":
            result = await client.create_data_model(
                arguments["project_id"],
                {k: v for k, v in arguments.items() if k != "project_id"}
            )
            return [TextContent(
                type="text",
                text=f"✅ Data model '{result['name']}' created!\n\n"
                     f"Model ID: {result['id']}\n"
                     f"Fields: {len(result.get('fields', []))}\n\n"
                     f"You can now:\n"
                     f"- Add relationships with create_relationship\n"
                     f"- Create a service to work with this model"
            )]

        elif name == "list_data_models":
            models = await client.list_data_models(arguments["project_id"])
            if not models:
                return [TextContent(type="text", text="No data models found. Create one with create_data_model.")]

            text = f"🗄️  Found {len(models)} data model(s):\n\n"
            for m in models:
                text += f"• {m['name']} (ID: {m['id']})\n"
                text += f"  Fields: {', '.join([f['name'] for f in m.get('fields', [])])}\n"
            return [TextContent(type="text", text=text)]

        elif name == "get_data_model":
            model = await client.get_data_model(arguments["project_id"], arguments["model_id"])
            return [TextContent(
                type="text",
                text=f"📋 Data Model: {model['name']}\n\n{json.dumps(model, indent=2)}"
            )]

        elif name == "update_data_model":
            result = await client.update_data_model(
                arguments["project_id"],
                arguments["model_id"],
                {k: v for k, v in arguments.items() if k not in ["project_id", "model_id"]}
            )
            return [TextContent(
                type="text",
                text=f"✅ Data model '{result['name']}' updated successfully!"
            )]

        elif name == "delete_data_model":
            await client.delete_data_model(arguments["project_id"], arguments["model_id"])
            return [TextContent(
                type="text",
                text=f"🗑️  Data model deleted successfully"
            )]

        elif name == "create_relationship":
            result = await client.create_relationship(
                arguments["project_id"],
                arguments["source_model_id"],
                {k: v for k, v in arguments.items() if k not in ["project_id", "source_model_id"]}
            )
            return [TextContent(
                type="text",
                text=f"✅ Relationship created: {result['type']} to {result['target_model']}"
            )]

        # Services
        elif name == "create_service":
            result = await client.create_service(
                arguments["project_id"],
                {k: v for k, v in arguments.items() if k != "project_id"}
            )
            return [TextContent(
                type="text",
                text=f"✅ Service '{result['name']}' created!\n\n"
                     f"Service ID: {result['id']}\n\n"
                     f"Next steps:\n"
                     f"- Add schemas with create_service_schema\n"
                     f"- Add functions with create_service_function\n"
                     f"- Add endpoints with create_endpoint"
            )]

        elif name == "list_services":
            services = await client.list_services(arguments["project_id"])
            if not services:
                return [TextContent(type="text", text="No services found. Create one with create_service.")]

            text = f"⚙️  Found {len(services)} service(s):\n\n"
            for s in services:
                text += f"• {s['name']} (ID: {s['id']})\n"
                if s.get('description'):
                    text += f"  {s['description']}\n"
            return [TextContent(type="text", text=text)]

        elif name == "get_service":
            service = await client.get_service(arguments["project_id"], arguments["service_id"])
            return [TextContent(
                type="text",
                text=f"📋 Service: {service['name']}\n\n{json.dumps(service, indent=2)}"
            )]

        elif name == "update_service":
            result = await client.update_service(
                arguments["project_id"],
                arguments["service_id"],
                {k: v for k, v in arguments.items() if k not in ["project_id", "service_id"]}
            )
            return [TextContent(
                type="text",
                text=f"✅ Service '{result['name']}' updated successfully!"
            )]

        elif name == "delete_service":
            await client.delete_service(arguments["project_id"], arguments["service_id"])
            return [TextContent(
                type="text",
                text=f"🗑️  Service deleted successfully"
            )]

        elif name == "list_service_schemas":
            schemas = await client.list_service_schemas(arguments["project_id"], arguments["service_id"])
            if not schemas:
                return [TextContent(type="text", text="No schemas found. Create one with create_service_schema.")]

            text = f"📄 Found {len(schemas)} schema(s):\n\n"
            for s in schemas:
                text += f"• {s['name']} (ID: {s['id']})\n"
                text += f"  Fields: {len(s.get('fields', []))}\n"
            return [TextContent(type="text", text=text)]

        elif name == "create_service_schema":
            result = await client.create_service_schema(
                arguments["project_id"],
                arguments["service_id"],
                {k: v for k, v in arguments.items() if k not in ["project_id", "service_id"]}
            )
            return [TextContent(
                type="text",
                text=f"✅ Schema '{result['name']}' created with {len(result.get('fields', []))} fields"
            )]

        elif name == "list_service_functions":
            functions = await client.list_service_functions(arguments["project_id"], arguments["service_id"])
            if not functions:
                return [TextContent(type="text", text="No functions found. Create one with create_service_function.")]

            text = f"⚡ Found {len(functions)} function(s):\n\n"
            for f in functions:
                text += f"• {f['name']} (ID: {f['id']})\n"
                if f.get('return_type'):
                    text += f"  Returns: {f['return_type']}\n"
            return [TextContent(type="text", text=text)]

        elif name == "create_service_function":
            result = await client.create_service_function(
                arguments["project_id"],
                arguments["service_id"],
                {k: v for k, v in arguments.items() if k not in ["project_id", "service_id"]}
            )
            return [TextContent(
                type="text",
                text=f"✅ Function '{result['name']}' created"
            )]

        # Endpoints
        elif name == "create_endpoint":
            result = await client.create_endpoint(
                arguments["project_id"],
                arguments["service_id"],
                {k: v for k, v in arguments.items() if k not in ["project_id", "service_id"]}
            )
            providers_info = ""
            if result.get('providers'):
                providers_info = f"\nProviders: {', '.join([p['variable_name'] for p in result['providers']])}"

            return [TextContent(
                type="text",
                text=f"✅ Endpoint created!\n\n"
                     f"{result['method']} {result['path']}\n"
                     f"Function: {result['function_name']}\n"
                     f"Status: {result.get('status_code', 200)}"
                     f"{providers_info}"
            )]

        elif name == "list_endpoints":
            endpoints = await client.list_endpoints(
                arguments["project_id"],
                arguments["service_id"]
            )
            if not endpoints:
                return [TextContent(type="text", text="No endpoints found. Create one with create_endpoint.")]

            text = f"🌐 Found {len(endpoints)} endpoint(s):\n\n"
            for e in endpoints:
                text += f"• {e['method']} {e['path']}\n"
                if e.get('summary'):
                    text += f"  {e['summary']}\n"
            return [TextContent(type="text", text=text)]

        elif name == "get_endpoint":
            endpoint = await client.get_endpoint(
                arguments["project_id"],
                arguments["service_id"],
                arguments["endpoint_id"]
            )
            return [TextContent(
                type="text",
                text=f"📋 Endpoint: {endpoint['method']} {endpoint['path']}\n\n{json.dumps(endpoint, indent=2)}"
            )]

        elif name == "update_endpoint":
            result = await client.update_endpoint(
                arguments["project_id"],
                arguments["service_id"],
                arguments["endpoint_id"],
                {k: v for k, v in arguments.items() if k not in ["project_id", "service_id", "endpoint_id"]}
            )
            return [TextContent(
                type="text",
                text=f"✅ Endpoint {result['method']} {result['path']} updated successfully!"
            )]

        elif name == "delete_endpoint":
            await client.delete_endpoint(
                arguments["project_id"],
                arguments["service_id"],
                arguments["endpoint_id"]
            )
            return [TextContent(
                type="text",
                text=f"🗑️  Endpoint deleted successfully"
            )]

        # Dependencies
        elif name == "create_dependency":
            result = await client.create_dependency(
                arguments["project_id"],
                {k: v for k, v in arguments.items() if k != "project_id"}
            )
            return [TextContent(
                type="text",
                text=f"✅ {result['type'].title()} '{result['name']}' created!\n\n"
                     f"Dependency ID: {result['id']}\n"
                     f"Return type: {result.get('return_type', 'None')}\n\n"
                     f"Use this dependency in endpoints with the {'middlewares' if result['type'] == 'guard' else 'providers'} field"
            )]

        elif name == "list_dependencies":
            deps = await client.list_dependencies(arguments["project_id"])
            if not deps:
                return [TextContent(type="text", text="No dependencies found. Create one with create_dependency.")]

            guards = [d for d in deps if d['type'] == 'guard']
            providers = [d for d in deps if d['type'] == 'provider']

            text = f"🔐 Found {len(deps)} dependenc{'ies' if len(deps) != 1 else 'y'}:\n\n"
            if guards:
                text += "Guards (authorization/validation):\n"
                for g in guards:
                    text += f"• {g['name']} (ID: {g['id']})\n"
            if providers:
                text += "\nProviders (value injection):\n"
                for p in providers:
                    text += f"• {p['name']} → {p.get('return_type', 'Any')} (ID: {p['id']})\n"

            return [TextContent(type="text", text=text)]

        elif name == "get_dependency":
            dependency = await client.get_dependency(arguments["project_id"], arguments["dependency_id"])
            return [TextContent(
                type="text",
                text=f"📋 Dependency: {dependency['name']} ({dependency['type']})\n\n{json.dumps(dependency, indent=2)}"
            )]

        elif name == "update_dependency":
            result = await client.update_dependency(
                arguments["project_id"],
                arguments["dependency_id"],
                {k: v for k, v in arguments.items() if k not in ["project_id", "dependency_id"]}
            )
            return [TextContent(
                type="text",
                text=f"✅ Dependency '{result['name']}' updated successfully!"
            )]

        elif name == "delete_dependency":
            await client.delete_dependency(arguments["project_id"], arguments["dependency_id"])
            return [TextContent(
                type="text",
                text=f"🗑️  Dependency deleted successfully"
            )]

        # Code Generation
        elif name == "generate_code":
            result = await client.generate_code(
                arguments["project_id"],
                arguments.get("force", False)
            )
            return [TextContent(
                type="text",
                text=f"🎉 Code generated successfully!\n\n"
                     f"Path: {result['generated_path']}\n"
                     f"Checksum: {result['checksum']}\n\n"
                     f"Your FastAPI project is ready! Navigate to the generated directory and run:\n"
                     f"  cd {result['generated_path']}\n"
                     f"  pip install -r requirements.txt\n"
                     f"  uvicorn main:app --reload"
            )]

        elif name == "sync_project":
            result = await client.sync_project(arguments["project_id"])
            return [TextContent(
                type="text",
                text=f"🔄 Project synchronized!\n\n"
                     f"Path: {result['generated_path']}\n"
                     f"Updated checksum: {result['checksum']}"
            )]

        elif name == "get_project_state":
            state = await client.get_project_state(arguments["project_id"])
            return [TextContent(
                type="text",
                text=f"📊 Project State:\n\n{json.dumps(state, indent=2)}"
            )]

        elif name == "get_generated_code_path":
            # Get project to access the name
            project = await client.get_project(arguments["project_id"])
            project_name = project['name']
            generated_path = f"/home/basel-morsy/BackStudio/workspace/{project_name}"

            return [TextContent(
                type="text",
                text=f"📁 Generated Code Location:\n\n"
                     f"Server Path: {generated_path}\n\n"
                     f"To download to your local machine, use one of these methods:\n\n"
                     f"Method 1 - SCP (from your local machine):\n"
                     f"  scp -r mypc:{generated_path} C:\\Users\\bmors\\Downloads\\{project_name}\n\n"
                     f"Method 2 - SFTP:\n"
                     f"  sftp mypc\n"
                     f"  get -r {generated_path} C:\\Users\\bmors\\Downloads\\{project_name}\n\n"
                     f"Method 3 - VSCode Remote Explorer:\n"
                     f"  Connect to mypc via Remote SSH, then copy the folder from {generated_path}"
            )]

        elif name == "download_project":
            import os
            import pathlib

            # Get project to access the name
            project = await client.get_project(arguments["project_id"])
            project_name = project['name']

            # Download the ZIP file from the API
            zip_content = await client.download_project(arguments["project_id"])

            # Determine destination path
            destination = arguments.get("destination")
            if not destination:
                # Default to Windows Downloads folder
                downloads_folder = pathlib.Path.home() / "Downloads"
                destination = downloads_folder / f"{project_name}.zip"
            else:
                destination = pathlib.Path(destination)

            # Ensure parent directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)

            # Write the ZIP file
            with open(destination, 'wb') as f:
                f.write(zip_content)

            return [TextContent(
                type="text",
                text=f"✅ Project downloaded successfully!\n\n"
                     f"Location: {destination}\n"
                     f"Size: {len(zip_content) / 1024:.2f} KB\n\n"
                     f"You can now extract the ZIP file to start working with your generated FastAPI project."
            )]

        else:
            return [TextContent(
                type="text",
                text=f"❌ Unknown tool: {name}"
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ Error: {str(e)}\n\nPlease check your inputs and try again."
        )]


# ==================== Server Entry Point ====================

async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
