"""Project management API endpoints for BackStudio"""

from fastapi import APIRouter, HTTPException, status, Response
from fastapi.responses import FileResponse
from typing import List

from backend.schemas.project import ProjectCreate, ProjectUpdate, ProjectSummary, ProjectState
from backend.schemas.data import DataModel, DataModelCreate, DataModelUpdate
from backend.schemas.data import RelationshipSpec, RelationshipCreate, RelationshipUpdate
from backend.schemas.service import (
    Service, ServiceCreate, ServiceUpdate,
    ServiceSchema, ServiceSchemaCreate, ServiceSchemaUpdate,
    ServiceFunction, ServiceFunctionCreate, ServiceFunctionUpdate,
    ServiceEndpoint, ServiceEndpointCreate, ServiceEndpointUpdate
)
from backend.schemas.middleware import Middleware, MiddlewareCreate, MiddlewareUpdate
from backend.schemas.dependency import Dependency, DependencyCreate, DependencyUpdate
from backend.schemas.configuration import (
    DatabaseConfig, DatabaseConfigCreate, DatabaseConfigUpdate,
    FrameworkConfig, FrameworkConfigCreate, FrameworkConfigUpdate,
    SecurityConfig, SecurityConfigCreate, SecurityConfigUpdate
)
from backend.services.project_service import ProjectService
from backend.services.code_generator import CodeGenerator

# Initialize services
project_service = ProjectService()
code_generator = CodeGenerator()

# Create router
router = APIRouter(prefix="/api")


# ==================== Basic Project Operations ====================

@router.get("/projects/", response_model=List[ProjectSummary])
async def list_projects():
    """
    List all projects with summary information.

    Returns only project names, versions, and frameworks.
    """
    return project_service.list_projects()


@router.post("/projects/", response_model=ProjectState, status_code=status.HTTP_201_CREATED)
async def create_project(project: ProjectCreate):
    """
    Create a new project.

    Initializes state with project name and description.
    """
    return project_service.create_project(project)


@router.get("/projects/{project_id}/", response_model=ProjectState)
async def get_project(project_id: str):
    """
    Get complete project details including full state.
    """
    return project_service.get_project(project_id)


@router.put("/projects/{project_id}/", response_model=ProjectState)
async def update_project(project_id: str, update: ProjectUpdate):
    """
    Update project details (name, version, or framework).
    """
    return project_service.update_project(project_id, update)


@router.delete("/projects/{project_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str):
    """
    Delete a project and all associated data.
    """
    project_service.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Code Generation ====================

@router.post("/projects/{project_id}/generate")
async def generate_codebase(project_id: str, force: bool = False):
    """
    Generate backend code for the specified project.

    Uses Jinja2 templates to create deterministic codebase from project specs.
    """
    project_state = project_service.get_project_state_json(project_id)

    try:
        generated_dir = code_generator.generate_project(project_state, force=force)
        return {
            "message": "Code generated successfully",
            "project_id": project_id,
            "generated_path": str(generated_dir),
            "checksum": project_state['checksum']
        }
    except FileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generated code already exists. Use force=true to overwrite."
        )


@router.post("/projects/{project_id}/sync")
async def sync_project(project_id: str):
    """
    Sync generated codebase with the project state.
    Regenerates code to match current specifications.
    """
    project_state = project_service.get_project_state_json(project_id)
    project_name = project_state['name']
    generated_dir = code_generator.sync_project(project_name, project_state)

    return {
        "message": "Project synchronized successfully",
        "project_id": project_id,
        "generated_path": str(generated_dir),
        "checksum": project_state['checksum']
    }


@router.get("/projects/{project_id}/download")
async def download_codebase(project_id: str):
    """
    Download the generated codebase as a ZIP file.
    """
    try:
        # Get project to access name
        project = project_service.get_project(project_id)
        zip_path = code_generator.create_archive(project.name)
        return FileResponse(
            path=str(zip_path),
            media_type='application/zip',
            filename=f"{project.name}.zip"
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No generated code found. Generate code first."
        )


@router.get("/projects/{project_id}/state")
async def get_project_state(project_id: str):
    """
    Get the JSON state of the project.

    Returns the complete state including checksum.
    """
    return project_service.get_project_state_json(project_id)


# ==================== Data Models ====================

@router.get("/projects/{project_id}/models/", response_model=List[DataModel])
async def list_models(project_id: str):
    """List all data models in the project."""
    return project_service.list_models(project_id)


@router.get("/projects/{project_id}/provider-suggestions/{dependency_id}/")
async def get_provider_suggestions(project_id: str, dependency_id: str, variable_name: str):
    """
    Get field access suggestions for a provider dependency.

    Returns a list of valid Python expressions for accessing fields from the provider's return type.
    Useful for autocomplete in the frontend when configuring parameter mappings.

    Example:
        For get_current_user with variable_name="current_user":
        Returns ["current_user.id", "current_user.email", "current_user.organization.id", ...]
    """
    # Get the dependency details
    dependency = project_service.get_dependency(project_id, dependency_id)

    if not dependency.return_type:
        return {"suggestions": []}

    # Get all models in the project
    models = project_service.list_models(project_id)

    # Find the model that matches the return type
    model = next((m for m in models if m.name == dependency.return_type), None)
    if not model:
        return {"suggestions": []}

    # Generate suggestions
    suggestions = []
    models_dict = {m.name: m for m in models}

    def add_field_suggestions(prefix: str, model_obj, depth: int = 0):
        """Recursively generate field suggestions"""
        if depth > 2:  # Limit nesting to 2 levels
            return

        for field in model_obj.fields:
            field_path = f"{prefix}.{field.name}"
            suggestions.append(field_path)

            # If field type is another model, recursively add its fields
            if field.type.value in models_dict:
                nested_model = models_dict[field.type.value]
                add_field_suggestions(field_path, nested_model, depth + 1)

    add_field_suggestions(variable_name, model)

    return {
        "variable_name": variable_name,
        "return_type": dependency.return_type,
        "suggestions": suggestions
    }


@router.post("/projects/{project_id}/models/", response_model=DataModel, status_code=status.HTTP_201_CREATED)
async def create_model(project_id: str, model: DataModelCreate):
    """Create a new data model."""
    return project_service.create_model(project_id, model)


@router.get("/projects/{project_id}/models/{model_id}/", response_model=DataModel)
async def get_model(project_id: str, model_id: str):
    """Get details of a specific data model."""
    return project_service.get_model(project_id, model_id)


@router.put("/projects/{project_id}/models/{model_id}/", response_model=DataModel)
async def update_model(project_id: str, model_id: str, update: DataModelUpdate):
    """Update a specific data model."""
    return project_service.update_model(project_id, model_id, update)


@router.delete("/projects/{project_id}/models/{model_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(project_id: str, model_id: str):
    """Delete a specific data model."""
    project_service.delete_model(project_id, model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Relationships ====================

@router.get("/projects/{project_id}/models/{model_id}/relations/", response_model=List[RelationshipSpec])
async def list_relations(project_id: str, model_id: str):
    """List relationships for a specific data model."""
    return project_service.list_relations(project_id, model_id)


@router.post("/projects/{project_id}/models/{model_id}/relations/", response_model=RelationshipSpec, status_code=status.HTTP_201_CREATED)
async def create_relation(project_id: str, model_id: str, relation: RelationshipCreate):
    """Define relationship between data models."""
    return project_service.create_relation(project_id, model_id, relation)


@router.get("/projects/{project_id}/models/{model_id}/relations/{relation_id}/", response_model=RelationshipSpec)
async def get_relation(project_id: str, model_id: str, relation_id: str):
    """Get details of a specific relationship."""
    return project_service.get_relation(project_id, model_id, relation_id)


@router.put("/projects/{project_id}/models/{model_id}/relations/{relation_id}/", response_model=RelationshipSpec)
async def update_relation(project_id: str, model_id: str, relation_id: str, update: RelationshipUpdate):
    """Update a specific relationship."""
    return project_service.update_relation(project_id, model_id, relation_id, update)


@router.delete("/projects/{project_id}/models/{model_id}/relations/{relation_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relation(project_id: str, model_id: str, relation_id: str):
    """Delete a specific relationship."""
    project_service.delete_relation(project_id, model_id, relation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Services ====================

@router.get("/projects/{project_id}/services/", response_model=List[Service])
async def list_services(project_id: str):
    """List all services in the project."""
    return project_service.list_services(project_id)


@router.post("/projects/{project_id}/services/", response_model=Service, status_code=status.HTTP_201_CREATED)
async def create_service(project_id: str, service: ServiceCreate):
    """Create a new service."""
    return project_service.create_service(project_id, service)


@router.get("/projects/{project_id}/services/{service_id}/", response_model=Service)
async def get_service(project_id: str, service_id: str):
    """Get details of a specific service."""
    return project_service.get_service(project_id, service_id)


@router.put("/projects/{project_id}/services/{service_id}/", response_model=Service)
async def update_service(project_id: str, service_id: str, update: ServiceUpdate):
    """Update a specific service."""
    return project_service.update_service(project_id, service_id, update)


@router.delete("/projects/{project_id}/services/{service_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(project_id: str, service_id: str):
    """Delete a specific service."""
    project_service.delete_service(project_id, service_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Service Schemas ====================

@router.get("/projects/{project_id}/services/{service_id}/schemas/", response_model=List[ServiceSchema])
async def list_service_schemas(project_id: str, service_id: str):
    """List all schemas for a service."""
    return project_service.list_service_schemas(project_id, service_id)


@router.post("/projects/{project_id}/services/{service_id}/schemas/", response_model=ServiceSchema, status_code=status.HTTP_201_CREATED)
async def create_service_schema(project_id: str, service_id: str, schema: ServiceSchemaCreate):
    """Create a new schema for a service."""
    return project_service.create_service_schema(project_id, service_id, schema)


@router.get("/projects/{project_id}/services/{service_id}/schemas/{schema_id}/", response_model=ServiceSchema)
async def get_service_schema(project_id: str, service_id: str, schema_id: str):
    """Get details of a specific schema."""
    return project_service.get_service_schema(project_id, service_id, schema_id)


@router.put("/projects/{project_id}/services/{service_id}/schemas/{schema_id}/", response_model=ServiceSchema)
async def update_service_schema(project_id: str, service_id: str, schema_id: str, update: ServiceSchemaUpdate):
    """Update a specific schema."""
    return project_service.update_service_schema(project_id, service_id, schema_id, update)


@router.delete("/projects/{project_id}/services/{service_id}/schemas/{schema_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_schema(project_id: str, service_id: str, schema_id: str):
    """Delete a specific schema."""
    project_service.delete_service_schema(project_id, service_id, schema_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Service Functions ====================

@router.get("/projects/{project_id}/services/{service_id}/functions/", response_model=List[ServiceFunction])
async def list_service_functions(project_id: str, service_id: str):
    """List all functions for a service."""
    return project_service.list_service_functions(project_id, service_id)


@router.post("/projects/{project_id}/services/{service_id}/functions/", response_model=ServiceFunction, status_code=status.HTTP_201_CREATED)
async def create_service_function(project_id: str, service_id: str, function: ServiceFunctionCreate):
    """Create a new function for a service."""
    return project_service.create_service_function(project_id, service_id, function)


@router.get("/projects/{project_id}/services/{service_id}/functions/{function_id}/", response_model=ServiceFunction)
async def get_service_function(project_id: str, service_id: str, function_id: str):
    """Get details of a specific function."""
    return project_service.get_service_function(project_id, service_id, function_id)


@router.put("/projects/{project_id}/services/{service_id}/functions/{function_id}/", response_model=ServiceFunction)
async def update_service_function(project_id: str, service_id: str, function_id: str, update: ServiceFunctionUpdate):
    """Update a specific function."""
    return project_service.update_service_function(project_id, service_id, function_id, update)


@router.delete("/projects/{project_id}/services/{service_id}/functions/{function_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_function(project_id: str, service_id: str, function_id: str):
    """Delete a specific function."""
    project_service.delete_service_function(project_id, service_id, function_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Service Endpoints ====================

@router.get("/projects/{project_id}/services/{service_id}/endpoints/", response_model=List[ServiceEndpoint])
async def list_service_endpoints(project_id: str, service_id: str):
    """List all endpoints for a service."""
    return project_service.list_service_endpoints(project_id, service_id)


@router.post("/projects/{project_id}/services/{service_id}/endpoints/", response_model=ServiceEndpoint, status_code=status.HTTP_201_CREATED)
async def create_service_endpoint(project_id: str, service_id: str, endpoint: ServiceEndpointCreate):
    """Create a new endpoint for a service."""
    return project_service.create_service_endpoint(project_id, service_id, endpoint)


@router.get("/projects/{project_id}/services/{service_id}/endpoints/{endpoint_id}/", response_model=ServiceEndpoint)
async def get_service_endpoint(project_id: str, service_id: str, endpoint_id: str):
    """Get details of a specific endpoint."""
    return project_service.get_service_endpoint(project_id, service_id, endpoint_id)


@router.put("/projects/{project_id}/services/{service_id}/endpoints/{endpoint_id}/", response_model=ServiceEndpoint)
async def update_service_endpoint(project_id: str, service_id: str, endpoint_id: str, update: ServiceEndpointUpdate):
    """Update a specific endpoint."""
    try:
        return project_service.update_service_endpoint(project_id, service_id, endpoint_id, update)
    except Exception as e:
        print(f"ERROR in update_service_endpoint: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


@router.delete("/projects/{project_id}/services/{service_id}/endpoints/{endpoint_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_endpoint(project_id: str, service_id: str, endpoint_id: str):
    """Delete a specific endpoint."""
    project_service.delete_service_endpoint(project_id, service_id, endpoint_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Middlewares ====================

@router.get("/projects/{project_id}/middlewares/", response_model=List[Middleware])
async def list_middlewares(project_id: str):
    """List all middlewares in the project."""
    return project_service.list_middlewares(project_id)


@router.post("/projects/{project_id}/middlewares/", response_model=Middleware, status_code=status.HTTP_201_CREATED)
async def create_middleware(project_id: str, middleware: MiddlewareCreate):
    """Create a new middleware."""
    return project_service.create_middleware(project_id, middleware)


# ==================== Dependencies ====================

@router.get("/projects/{project_id}/dependencies/", response_model=List[Dependency])
async def list_dependencies(project_id: str):
    """List all dependencies in the project."""
    return project_service.list_dependencies(project_id)


@router.post("/projects/{project_id}/dependencies/", response_model=Dependency, status_code=status.HTTP_201_CREATED)
async def create_dependency(project_id: str, dependency: DependencyCreate):
    """Add a new dependency."""
    return project_service.create_dependency(project_id, dependency)


@router.get("/projects/{project_id}/dependencies/{dependency_id}/", response_model=Dependency)
async def get_dependency(project_id: str, dependency_id: str):
    """Get details of a specific dependency."""
    return project_service.get_dependency(project_id, dependency_id)


@router.put("/projects/{project_id}/dependencies/{dependency_id}/", response_model=Dependency)
async def update_dependency(project_id: str, dependency_id: str, update: DependencyUpdate):
    """Update a specific dependency."""
    return project_service.update_dependency(project_id, dependency_id, update)


@router.delete("/projects/{project_id}/dependencies/{dependency_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dependency(project_id: str, dependency_id: str):
    """Delete a specific dependency."""
    project_service.delete_dependency(project_id, dependency_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Configuration ====================

@router.get("/projects/{project_id}/config/database/")
async def get_database_config(project_id: str):
    """Get database configuration."""
    config = project_service.get_database_config(project_id)
    if not config:
        raise HTTPException(status_code=404, detail="Database configuration not set")
    return config


@router.post("/projects/{project_id}/config/database/", response_model=DatabaseConfig, status_code=status.HTTP_201_CREATED)
async def create_database_config(project_id: str, config: DatabaseConfigCreate):
    """Create database configuration."""
    return project_service.set_database_config(project_id, config)


@router.put("/projects/{project_id}/config/database/", response_model=DatabaseConfig)
async def update_database_config(project_id: str, config: DatabaseConfigCreate):
    """Update database configuration."""
    return project_service.set_database_config(project_id, config)


@router.get("/projects/{project_id}/config/framework/")
async def get_framework_config(project_id: str):
    """Get framework configuration."""
    config = project_service.get_framework_config(project_id)
    if not config:
        raise HTTPException(status_code=404, detail="Framework configuration not set")
    return config


@router.post("/projects/{project_id}/config/framework/", response_model=FrameworkConfig, status_code=status.HTTP_201_CREATED)
async def create_framework_config(project_id: str, config: FrameworkConfigCreate):
    """Create framework configuration."""
    return project_service.set_framework_config(project_id, config)


@router.put("/projects/{project_id}/config/framework/", response_model=FrameworkConfig)
async def update_framework_config(project_id: str, config: FrameworkConfigCreate):
    """Update framework configuration."""
    return project_service.set_framework_config(project_id, config)


@router.get("/projects/{project_id}/config/security/")
async def get_security_config(project_id: str):
    """Get security configuration."""
    config = project_service.get_security_config(project_id)
    if not config:
        raise HTTPException(status_code=404, detail="Security configuration not set")
    return config


@router.post("/projects/{project_id}/config/security/", response_model=SecurityConfig, status_code=status.HTTP_201_CREATED)
async def create_security_config(project_id: str, config: SecurityConfigCreate):
    """Create security configuration."""
    return project_service.set_security_config(project_id, config)


@router.put("/projects/{project_id}/config/security/", response_model=SecurityConfig)
async def update_security_config(project_id: str, config: SecurityConfigCreate):
    """Update security configuration."""
    return project_service.set_security_config(project_id, config)