"""Service for managing BackStudio projects"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status

from backend.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectSummary, ProjectState, Framework
)
from backend.schemas.data import DataModel, DataModelCreate, DataModelUpdate, RelationshipSpec, RelationshipCreate, RelationshipUpdate
from backend.schemas.service import Service, ServiceCreate, ServiceUpdate, ServiceSchema, ServiceSchemaCreate, ServiceSchemaUpdate
from backend.schemas.service import ServiceFunction, ServiceFunctionCreate, ServiceFunctionUpdate
from backend.schemas.service import ServiceEndpoint, ServiceEndpointCreate, ServiceEndpointUpdate
from backend.schemas.middleware import Middleware, MiddlewareCreate, MiddlewareUpdate
from backend.schemas.dependency import Dependency, DependencyCreate, DependencyUpdate
from backend.schemas.configuration import DatabaseConfig, DatabaseConfigCreate, DatabaseConfigUpdate
from backend.schemas.configuration import FrameworkConfig, FrameworkConfigCreate, FrameworkConfigUpdate
from backend.schemas.configuration import SecurityConfig, SecurityConfigCreate, SecurityConfigUpdate
from backend.utils.checksum import compute_checksum, verify_checksum
from backend.utils.file_ops import (
    ensure_directory, read_json_file, write_json_file,
    delete_directory, get_timestamp
)
from backend.utils.id_generator import (
    generate_project_id, generate_model_id, generate_service_id,
    generate_schema_id, generate_function_id, generate_endpoint_id,
    generate_middleware_id, generate_dependency_id, generate_relation_id
)


class ProjectService:
    """Service for managing BackStudio projects and their complete state"""

    def __init__(self, workspace_dir: str = "workspace"):
        """
        Initialize project service.

        Args:
            workspace_dir: Directory where project files are stored
        """
        self.workspace_dir = Path(workspace_dir)
        ensure_directory(self.workspace_dir)

        # In-memory stores for project components
        self.projects: Dict[str, Dict[str, Any]] = {}
        self.models: Dict[str, Dict[str, Any]] = {}
        self.relations: Dict[str, Dict[str, Any]] = {}
        self.services: Dict[str, Dict[str, Any]] = {}
        self.schemas: Dict[str, Dict[str, Any]] = {}
        self.functions: Dict[str, Dict[str, Any]] = {}
        self.endpoints: Dict[str, Dict[str, Any]] = {}
        self.middlewares: Dict[str, Dict[str, Any]] = {}
        self.dependencies: Dict[str, Dict[str, Any]] = {}

        self._load_all_projects()

    def _load_all_projects(self) -> None:
        """
        Load all existing projects from workspace.

        Projects are organized as: workspace/{project_name}/state.json
        """
        if not self.workspace_dir.exists():
            return

        for project_dir in self.workspace_dir.iterdir():
            if project_dir.is_dir():
                state_file = project_dir / "state.json"
                if state_file.exists():
                    try:
                        state = read_json_file(state_file)
                        # Verify that folder name matches project name
                        if project_dir.name == state.get('name'):
                            self.projects[state['id']] = state
                            # Load components for this project
                            self._load_components(state['id'])
                    except Exception:
                        pass  # Skip corrupted project files

    def _get_project_dir(self, project_id: str) -> Path:
        """
        Get project directory path based on project name.

        Args:
            project_id: Project identifier

        Returns:
            Path to project directory (workspace/{project_name}/)
        """
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        project_name = self.projects[project_id]['name']
        return self.workspace_dir / project_name

    def _save_project_state(self, project_id: str) -> None:
        """
        Save complete project state to disk with checksum.

        Args:
            project_id: Project identifier
        """
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        state = self.projects[project_id].copy()
        state['updated_at'] = get_timestamp()

        # Compute checksum (excluding checksum field itself)
        state['checksum'] = compute_checksum(state)

        # Save to file
        project_dir = self._get_project_dir(project_id)
        ensure_directory(project_dir)
        write_json_file(project_dir / "state.json", state)

        # Update in-memory state
        self.projects[project_id] = state

        # Save component data (models, services, schemas, functions, endpoints, etc.)
        self._save_components(project_id)

    def _save_components(self, project_id: str) -> None:
        """
        Save all project components (models, services, schemas, etc.) to disk.

        Args:
            project_id: Project identifier
        """
        project_dir = self._get_project_dir(project_id)
        project_state = self.projects[project_id]

        # Get all service IDs for this project
        project_service_ids = set(project_state.get('services', []))

        # Get all model names for this project (to filter relations)
        project_model_names = set()
        for mid in project_state.get('models', []):
            if mid in self.models:
                project_model_names.add(self.models[mid]['name'])

        # Helper function to check if a relation belongs to this project
        def belongs_to_project(relation):
            source_model = relation.get('source', {}).get('model', '')
            target_model = relation.get('target', {}).get('model', '')
            return source_model in project_model_names or target_model in project_model_names

        # Collect all components for this project
        components = {
            'models': {mid: self.models[mid] for mid in project_state.get('models', []) if mid in self.models},
            'relations': {rid: self.relations[rid] for rid in self.relations if belongs_to_project(self.relations[rid])},
            'services': {sid: self.services[sid] for sid in project_state.get('services', []) if sid in self.services},
            'schemas': {sid: self.schemas[sid] for sid in self.schemas if self.schemas[sid].get('service_id') in project_service_ids},
            'functions': {fid: self.functions[fid] for fid in self.functions if self.functions[fid].get('service_id') in project_service_ids},
            'endpoints': {eid: self.endpoints[eid] for eid in self.endpoints if self.endpoints[eid].get('service_id') in project_service_ids},
            'middlewares': {mid: self.middlewares[mid] for mid in project_state.get('middlewares', []) if mid in self.middlewares},
            'dependencies': {did: self.dependencies[did] for did in project_state.get('dependencies', []) if did in self.dependencies},
        }

        # Save to components.json
        write_json_file(project_dir / "components.json", components)

    def _load_components(self, project_id: str) -> None:
        """
        Load all project components from disk.

        Args:
            project_id: Project identifier
        """
        project_dir = self._get_project_dir(project_id)
        components_file = project_dir / "components.json"

        if not components_file.exists():
            return

        try:
            components = read_json_file(components_file)

            # Load components into memory
            for model_id, model_data in components.get('models', {}).items():
                self.models[model_id] = model_data

            for rel_id, rel_data in components.get('relations', {}).items():
                self.relations[rel_id] = rel_data

            for svc_id, svc_data in components.get('services', {}).items():
                self.services[svc_id] = svc_data

            for schema_id, schema_data in components.get('schemas', {}).items():
                self.schemas[schema_id] = schema_data

            for func_id, func_data in components.get('functions', {}).items():
                self.functions[func_id] = func_data

            for ep_id, ep_data in components.get('endpoints', {}).items():
                self.endpoints[ep_id] = ep_data

            for mid_id, mid_data in components.get('middlewares', {}).items():
                self.middlewares[mid_id] = mid_data

            for dep_id, dep_data in components.get('dependencies', {}).items():
                self.dependencies[dep_id] = dep_data

        except Exception as e:
            print(f"Warning: Failed to load components for project {project_id}: {e}")

    # ========== Project Operations ==========

    def list_projects(self) -> List[ProjectSummary]:
        """
        List all projects with summary information.

        Returns:
            List of project summaries
        """
        return [
            ProjectSummary(
                id=p['id'],
                name=p['name'],
                version=p['version'],
                framework=p['framework'],
                created_at=p['created_at'],
                updated_at=p['updated_at']
            )
            for p in self.projects.values()
        ]

    def create_project(self, project_data: ProjectCreate) -> ProjectState:
        """
        Create a new project with initial state.

        Args:
            project_data: Project creation data

        Returns:
            Created project state
        """
        project_id = generate_project_id()
        timestamp = get_timestamp()

        state = {
            'id': project_id,
            'name': project_data.name,
            'description': project_data.description,
            'version': project_data.version,
            'framework': project_data.framework,
            'models': [],
            'services': [],
            'middlewares': [],
            'dependencies': [],
            'database_config': None,
            'framework_config': None,
            'security_config': None,
            'created_at': timestamp,
            'updated_at': timestamp,
            'checksum': ''
        }

        # Add pre-defined get_db dependency for database session management
        get_db_dep_id = 'dep_get_db_' + project_id[:8]
        get_db_dependency = {
            'id': get_db_dep_id,
            'name': 'get_db',
            'type': 'provider',
            'description': 'Get database session',
            'scope': 'request',
            'function_name': 'get_db',
            'return_type': 'Session',
            'parameters': [],
            'is_async': False,
            'created_at': timestamp,
            'updated_at': timestamp
        }
        # Store dependency ID in project state (not the dict object)
        state['dependencies'].append(get_db_dep_id)
        # Store actual dependency object in dependencies dict
        self.dependencies[get_db_dep_id] = get_db_dependency

        # Compute and set checksum
        state['checksum'] = compute_checksum(state)

        self.projects[project_id] = state
        self._save_project_state(project_id)

        return ProjectState(**state)

    def get_project(self, project_id: str) -> ProjectState:
        """
        Get complete project state.

        Args:
            project_id: Project identifier

        Returns:
            Project state

        Raises:
            HTTPException: If project not found
        """
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        return ProjectState(**self.projects[project_id])

    def update_project(self, project_id: str, update_data: ProjectUpdate) -> ProjectState:
        """
        Update project basic information.

        Args:
            project_id: Project identifier
            update_data: Fields to update

        Returns:
            Updated project state
        """
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        project = self.projects[project_id]

        # Update only provided fields
        if update_data.name is not None:
            project['name'] = update_data.name
        if update_data.description is not None:
            project['description'] = update_data.description
        if update_data.version is not None:
            project['version'] = update_data.version
        if update_data.framework is not None:
            project['framework'] = update_data.framework

        self._save_project_state(project_id)
        return ProjectState(**self.projects[project_id])

    def delete_project(self, project_id: str) -> None:
        """
        Delete project and all associated data.

        Args:
            project_id: Project identifier
        """
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        # Delete from disk
        project_dir = self._get_project_dir(project_id)
        delete_directory(project_dir)

        # Remove from memory
        del self.projects[project_id]

        # Clean up all associated components
        self.models = {k: v for k, v in self.models.items() if v.get('project_id') != project_id}
        self.services = {k: v for k, v in self.services.items() if v.get('project_id') != project_id}
        self.middlewares = {k: v for k, v in self.middlewares.items() if v.get('project_id') != project_id}
        self.dependencies = {k: v for k, v in self.dependencies.items() if v.get('project_id') != project_id}

    def get_project_state_json(self, project_id: str) -> Dict[str, Any]:
        """
        Get project state as raw JSON dictionary with enriched nested data.

        This method enriches the state by replacing IDs with full objects
        for use in code generation templates.

        Args:
            project_id: Project identifier

        Returns:
            Enriched project state dictionary with full nested objects
        """
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get base project state
        base_state = self.projects[project_id].copy()

        # Enrich with full model data
        enriched_models = []
        for model_id in base_state.get('models', []):
            if model_id in self.models:
                model_data = self.models[model_id].copy()

                # Add relationships for this model (where it's source OR target)
                model_name = model_data.get('name')
                model_data['relationships'] = [
                    rel for rel in self.relations.values()
                    if rel.get('source', {}).get('model') == model_name or
                       rel.get('target', {}).get('model') == model_name
                ]

                enriched_models.append(model_data)
        base_state['data_models'] = enriched_models

        # Enrich with full service data
        enriched_services = []
        for service_id in base_state.get('services', []):
            if service_id in self.services:
                service_data = self.services[service_id].copy()

                # Add full schemas, functions, and endpoints
                service_data['schemas'] = [
                    self.schemas[sid] for sid in service_data.get('schemas', [])
                    if sid in self.schemas
                ]
                service_data['functions'] = [
                    self.functions[fid] for fid in service_data.get('functions', [])
                    if fid in self.functions
                ]
                service_data['endpoints'] = [
                    self.endpoints[eid] for eid in service_data.get('endpoints', [])
                    if eid in self.endpoints
                ]

                enriched_services.append(service_data)
        base_state['services'] = enriched_services

        # Enrich with full middleware data
        enriched_middlewares = []
        for mw_id in base_state.get('middlewares', []):
            if mw_id in self.middlewares:
                enriched_middlewares.append(self.middlewares[mw_id])
        base_state['middlewares'] = enriched_middlewares

        # Enrich with full dependency data
        enriched_dependencies = []
        for dep_id in base_state.get('dependencies', []):
            if dep_id in self.dependencies:
                enriched_dependencies.append(self.dependencies[dep_id])
        base_state['dependencies'] = enriched_dependencies

        # Add all relationships
        all_relations = list(self.relations.values())
        base_state['relationships'] = all_relations

        return base_state

    # ========== Data Model Operations ==========

    def list_models(self, project_id: str) -> List[DataModel]:
        """List all data models in project"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        project_models = [
            DataModel(**self.models[mid])
            for mid in self.projects[project_id]['models']
            if mid in self.models
        ]
        return project_models

    def create_model(self, project_id: str, model_data: DataModelCreate) -> DataModel:
        """Create a new data model"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        model_id = generate_model_id()
        timestamp = get_timestamp()

        model = {
            'id': model_id,
            'project_id': project_id,
            'name': model_data.name,
            'table_name': model_data.table_name or model_data.name.lower(),
            'fields': [f.model_dump() for f in model_data.fields],
            'created_at': timestamp,
            'updated_at': timestamp
        }

        self.models[model_id] = model
        self.projects[project_id]['models'].append(model_id)
        self._save_project_state(project_id)

        return DataModel(**model)

    def get_model(self, project_id: str, model_id: str) -> DataModel:
        """Get specific data model"""
        if model_id not in self.models:
            raise HTTPException(status_code=404, detail="Model not found")

        if self.models[model_id]['project_id'] != project_id:
            raise HTTPException(status_code=403, detail="Model doesn't belong to this project")

        return DataModel(**self.models[model_id])

    def update_model(self, project_id: str, model_id: str, update_data: DataModelUpdate) -> DataModel:
        """Update data model"""
        if model_id not in self.models:
            raise HTTPException(status_code=404, detail="Model not found")

        model = self.models[model_id]
        if model['project_id'] != project_id:
            raise HTTPException(status_code=403, detail="Model doesn't belong to this project")

        if update_data.name is not None:
            model['name'] = update_data.name
        if update_data.table_name is not None:
            model['table_name'] = update_data.table_name
        if update_data.fields is not None:
            model['fields'] = [f.model_dump() for f in update_data.fields]

        model['updated_at'] = get_timestamp()
        self._save_project_state(project_id)

        return DataModel(**model)

    def delete_model(self, project_id: str, model_id: str) -> None:
        """Delete data model"""
        if model_id not in self.models:
            raise HTTPException(status_code=404, detail="Model not found")

        del self.models[model_id]
        self.projects[project_id]['models'] = [
            m for m in self.projects[project_id]['models'] if m != model_id
        ]
        self._save_project_state(project_id)

    # ========== Relationship Operations ==========

    def list_relations(self, project_id: str, model_id: str) -> List[RelationshipSpec]:
        """List relationships for a model"""
        # Get the model name from the model_id
        if model_id not in self.models:
            return []

        model_name = self.models[model_id]['name']

        return [
            RelationshipSpec(**rel)
            for rel in self.relations.values()
            if (rel.get('source', {}).get('model') == model_name or
                rel.get('target', {}).get('model') == model_name)
        ]

    def create_relation(self, project_id: str, model_id: str, relation_data: RelationshipCreate) -> RelationshipSpec:
        """Create a relationship"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        relation_id = generate_relation_id()
        relation = {
            'id': relation_id,
            'name': relation_data.name,
            'cardinality': relation_data.cardinality,
            'source': relation_data.source.model_dump(),
            'target': relation_data.target.model_dump(),
            'foreign_key': relation_data.foreign_key.model_dump() if relation_data.foreign_key else None,
            'association_table': relation_data.association_table.model_dump() if relation_data.association_table else None,
            'joins': relation_data.joins.model_dump() if relation_data.joins else None,
            'behavior': relation_data.behavior.model_dump() if relation_data.behavior else None
        }

        self.relations[relation_id] = relation
        self._save_project_state(project_id)

        return RelationshipSpec(**relation)

    def get_relation(self, project_id: str, model_id: str, relation_id: str) -> RelationshipSpec:
        """Get specific relationship"""
        if relation_id not in self.relations:
            raise HTTPException(status_code=404, detail="Relation not found")

        return RelationshipSpec(**self.relations[relation_id])

    def update_relation(self, project_id: str, model_id: str, relation_id: str, update_data: RelationshipUpdate) -> RelationshipSpec:
        """Update relationship"""
        if relation_id not in self.relations:
            raise HTTPException(status_code=404, detail="Relation not found")

        relation = self.relations[relation_id]

        if update_data.name is not None:
            relation['name'] = update_data.name
        if update_data.cardinality is not None:
            relation['cardinality'] = update_data.cardinality
        if update_data.source is not None:
            relation['source'] = update_data.source.model_dump()
        if update_data.target is not None:
            relation['target'] = update_data.target.model_dump()
        if update_data.foreign_key is not None:
            relation['foreign_key'] = update_data.foreign_key.model_dump()
        if update_data.association_table is not None:
            relation['association_table'] = update_data.association_table.model_dump()

        self._save_project_state(project_id)
        return RelationshipSpec(**relation)

    def delete_relation(self, project_id: str, model_id: str, relation_id: str) -> None:
        """Delete relationship"""
        if relation_id not in self.relations:
            raise HTTPException(status_code=404, detail="Relation not found")

        del self.relations[relation_id]
        self._save_project_state(project_id)

    # ========== Service Operations ==========

    def list_services(self, project_id: str) -> List[Service]:
        """List all services"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        return [
            Service(**self.services[sid])
            for sid in self.projects[project_id]['services']
            if sid in self.services
        ]

    def create_service(self, project_id: str, service_data: ServiceCreate) -> Service:
        """Create a new service"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        service_id = generate_service_id()
        timestamp = get_timestamp()

        service = {
            'id': service_id,
            'project_id': project_id,
            'name': service_data.name,
            'description': service_data.description,
            'schemas': [],
            'functions': [],
            'endpoints': [],
            'created_at': timestamp,
            'updated_at': timestamp
        }

        self.services[service_id] = service
        self.projects[project_id]['services'].append(service_id)
        self._save_project_state(project_id)

        return Service(**service)

    def get_service(self, project_id: str, service_id: str) -> Service:
        """Get specific service"""
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        return Service(**self.services[service_id])

    def update_service(self, project_id: str, service_id: str, update_data: ServiceUpdate) -> Service:
        """Update service"""
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        service = self.services[service_id]

        if update_data.name is not None:
            service['name'] = update_data.name
        if update_data.description is not None:
            service['description'] = update_data.description

        service['updated_at'] = get_timestamp()
        self._save_project_state(project_id)

        return Service(**service)

    def delete_service(self, project_id: str, service_id: str) -> None:
        """Delete service"""
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        del self.services[service_id]
        self.projects[project_id]['services'] = [
            s for s in self.projects[project_id]['services'] if s != service_id
        ]
        self._save_project_state(project_id)

    # ========== Service Schema Operations ==========

    def list_service_schemas(self, project_id: str, service_id: str) -> List[ServiceSchema]:
        """List all schemas in a service"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        return [
            ServiceSchema(**self.schemas[sid])
            for sid in self.services[service_id].get('schemas', [])
            if sid in self.schemas
        ]

    def create_service_schema(self, project_id: str, service_id: str, schema_data: ServiceSchemaCreate) -> ServiceSchema:
        """Create a new service schema"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        schema_id = generate_schema_id()
        timestamp = get_timestamp()

        schema = {
            'id': schema_id,
            'service_id': service_id,
            'name': schema_data.name,
            'description': schema_data.description,
            'fields': [f.model_dump() for f in schema_data.fields],
            'created_at': timestamp,
            'updated_at': timestamp
        }

        self.schemas[schema_id] = schema
        if 'schemas' not in self.services[service_id]:
            self.services[service_id]['schemas'] = []
        self.services[service_id]['schemas'].append(schema_id)
        self._save_project_state(project_id)

        return ServiceSchema(**schema)

    def get_service_schema(self, project_id: str, service_id: str, schema_id: str) -> ServiceSchema:
        """Get specific service schema"""
        if schema_id not in self.schemas:
            raise HTTPException(status_code=404, detail="Schema not found")
        if self.schemas[schema_id]['service_id'] != service_id:
            raise HTTPException(status_code=403, detail="Schema doesn't belong to this service")

        return ServiceSchema(**self.schemas[schema_id])

    def update_service_schema(self, project_id: str, service_id: str, schema_id: str, update_data: ServiceSchemaUpdate) -> ServiceSchema:
        """Update service schema"""
        if schema_id not in self.schemas:
            raise HTTPException(status_code=404, detail="Schema not found")

        schema = self.schemas[schema_id]
        if schema['service_id'] != service_id:
            raise HTTPException(status_code=403, detail="Schema doesn't belong to this service")

        if update_data.name is not None:
            schema['name'] = update_data.name
        if update_data.description is not None:
            schema['description'] = update_data.description
        if update_data.fields is not None:
            schema['fields'] = [f.model_dump() for f in update_data.fields]

        schema['updated_at'] = get_timestamp()
        self._save_project_state(project_id)

        return ServiceSchema(**schema)

    def delete_service_schema(self, project_id: str, service_id: str, schema_id: str) -> None:
        """Delete service schema"""
        if schema_id not in self.schemas:
            raise HTTPException(status_code=404, detail="Schema not found")

        del self.schemas[schema_id]
        if schema_id in self.services[service_id]['schemas']:
            self.services[service_id]['schemas'].remove(schema_id)
        self._save_project_state(project_id)

    # ========== Service Function Operations ==========

    def list_service_functions(self, project_id: str, service_id: str) -> List[ServiceFunction]:
        """List all functions in a service"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        return [
            ServiceFunction(**self.functions[fid])
            for fid in self.services[service_id].get('functions', [])
            if fid in self.functions
        ]

    def create_service_function(self, project_id: str, service_id: str, function_data: ServiceFunctionCreate) -> ServiceFunction:
        """Create a new service function"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        function_id = generate_function_id()
        timestamp = get_timestamp()

        function = {
            'id': function_id,
            'service_id': service_id,
            'name': function_data.name,
            'description': function_data.description,
            'parameters': [p.model_dump() for p in function_data.parameters] if function_data.parameters else [],
            'return_type': function_data.return_type,
            'is_async': function_data.is_async,
            'created_at': timestamp,
            'updated_at': timestamp
        }

        self.functions[function_id] = function
        if 'functions' not in self.services[service_id]:
            self.services[service_id]['functions'] = []
        self.services[service_id]['functions'].append(function_id)
        self._save_project_state(project_id)

        return ServiceFunction(**function)

    def get_service_function(self, project_id: str, service_id: str, function_id: str) -> ServiceFunction:
        """Get specific service function"""
        if function_id not in self.functions:
            raise HTTPException(status_code=404, detail="Function not found")
        if self.functions[function_id]['service_id'] != service_id:
            raise HTTPException(status_code=403, detail="Function doesn't belong to this service")

        return ServiceFunction(**self.functions[function_id])

    def update_service_function(self, project_id: str, service_id: str, function_id: str, update_data: ServiceFunctionUpdate) -> ServiceFunction:
        """Update service function"""
        if function_id not in self.functions:
            raise HTTPException(status_code=404, detail="Function not found")

        function = self.functions[function_id]
        if function['service_id'] != service_id:
            raise HTTPException(status_code=403, detail="Function doesn't belong to this service")

        if update_data.name is not None:
            function['name'] = update_data.name
        if update_data.description is not None:
            function['description'] = update_data.description
        if update_data.parameters is not None:
            function['parameters'] = [p.model_dump() for p in update_data.parameters]
        if update_data.return_type is not None:
            function['return_type'] = update_data.return_type
        if update_data.is_async is not None:
            function['is_async'] = update_data.is_async

        function['updated_at'] = get_timestamp()
        self._save_project_state(project_id)

        return ServiceFunction(**function)

    def delete_service_function(self, project_id: str, service_id: str, function_id: str) -> None:
        """Delete service function"""
        if function_id not in self.functions:
            raise HTTPException(status_code=404, detail="Function not found")

        del self.functions[function_id]
        if function_id in self.services[service_id]['functions']:
            self.services[service_id]['functions'].remove(function_id)
        self._save_project_state(project_id)

    # ========== Service Endpoint Operations ==========

    def list_service_endpoints(self, project_id: str, service_id: str) -> List[ServiceEndpoint]:
        """List all endpoints in a service"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        return [
            ServiceEndpoint(**self.endpoints[eid])
            for eid in self.services[service_id].get('endpoints', [])
            if eid in self.endpoints
        ]

    def _validate_provider_bindings(self, project_id: str, providers: List[Dict[str, str]], parameters: List[Any]) -> None:
        """
        Validate provider bindings for an endpoint.

        Args:
            project_id: Project identifier
            providers: List of provider bindings [{'dependency_id': '...'}]
            parameters: List of endpoint parameters to check for conflicts

        Raises:
            HTTPException: If validation fails
        """
        # DEBUG: Log received providers
        import sys
        print(f"=== VALIDATE PROVIDER BINDINGS DEBUG ===", flush=True)
        print(f"Received providers: {providers}", flush=True)
        print(f"Provider count: {len(providers) if providers else 0}", flush=True)
        for i, binding in enumerate(providers or []):
            print(f"Provider {i}: {binding}", flush=True)
            print(f"  Type: {type(binding)}", flush=True)
            # Handle both dict and Pydantic model
            if hasattr(binding, 'dependency_id'):
                print(f"  dependency_id (attr): '{binding.dependency_id}'", flush=True)
            elif isinstance(binding, dict) and 'dependency_id' in binding:
                print(f"  dependency_id (dict): '{binding['dependency_id']}'", flush=True)
            else:
                print(f"  NO dependency_id found!", flush=True)
        print(f"=========================================", flush=True)
        sys.stdout.flush()

        if not providers:
            return

        # Get all dependencies for this project
        project_deps = {dep_id: dep for dep_id, dep in self.dependencies.items()
                       if dep.get('project_id') == project_id}
        provider_deps = {dep_id: dep for dep_id, dep in project_deps.items()
                        if dep.get('type') == 'provider'}

        seen_deps = set()

        for binding in providers:
            # Handle both dict and Pydantic model
            if hasattr(binding, 'dependency_id'):
                dep_id = binding.dependency_id
            elif isinstance(binding, dict) and 'dependency_id' in binding:
                dep_id = binding['dependency_id']
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Provider binding must have dependency_id"
                )

            # Check dependency exists and is provider
            if dep_id not in provider_deps:
                raise HTTPException(
                    status_code=400,
                    detail=f"Dependency {dep_id} not found or is not a provider"
                )

            # Check for duplicate dependency usage
            if dep_id in seen_deps:
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate provider dependency: {dep_id}"
                )

            seen_deps.add(dep_id)

    def create_service_endpoint(self, project_id: str, service_id: str, endpoint_data: ServiceEndpointCreate) -> ServiceEndpoint:
        """Create a new service endpoint"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if service_id not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        # Validate provider bindings
        providers = endpoint_data.providers or []
        parameters = endpoint_data.parameters or []
        self._validate_provider_bindings(project_id, providers, parameters)

        endpoint_id = generate_endpoint_id()
        timestamp = get_timestamp()

        endpoint = {
            'id': endpoint_id,
            'service_id': service_id,
            'path': endpoint_data.path,
            'method': endpoint_data.method,
            'function_name': endpoint_data.function_name,
            'summary': endpoint_data.summary,
            'description': endpoint_data.description,
            'tags': endpoint_data.tags or [],
            'parameters': [p.model_dump() for p in endpoint_data.parameters] if endpoint_data.parameters else [],
            'request_schema': endpoint_data.request_schema,
            'response_schema': endpoint_data.response_schema,
            'status_code': endpoint_data.status_code,
            'middlewares': endpoint_data.middlewares or [],
            'dependencies': endpoint_data.dependencies or [],
            'providers': providers,
            'created_at': timestamp,
            'updated_at': timestamp
        }

        self.endpoints[endpoint_id] = endpoint
        if 'endpoints' not in self.services[service_id]:
            self.services[service_id]['endpoints'] = []
        self.services[service_id]['endpoints'].append(endpoint_id)
        self._save_project_state(project_id)

        return ServiceEndpoint(**endpoint)

    def get_service_endpoint(self, project_id: str, service_id: str, endpoint_id: str) -> ServiceEndpoint:
        """Get specific service endpoint"""
        if endpoint_id not in self.endpoints:
            raise HTTPException(status_code=404, detail="Endpoint not found")
        if self.endpoints[endpoint_id]['service_id'] != service_id:
            raise HTTPException(status_code=403, detail="Endpoint doesn't belong to this service")

        return ServiceEndpoint(**self.endpoints[endpoint_id])

    def update_service_endpoint(self, project_id: str, service_id: str, endpoint_id: str, update_data: ServiceEndpointUpdate) -> ServiceEndpoint:
        """Update service endpoint"""
        if endpoint_id not in self.endpoints:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        endpoint = self.endpoints[endpoint_id]
        if endpoint['service_id'] != service_id:
            raise HTTPException(status_code=403, detail="Endpoint doesn't belong to this service")

        # Validate provider bindings if being updated
        if update_data.providers is not None:
            parameters = update_data.parameters if update_data.parameters is not None else endpoint.get('parameters', [])
            self._validate_provider_bindings(project_id, update_data.providers, parameters)

        if update_data.path is not None:
            endpoint['path'] = update_data.path
        if update_data.method is not None:
            endpoint['method'] = update_data.method
        if update_data.function_name is not None:
            endpoint['function_name'] = update_data.function_name
        if update_data.summary is not None:
            endpoint['summary'] = update_data.summary
        if update_data.description is not None:
            endpoint['description'] = update_data.description
        if update_data.tags is not None:
            endpoint['tags'] = update_data.tags
        if update_data.parameters is not None:
            endpoint['parameters'] = [p.model_dump() for p in update_data.parameters]
        if update_data.request_schema is not None:
            endpoint['request_schema'] = update_data.request_schema
        if update_data.response_schema is not None:
            endpoint['response_schema'] = update_data.response_schema
        if update_data.status_code is not None:
            endpoint['status_code'] = update_data.status_code
        if update_data.middlewares is not None:
            endpoint['middlewares'] = update_data.middlewares
        if update_data.dependencies is not None:
            endpoint['dependencies'] = update_data.dependencies
        if update_data.providers is not None:
            endpoint['providers'] = [p.model_dump() for p in update_data.providers]

        endpoint['updated_at'] = get_timestamp()
        self._save_project_state(project_id)

        return ServiceEndpoint(**endpoint)

    def delete_service_endpoint(self, project_id: str, service_id: str, endpoint_id: str) -> None:
        """Delete service endpoint"""
        if endpoint_id not in self.endpoints:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        del self.endpoints[endpoint_id]
        if endpoint_id in self.services[service_id]['endpoints']:
            self.services[service_id]['endpoints'].remove(endpoint_id)
        self._save_project_state(project_id)

    # ========== Middleware Operations ==========

    def list_middlewares(self, project_id: str) -> List[Middleware]:
        """List all middlewares"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        return [
            Middleware(**self.middlewares[mid])
            for mid in self.projects[project_id]['middlewares']
            if mid in self.middlewares
        ]

    def create_middleware(self, project_id: str, middleware_data: MiddlewareCreate) -> Middleware:
        """Create middleware"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        middleware_id = generate_middleware_id()
        timestamp = get_timestamp()

        middleware = {
            'id': middleware_id,
            'project_id': project_id,
            **middleware_data.model_dump(),
            'created_at': timestamp,
            'updated_at': timestamp
        }

        self.middlewares[middleware_id] = middleware
        self.projects[project_id]['middlewares'].append(middleware_id)
        self._save_project_state(project_id)

        return Middleware(**middleware)

    # ========== Dependency Operations ==========

    def list_dependencies(self, project_id: str) -> List[Dependency]:
        """List all dependencies"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        return [
            Dependency(**self.dependencies[did])
            for did in self.projects[project_id]['dependencies']
            if did in self.dependencies
        ]

    def create_dependency(self, project_id: str, dependency_data: DependencyCreate) -> Dependency:
        """Create dependency"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        dependency_id = generate_dependency_id()
        timestamp = get_timestamp()

        dependency = {
            'id': dependency_id,
            'project_id': project_id,
            **dependency_data.model_dump(),
            'created_at': timestamp,
            'updated_at': timestamp
        }

        self.dependencies[dependency_id] = dependency
        self.projects[project_id]['dependencies'].append(dependency_id)
        self._save_project_state(project_id)

        return Dependency(**dependency)

    def get_dependency(self, project_id: str, dependency_id: str) -> Dependency:
        """Get a specific dependency"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if dependency_id not in self.dependencies:
            raise HTTPException(status_code=404, detail="Dependency not found")

        return Dependency(**self.dependencies[dependency_id])

    def update_dependency(self, project_id: str, dependency_id: str, update_data: DependencyUpdate) -> Dependency:
        """Update a dependency"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if dependency_id not in self.dependencies:
            raise HTTPException(status_code=404, detail="Dependency not found")

        dependency = self.dependencies[dependency_id]
        update_dict = update_data.model_dump(exclude_unset=True)
        dependency.update(update_dict)
        dependency['updated_at'] = get_timestamp()

        self._save_project_state(project_id)
        return Dependency(**dependency)

    def delete_dependency(self, project_id: str, dependency_id: str):
        """Delete a dependency"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")
        if dependency_id not in self.dependencies:
            raise HTTPException(status_code=404, detail="Dependency not found")

        # Remove from dependencies dict
        del self.dependencies[dependency_id]

        # Remove from project's dependency list
        if dependency_id in self.projects[project_id]['dependencies']:
            self.projects[project_id]['dependencies'].remove(dependency_id)

        self._save_project_state(project_id)

    # ========== Configuration Operations ==========

    def get_database_config(self, project_id: str) -> Optional[DatabaseConfig]:
        """Get database configuration"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        config = self.projects[project_id].get('database_config')
        return DatabaseConfig(**config) if config else None

    def set_database_config(self, project_id: str, config_data: DatabaseConfigCreate) -> DatabaseConfig:
        """Set database configuration"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        self.projects[project_id]['database_config'] = config_data.model_dump()
        self._save_project_state(project_id)

        return DatabaseConfig(**self.projects[project_id]['database_config'])

    def get_framework_config(self, project_id: str) -> Optional[FrameworkConfig]:
        """Get framework configuration"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        config = self.projects[project_id].get('framework_config')
        return FrameworkConfig(**config) if config else None

    def set_framework_config(self, project_id: str, config_data: FrameworkConfigCreate) -> FrameworkConfig:
        """Set framework configuration"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        self.projects[project_id]['framework_config'] = config_data.model_dump()
        self._save_project_state(project_id)

        return FrameworkConfig(**self.projects[project_id]['framework_config'])

    def get_security_config(self, project_id: str) -> Optional[SecurityConfig]:
        """Get security configuration"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        config = self.projects[project_id].get('security_config')
        return SecurityConfig(**config) if config else None

    def set_security_config(self, project_id: str, config_data: SecurityConfigCreate) -> SecurityConfig:
        """Set security configuration"""
        if project_id not in self.projects:
            raise HTTPException(status_code=404, detail="Project not found")

        self.projects[project_id]['security_config'] = config_data.model_dump()
        self._save_project_state(project_id)

        return SecurityConfig(**self.projects[project_id]['security_config'])
