"""Service for generating backend code from project state using Jinja2 templates"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, List
from jinja2 import Environment, FileSystemLoader, Template, select_autoescape

from backend.utils.file_ops import ensure_directory, create_zip_archive


class CodeGenerator:
    """
    Service for generating backend code from project state.

    Uses Jinja2 templates to generate deterministic code based on project specifications.
    Same specs always produce the same codebase with matching checksum.
    """

    def __init__(self, templates_dir: str = "backend/templates", output_dir: str = "workspace"):
        """
        Initialize code generator with template and output directories.

        Args:
            templates_dir: Directory containing Jinja2 templates
            output_dir: Base directory for generated projects
        """
        self.templates_dir = Path(templates_dir)
        self.output_dir = Path(output_dir)

        ensure_directory(self.output_dir)

        # Initialize Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )

        # Register custom filters
        self._register_filters()

    def _register_filters(self) -> None:
        """Register custom Jinja2 filters for code generation"""

        def to_snake_case(text: str) -> str:
            """Convert text to snake_case"""
            import re
            text = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
            return re.sub('([a-z0-9])([A-Z])', r'\1_\2', text).lower()

        def to_pascal_case(text: str) -> str:
            """Convert text to PascalCase"""
            import re
            # If already in PascalCase (starts with capital, has capitals in middle), return as-is
            if text and text[0].isupper() and any(c.isupper() for c in text[1:]):
                return text
            # Otherwise convert from snake_case or other formats
            return ''.join(word.capitalize() for word in text.replace('_', ' ').split())

        def to_camel_case(text: str) -> str:
            """Convert text to camelCase"""
            pascal = to_pascal_case(text)
            return pascal[0].lower() + pascal[1:] if pascal else ''

        def to_kebab_case(text: str) -> str:
            """Convert text to kebab-case"""
            import re
            text = re.sub('(.)([A-Z][a-z]+)', r'\1-\2', text)
            return re.sub('([a-z0-9])([A-Z])', r'\1-\2', text).lower()

        def to_python_value(value: Any) -> str:
            """Convert Python value to its string representation with correct syntax"""
            if isinstance(value, bool):
                return 'True' if value else 'False'
            elif isinstance(value, str):
                return f"'{value}'"
            elif value is None:
                return 'None'
            else:
                return str(value)

        self.jinja_env.filters['snake_case'] = to_snake_case
        self.jinja_env.filters['pascal_case'] = to_pascal_case
        self.jinja_env.filters['camel_case'] = to_camel_case
        self.jinja_env.filters['kebab_case'] = to_kebab_case
        self.jinja_env.filters['python_value'] = to_python_value

        # Register global functions for templates
        self.jinja_env.globals['get_sqlalchemy_type'] = self._get_sqlalchemy_type
        self.jinja_env.globals['get_python_type'] = self._get_python_type

    def _get_sqlalchemy_type(self, field_type: str) -> str:
        """
        Map FieldType enum values to SQLAlchemy column types.

        Args:
            field_type: Field type from schema (string, integer, etc.)

        Returns:
            SQLAlchemy type name
        """
        type_map = {
            'string': 'String',
            'integer': 'Integer',
            'float': 'Float',
            'boolean': 'Boolean',
            'datetime': 'DateTime',
            'date': 'Date',
            'text': 'Text',
            'json': 'JSON',
            'uuid': 'String'  # UUID type would require additional import
        }
        return type_map.get(str(field_type).lower(), 'String')

    def _get_python_type(self, field_type: str) -> str:
        """Map FieldType enum values to Python/Pydantic type annotations."""
        type_map = {
            'string': 'str', 'integer': 'int', 'float': 'float', 'boolean': 'bool',
            'datetime': 'datetime', 'date': 'date', 'text': 'str', 'json': 'Any', 'uuid': 'str',
        }
        # field_type may be a FieldType enum member (whose str() is "FieldType.X", not
        # its value) or a plain string, depending on how the caller built the context.
        value = field_type.value if hasattr(field_type, 'value') else field_type
        return type_map.get(str(value).lower(), 'str')

    def _render_template(self, template_path: str, context: Dict[str, Any]) -> str:
        """
        Render a Jinja2 template with given context.

        Args:
            template_path: Path to template file relative to templates_dir
            context: Template context variables

        Returns:
            Rendered template string
        """
        template = self.jinja_env.get_template(template_path)
        return template.render(**context)

    def _write_file(self, path: Path, content: str) -> None:
        """Write content to file, ensuring directory exists"""
        ensure_directory(path.parent)
        path.write_text(content, encoding='utf-8')

    def generate_project(self, project_state: Dict[str, Any], force: bool = False) -> Path:
        """
        Generate complete backend codebase from project state.

        Args:
            project_state: Complete project specification dictionary
            force: If True, overwrite existing generated code

        Returns:
            Path to generated project directory (workspace/{project_name}/codebase)

        Raises:
            FileExistsError: If project exists and force=False
            ValueError: If required configuration missing
        """
        project_name = project_state['name']
        framework = project_state['framework']

        # Output directory: workspace/{project_name}/codebase
        project_dir = self.output_dir / project_name
        codebase_dir = project_dir / "codebase"

        if codebase_dir.exists() and not force:
            raise FileExistsError(f"Generated code already exists at {codebase_dir}")

        # Create clean output directory
        if codebase_dir.exists():
            shutil.rmtree(codebase_dir)
        ensure_directory(codebase_dir)

        # Generate FastAPI project (Python only)
        if framework == 'fastapi':
            self._generate_fastapi_project(project_state, codebase_dir)
        else:
            raise ValueError(f"Unsupported framework: {framework}. Only 'fastapi' is supported.")

        return codebase_dir

    def _generate_fastapi_project(self, state: Dict[str, Any], output_dir: Path) -> None:
        """
        Generate FastAPI project structure using templates.

        Creates:
        - server.py
        - database/ (base.py, models.py, repo.py)
        - {service}/ (service.py, schemas.py, routes.py) for each service
        - middleware.py
        - dependencies.py
        - requirements.txt
        - README.md
        """
        context = {'project': state}

        # Create database directory
        db_dir = output_dir / "database"
        ensure_directory(db_dir)
        (db_dir / "__init__.py").touch()

        # Generate database files
        self._write_file(
            db_dir / "base.py",
            self._render_template("Python/database/base.py.jinja", context)
        )
        self._write_file(
            db_dir / "models.py",
            self._render_template("Python/database/models.py.jinja", context)
        )
        self._write_file(
            db_dir / "repo.py",
            self._render_template("Python/database/repo.py.jinja", context)
        )

        # Generate service directories
        for service in state.get('services', []):
            # Get full service data from services dict
            service_name = service if isinstance(service, str) else service.get('name', service.get('id'))
            service_dir = output_dir / self._to_snake_case(service_name)
            ensure_directory(service_dir)
            (service_dir / "__init__.py").touch()

            # Service context
            service_context = {'project': state, 'service': service}

            self._write_file(
                service_dir / "service.py",
                self._render_template("Python/service/service.py.jinja", service_context)
            )
            self._write_file(
                service_dir / "schemas.py",
                self._render_template("Python/service/schemas.py.jinja", service_context)
            )
            self._write_file(
                service_dir / "routes.py",
                self._render_template("Python/service/routes.py.jinja", service_context)
            )

        # Generate auto-CRUD entity directories from an ERD (services list is separate/legacy)
        for entity in state.get('crud_entities', []):
            entity_dir = output_dir / entity['plural_snake']
            ensure_directory(entity_dir)
            (entity_dir / "__init__.py").touch()

            entity_context = {'project': state, 'entity': entity}
            self._write_file(
                entity_dir / "schemas.py",
                self._render_template("Python/service/crud_schemas.py.jinja", entity_context)
            )
            self._write_file(
                entity_dir / "routes.py",
                self._render_template("Python/service/crud_routes.py.jinja", entity_context)
            )

        # RBAC dependency (only meaningful once auth exists, enforced at the ERD validation layer)
        if state.get('rbac_enabled'):
            self._write_file(
                output_dir / "rbac.py",
                self._render_template("Python/rbac/dependency.py.jinja", context)
            )

        # Generate main application files
        self._write_file(
            output_dir / "config.py",
            self._render_template("Python/config.py.jinja", context)
        )
        self._write_file(
            output_dir / "server.py",
            self._render_template("Python/server.py.jinja", context)
        )
        self._write_file(
            output_dir / "middleware.py",
            self._render_template("Python/middleware.py.jinja", context)
        )
        self._write_file(
            output_dir / "dependencies.py",
            self._render_template("Python/dependencies.py.jinja", context)
        )
        self._write_file(
            output_dir / "requirements.txt",
            self._render_template("Python/requirements.txt.jinja", context)
        )
        self._write_file(
            output_dir / "README.md",
            self._render_template("Python/README.md.jinja", context)
        )


    def _to_snake_case(self, text: str) -> str:
        """Helper to convert to snake_case"""
        import re
        text = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', text).lower()

    def _to_camel_case(self, text: str) -> str:
        """Helper to convert to camelCase"""
        pascal = ''.join(word.capitalize() for word in text.replace('_', ' ').split())
        return pascal[0].lower() + pascal[1:] if pascal else ''

    def create_archive(self, project_name: str) -> Path:
        """
        Create ZIP archive of generated project.

        Args:
            project_name: Project name

        Returns:
            Path to created ZIP file
        """
        codebase_dir = self.output_dir / project_name / "codebase"
        if not codebase_dir.exists():
            raise FileNotFoundError(f"No generated code found for project {project_name}")

        zip_path = self.output_dir / project_name / f"{project_name}.zip"

        exclude_patterns = ['__pycache__', '.pyc', 'node_modules', '.git']
        create_zip_archive(codebase_dir, zip_path, exclude_patterns)

        return zip_path

    def sync_project(self, project_name: str, project_state: Dict[str, Any]) -> Path:
        """
        Sync generated code with updated project state.

        Args:
            project_name: Project name
            project_state: Updated project state

        Returns:
            Path to synced project directory
        """
        return self.generate_project(project_state, force=True)
