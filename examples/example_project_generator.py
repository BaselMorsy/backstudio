#!/usr/bin/env python3
"""
BackStudio Example Project Generator
=====================================
This script demonstrates how to programmatically generate a complete backend
using the BackStudio API. It creates a medium-complexity e-commerce platform
with users, products, orders, and reviews.

Project: ShopHub - E-commerce Platform
Features:
- User authentication with JWT
- Product catalog with categories
- Shopping cart and order management
- Product reviews and ratings
- Admin dashboard
- Rate limiting and CORS security

Usage:
    python example_project_generator.py
"""

import requests
import json
import time
import zipfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

# Configuration
BASE_URL = "http://localhost:8000/api"
WORKSPACE_DIR = Path("./workspace")
DOWNLOAD_DIR = Path("./generated_projects")


class BackStudioClient:
    """Client for interacting with BackStudio API"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {method} {endpoint}")
            print(f"   Error: {e}")
            if hasattr(e.response, 'text'):
                print(f"   Response: {e.response.text}")
            raise

    def create_project(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new project"""
        print(f"🚀 Creating project: {name}")
        return self._make_request("POST", "/projects/", json={
            "name": name,
            "description": description
        })

    def configure_framework(self, project_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Configure framework settings"""
        print(f"⚙️  Configuring framework...")
        return self._make_request("POST", f"/projects/{project_id}/config/framework/", json=config)

    def configure_database(self, project_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Configure database settings"""
        print(f"🗄️  Configuring database...")
        return self._make_request("POST", f"/projects/{project_id}/config/database/", json=config)

    def configure_security(self, project_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Configure security settings"""
        print(f"🔒 Configuring security...")
        return self._make_request("POST", f"/projects/{project_id}/config/security/", json=config)

    def create_model(self, project_id: str, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a data model"""
        print(f"📊 Creating model: {model_data['name']}")
        return self._make_request("POST", f"/projects/{project_id}/models/", json=model_data)

    def create_relationship(self, project_id: str, model_id: str, rel_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a relationship between models"""
        print(f"🔗 Creating relationship: {rel_data['name']}")
        return self._make_request("POST", f"/projects/{project_id}/models/{model_id}/relations/", json=rel_data)

    def create_dependency(self, project_id: str, dep_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a dependency for injection"""
        print(f"💉 Creating dependency: {dep_data['name']}")
        return self._make_request("POST", f"/projects/{project_id}/dependencies/", json=dep_data)

    def create_service(self, project_id: str, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a service"""
        print(f"🔧 Creating service: {service_data['name']}")
        return self._make_request("POST", f"/projects/{project_id}/services/", json=service_data)

    def create_schema(self, project_id: str, service_id: str, schema_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a service schema (DTO)"""
        print(f"   📝 Creating schema: {schema_data['name']}")
        return self._make_request("POST", f"/projects/{project_id}/services/{service_id}/schemas/", json=schema_data)

    def create_function(self, project_id: str, service_id: str, func_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a service function"""
        print(f"   ⚡ Creating function: {func_data['name']}")
        return self._make_request("POST", f"/projects/{project_id}/services/{service_id}/functions/", json=func_data)

    def create_endpoint(self, project_id: str, service_id: str, endpoint_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a service endpoint"""
        print(f"   🌐 Creating endpoint: {endpoint_data['method']} {endpoint_data['path']}")
        return self._make_request("POST", f"/projects/{project_id}/services/{service_id}/endpoints/", json=endpoint_data)

    def generate_code(self, project_id: str, force: bool = False) -> Dict[str, Any]:
        """Generate code for the project"""
        print(f"⚡ Generating code...")
        params = {"force": "true"} if force else {}
        return self._make_request("POST", f"/projects/{project_id}/generate", params=params)

    def download_project(self, project_id: str, output_path: Path):
        """Download generated project as ZIP"""
        print(f"📦 Downloading project...")
        url = f"{self.base_url}/projects/{project_id}/download"
        response = self.session.get(url, stream=True)
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"✅ Downloaded to: {output_path}")

    def download_to_workspace(self, project_id: str, project_name: str, workspace_dir: Path):
        """Download and extract project directly to workspace directory"""
        print(f"📦 Downloading project to workspace...")

        # Ensure workspace directory exists
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Download to temp location first
        temp_zip = workspace_dir / f"{project_name}_temp.zip"
        self.download_project(project_id, temp_zip)

        # Extract to workspace subdirectory
        print(f"📂 Extracting to workspace/{project_name}...")
        project_dir = workspace_dir / project_name

        # Backup state files if they exist (created by the API)
        state_file = project_dir / "state.json"
        components_file = project_dir / "components.json"
        state_backup = None
        components_backup = None

        if state_file.exists():
            print(f"💾 Preserving state.json file...")
            state_backup = state_file.read_bytes()

        if components_file.exists():
            print(f"💾 Preserving components.json file...")
            components_backup = components_file.read_bytes()

        # Remove existing directory if it exists
        if project_dir.exists():
            print(f"⚠️  Cleaning existing directory: {project_dir}")
            shutil.rmtree(project_dir)

        # Create project directory
        project_dir.mkdir(parents=True, exist_ok=True)

        # Extract ZIP contents into project directory
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            zip_ref.extractall(project_dir)

        # Restore state files if they were backed up
        if state_backup:
            print(f"📝 Restoring state.json file...")
            state_file.write_bytes(state_backup)

        if components_backup:
            print(f"📝 Restoring components.json file...")
            components_file.write_bytes(components_backup)

        # Remove temp ZIP file
        temp_zip.unlink()

        print(f"✅ Project extracted to: {project_dir}")
        return project_dir


def build_shophub_project():
    """Build a complete e-commerce platform"""

    client = BackStudioClient()

    # Step 1: Create Project
    print("\n" + "="*60)
    print("STEP 1: Creating Project")
    print("="*60)

    project = client.create_project(
        name="ShopHub",
        description="A modern e-commerce platform with user auth, product catalog, and order management"
    )
    project_id = project["id"]
    print(f"✅ Project created: {project_id}")

    # Step 2: Configure Framework
    print("\n" + "="*60)
    print("STEP 2: Configuring Framework")
    print("="*60)

    client.configure_framework(project_id, {
        "language": "python",
        "framework": "fastapi",
        "version": "0.104.1",
        "use_async": True,
        "enable_cors": True,
        "api_prefix": "/api/v1",
        "additional_config": {
            "title": "ShopHub API",
            "version": "1.0.0",
            "docs_url": "/docs"
        }
    })

    # Step 3: Configure Database
    print("\n" + "="*60)
    print("STEP 3: Configuring Database")
    print("="*60)

    client.configure_database(project_id, {
        "type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "shophub_db",
        "username": "shophub_user",
        "use_env_vars": True,
        "pool_size": 20,
        "echo": False,
        "additional_config": {
            "pool_recycle": 3600,
            "pool_pre_ping": True
        }
    })

    # Step 4: Configure Security
    print("\n" + "="*60)
    print("STEP 4: Configuring Security")
    print("="*60)

    client.configure_security(project_id, {
        "auth_strategy": "jwt",
        "jwt_secret_env_var": "JWT_SECRET_KEY",
        "jwt_algorithm": "HS256",
        "jwt_expiration_minutes": 1440,  # 24 hours
        "enable_https": True,
        "allowed_origins": [
            "http://localhost:3000",
            "http://localhost:3001",
            "https://shophub.example.com"
        ],
        "rate_limit_enabled": True,
        "rate_limit_requests": 100,
        "rate_limit_window_minutes": 1,
        "additional_config": {
            "password_min_length": 8,
            "require_email_verification": True
        }
    })

    # Step 5: Create Data Models
    print("\n" + "="*60)
    print("STEP 5: Creating Data Models")
    print("="*60)

    # User Model
    user_model = client.create_model(project_id, {
        "name": "User",
        "table_name": "users",
        "fields": [
            {"name": "id", "type": "integer", "primary_key": True, "nullable": False},
            {"name": "email", "type": "string", "nullable": False, "unique": True, "max_length": 255},
            {"name": "username", "type": "string", "nullable": False, "unique": True, "max_length": 50},
            {"name": "password_hash", "type": "string", "nullable": False, "max_length": 255},
            {"name": "first_name", "type": "string", "nullable": True, "max_length": 100},
            {"name": "last_name", "type": "string", "nullable": True, "max_length": 100},
            {"name": "is_active", "type": "boolean", "nullable": False, "default": True},
            {"name": "is_admin", "type": "boolean", "nullable": False, "default": False},
            {"name": "created_at", "type": "datetime", "nullable": False},
            {"name": "updated_at", "type": "datetime", "nullable": False}
        ]
    })

    # Category Model
    category_model = client.create_model(project_id, {
        "name": "Category",
        "table_name": "categories",
        "fields": [
            {"name": "id", "type": "integer", "primary_key": True, "nullable": False},
            {"name": "name", "type": "string", "nullable": False, "unique": True, "max_length": 100},
            {"name": "description", "type": "text", "nullable": True},
            {"name": "slug", "type": "string", "nullable": False, "unique": True, "max_length": 100},
            {"name": "created_at", "type": "datetime", "nullable": False}
        ]
    })

    # Product Model
    product_model = client.create_model(project_id, {
        "name": "Product",
        "table_name": "products",
        "fields": [
            {"name": "id", "type": "integer", "primary_key": True, "nullable": False},
            {"name": "name", "type": "string", "nullable": False, "max_length": 200},
            {"name": "description", "type": "text", "nullable": True},
            {"name": "price", "type": "float", "nullable": False},
            {"name": "stock_quantity", "type": "integer", "nullable": False, "default": 0},
            {"name": "sku", "type": "string", "nullable": False, "unique": True, "max_length": 50},
            {"name": "category_id", "type": "integer", "nullable": False},
            {"name": "image_url", "type": "string", "nullable": True, "max_length": 500},
            {"name": "is_active", "type": "boolean", "nullable": False, "default": True},
            {"name": "created_at", "type": "datetime", "nullable": False},
            {"name": "updated_at", "type": "datetime", "nullable": False}
        ]
    })

    # Order Model
    order_model = client.create_model(project_id, {
        "name": "Order",
        "table_name": "orders",
        "fields": [
            {"name": "id", "type": "integer", "primary_key": True, "nullable": False},
            {"name": "user_id", "type": "integer", "nullable": False},
            {"name": "order_number", "type": "string", "nullable": False, "unique": True, "max_length": 50},
            {"name": "status", "type": "string", "nullable": False, "max_length": 50, "default": "pending"},
            {"name": "total_amount", "type": "float", "nullable": False},
            {"name": "shipping_address", "type": "text", "nullable": False},
            {"name": "created_at", "type": "datetime", "nullable": False},
            {"name": "updated_at", "type": "datetime", "nullable": False}
        ]
    })

    # OrderItem Model
    order_item_model = client.create_model(project_id, {
        "name": "OrderItem",
        "table_name": "order_items",
        "fields": [
            {"name": "id", "type": "integer", "primary_key": True, "nullable": False},
            {"name": "order_id", "type": "integer", "nullable": False},
            {"name": "product_id", "type": "integer", "nullable": False},
            {"name": "quantity", "type": "integer", "nullable": False},
            {"name": "unit_price", "type": "float", "nullable": False},
            {"name": "subtotal", "type": "float", "nullable": False}
        ]
    })

    # Review Model
    review_model = client.create_model(project_id, {
        "name": "Review",
        "table_name": "reviews",
        "fields": [
            {"name": "id", "type": "integer", "primary_key": True, "nullable": False},
            {"name": "user_id", "type": "integer", "nullable": False},
            {"name": "product_id", "type": "integer", "nullable": False},
            {"name": "rating", "type": "integer", "nullable": False},
            {"name": "comment", "type": "text", "nullable": True},
            {"name": "created_at", "type": "datetime", "nullable": False}
        ]
    })

    # Step 6: Create Relationships
    print("\n" + "="*60)
    print("STEP 6: Creating Relationships")
    print("="*60)

    # Category -> Products (one-to-many)
    client.create_relationship(project_id, category_model["id"], {
        "name": "category_products",
        "cardinality": "one-to-many",
        "source": {
            "model": "Category",
            "attribute": "products",
            "lazy": "select"
        },
        "target": {
            "model": "Product",
            "attribute": "category"
        },
        "foreign_key": {
            "model": "Product",
            "column": "category_id",
            "references": "categories.id",
            "nullable": False,
            "ondelete": "CASCADE"
        },
        "behavior": {
            "cascade": "all, delete-orphan",
            "passive_deletes": False
        }
    })

    # User -> Orders (one-to-many)
    client.create_relationship(project_id, user_model["id"], {
        "name": "user_orders",
        "cardinality": "one-to-many",
        "source": {
            "model": "User",
            "attribute": "orders",
            "lazy": "select"
        },
        "target": {
            "model": "Order",
            "attribute": "user"
        },
        "foreign_key": {
            "model": "Order",
            "column": "user_id",
            "references": "users.id",
            "nullable": False,
            "ondelete": "CASCADE"
        },
        "behavior": {
            "cascade": "all, delete-orphan",
            "passive_deletes": False
        }
    })

    # Order -> OrderItems (one-to-many)
    client.create_relationship(project_id, order_model["id"], {
        "name": "order_items",
        "cardinality": "one-to-many",
        "source": {
            "model": "Order",
            "attribute": "items",
            "lazy": "select"
        },
        "target": {
            "model": "OrderItem",
            "attribute": "order"
        },
        "foreign_key": {
            "model": "OrderItem",
            "column": "order_id",
            "references": "orders.id",
            "nullable": False,
            "ondelete": "CASCADE"
        },
        "behavior": {
            "cascade": "all, delete-orphan",
            "passive_deletes": False
        }
    })

    # Product -> OrderItems (one-to-many)
    client.create_relationship(project_id, product_model["id"], {
        "name": "product_order_items",
        "cardinality": "one-to-many",
        "source": {
            "model": "Product",
            "attribute": "order_items",
            "lazy": "select"
        },
        "target": {
            "model": "OrderItem",
            "attribute": "product"
        },
        "foreign_key": {
            "model": "OrderItem",
            "column": "product_id",
            "references": "products.id",
            "nullable": False,
            "ondelete": "RESTRICT"
        },
        "behavior": {
            "cascade": "all",
            "passive_deletes": False
        }
    })

    # Product -> Reviews (one-to-many)
    client.create_relationship(project_id, product_model["id"], {
        "name": "product_reviews",
        "cardinality": "one-to-many",
        "source": {
            "model": "Product",
            "attribute": "reviews",
            "lazy": "select"
        },
        "target": {
            "model": "Review",
            "attribute": "product"
        },
        "foreign_key": {
            "model": "Review",
            "column": "product_id",
            "references": "products.id",
            "nullable": False,
            "ondelete": "CASCADE"
        },
        "behavior": {
            "cascade": "all, delete-orphan",
            "passive_deletes": False
        }
    })

    # User -> Reviews (one-to-many)
    client.create_relationship(project_id, user_model["id"], {
        "name": "user_reviews",
        "cardinality": "one-to-many",
        "source": {
            "model": "User",
            "attribute": "reviews",
            "lazy": "select"
        },
        "target": {
            "model": "Review",
            "attribute": "user"
        },
        "foreign_key": {
            "model": "Review",
            "column": "user_id",
            "references": "users.id",
            "nullable": False,
            "ondelete": "CASCADE"
        },
        "behavior": {
            "cascade": "all, delete-orphan",
            "passive_deletes": False
        }
    })

    # Step 7: Create Dependencies
    print("\n" + "="*60)
    print("STEP 7: Creating Dependencies")
    print("="*60)

    # JWT Token Verification Guard
    verify_token_dep = client.create_dependency(project_id, {
        "name": "verify_token",
        "type": "guard",
        "description": "Verify JWT token from Authorization header",
        "scope": "request",
        "function_name": "verify_jwt_token",
        "return_type": "dict",
        "parameters": [
            {"name": "authorization", "type": "str", "required": True}
        ],
        "is_async": True
    })

    # Current User Provider
    current_user_dep = client.create_dependency(project_id, {
        "name": "get_current_user",
        "type": "provider",
        "description": "Get authenticated user from JWT token",
        "scope": "request",
        "function_name": "get_current_user",
        "return_type": "User",
        "parameters": [
            {"name": "token", "type": "str", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "is_async": True
    })

    # Admin Guard
    admin_guard_dep = client.create_dependency(project_id, {
        "name": "require_admin",
        "type": "guard",
        "description": "Ensure user has admin privileges",
        "scope": "request",
        "function_name": "require_admin",
        "return_type": "bool",
        "parameters": [
            {"name": "current_user", "type": "User", "required": True}
        ],
        "is_async": True
    })

    # Step 8: Create Services with Schemas, Functions, and Endpoints
    print("\n" + "="*60)
    print("STEP 8: Creating Services")
    print("="*60)

    # ==================== AUTH SERVICE ====================
    auth_service = client.create_service(project_id, {
        "name": "AuthService",
        "description": "User authentication and authorization",
        "scope": "singleton"
    })
    auth_service_id = auth_service["id"]

    # Auth Schemas
    client.create_schema(project_id, auth_service_id, {
        "name": "UserRegister",
        "description": "User registration request",
        "fields": [
            {"name": "email", "type": "str", "required": True, "validation": {"max_length": 255}},
            {"name": "username", "type": "str", "required": True, "validation": {"max_length": 50}},
            {"name": "password", "type": "str", "required": True, "validation": {"min_length": 8}},
            {"name": "first_name", "type": "str", "required": False, "validation": {"max_length": 100}},
            {"name": "last_name", "type": "str", "required": False, "validation": {"max_length": 100}}
        ]
    })

    client.create_schema(project_id, auth_service_id, {
        "name": "UserLogin",
        "description": "User login request",
        "fields": [
            {"name": "email", "type": "str", "required": True},
            {"name": "password", "type": "str", "required": True}
        ]
    })

    client.create_schema(project_id, auth_service_id, {
        "name": "TokenResponse",
        "description": "JWT token response",
        "fields": [
            {"name": "access_token", "type": "str", "required": True},
            {"name": "token_type", "type": "str", "required": True, "default": "bearer"},
            {"name": "expires_in", "type": "int", "required": True}
        ]
    })

    client.create_schema(project_id, auth_service_id, {
        "name": "UserResponse",
        "description": "User data response",
        "fields": [
            {"name": "id", "type": "int", "required": True},
            {"name": "email", "type": "str", "required": True},
            {"name": "username", "type": "str", "required": True},
            {"name": "first_name", "type": "str", "required": False},
            {"name": "last_name", "type": "str", "required": False},
            {"name": "is_active", "type": "bool", "required": True},
            {"name": "is_admin", "type": "bool", "required": True}
        ]
    })

    # Auth Functions
    register_func = client.create_function(project_id, auth_service_id, {
        "name": "register_user",
        "description": "Register a new user account",
        "parameters": [
            {"name": "user_data", "type": "UserRegister", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "User",
        "is_async": True
    })

    login_func = client.create_function(project_id, auth_service_id, {
        "name": "login_user",
        "description": "Authenticate user and return JWT token",
        "parameters": [
            {"name": "credentials", "type": "UserLogin", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "TokenResponse",
        "is_async": True
    })

    get_profile_func = client.create_function(project_id, auth_service_id, {
        "name": "get_user_profile",
        "description": "Get current user profile",
        "parameters": [
            {"name": "user_id", "type": "int", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "UserResponse",
        "is_async": True
    })

    # Auth Endpoints
    client.create_endpoint(project_id, auth_service_id, {
        "path": "/auth/register",
        "method": "POST",
        "function_name": "register_user",
        "summary": "Register new user",
        "description": "Create a new user account",
        "tags": ["authentication"],
        "parameters": [
            {"name": "user_data", "location": "body", "type": "UserRegister", "required": True}
        ],
        "request_schema": "UserRegister",
        "response_schema": "UserResponse",
        "status_code": 201
    })

    client.create_endpoint(project_id, auth_service_id, {
        "path": "/auth/login",
        "method": "POST",
        "function_name": "login_user",
        "summary": "Login user",
        "description": "Authenticate user and receive JWT token",
        "tags": ["authentication"],
        "parameters": [
            {"name": "credentials", "location": "body", "type": "UserLogin", "required": True}
        ],
        "request_schema": "UserLogin",
        "response_schema": "TokenResponse",
        "status_code": 200
    })

    client.create_endpoint(project_id, auth_service_id, {
        "path": "/auth/me",
        "method": "GET",
        "function_name": "get_user_profile",
        "summary": "Get current user profile",
        "description": "Retrieve authenticated user's profile",
        "tags": ["authentication"],
        "response_schema": "UserResponse",
        "status_code": 200,
        "middlewares": [verify_token_dep["id"]],
        "dependencies": [current_user_dep["id"]]
    })

    # ==================== PRODUCT SERVICE ====================
    product_service = client.create_service(project_id, {
        "name": "ProductService",
        "description": "Product catalog management",
        "scope": "singleton"
    })
    product_service_id = product_service["id"]

    # Product Schemas
    client.create_schema(project_id, product_service_id, {
        "name": "ProductCreate",
        "description": "Create product request",
        "fields": [
            {"name": "name", "type": "str", "required": True, "validation": {"max_length": 200}},
            {"name": "description", "type": "str", "required": False},
            {"name": "price", "type": "float", "required": True},
            {"name": "stock_quantity", "type": "int", "required": True},
            {"name": "sku", "type": "str", "required": True, "validation": {"max_length": 50}},
            {"name": "category_id", "type": "int", "required": True},
            {"name": "image_url", "type": "str", "required": False}
        ]
    })

    client.create_schema(project_id, product_service_id, {
        "name": "ProductUpdate",
        "description": "Update product request",
        "fields": [
            {"name": "name", "type": "str", "required": False},
            {"name": "description", "type": "str", "required": False},
            {"name": "price", "type": "float", "required": False},
            {"name": "stock_quantity", "type": "int", "required": False},
            {"name": "category_id", "type": "int", "required": False},
            {"name": "image_url", "type": "str", "required": False},
            {"name": "is_active", "type": "bool", "required": False}
        ]
    })

    client.create_schema(project_id, product_service_id, {
        "name": "ProductResponse",
        "description": "Product data response",
        "fields": [
            {"name": "id", "type": "int", "required": True},
            {"name": "name", "type": "str", "required": True},
            {"name": "description", "type": "str", "required": False},
            {"name": "price", "type": "float", "required": True},
            {"name": "stock_quantity", "type": "int", "required": True},
            {"name": "sku", "type": "str", "required": True},
            {"name": "category_id", "type": "int", "required": True},
            {"name": "image_url", "type": "str", "required": False},
            {"name": "is_active", "type": "bool", "required": True},
            {"name": "created_at", "type": "str", "required": True}
        ]
    })

    client.create_schema(project_id, product_service_id, {
        "name": "ProductListResponse",
        "description": "Paginated product list",
        "fields": [
            {"name": "items", "type": "List[ProductResponse]", "required": True},
            {"name": "total", "type": "int", "required": True},
            {"name": "page", "type": "int", "required": True},
            {"name": "size", "type": "int", "required": True}
        ]
    })

    # Product Functions
    client.create_function(project_id, product_service_id, {
        "name": "create_product",
        "description": "Create a new product (admin only)",
        "parameters": [
            {"name": "product_data", "type": "ProductCreate", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "ProductResponse",
        "is_async": True
    })

    client.create_function(project_id, product_service_id, {
        "name": "list_products",
        "description": "List products with pagination and filters",
        "parameters": [
            {"name": "category_id", "type": "int", "required": False},
            {"name": "search", "type": "str", "required": False},
            {"name": "page", "type": "int", "required": False, "default": 1},
            {"name": "size", "type": "int", "required": False, "default": 20},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "ProductListResponse",
        "is_async": True
    })

    client.create_function(project_id, product_service_id, {
        "name": "get_product",
        "description": "Get product by ID",
        "parameters": [
            {"name": "product_id", "type": "int", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "ProductResponse",
        "is_async": True
    })

    client.create_function(project_id, product_service_id, {
        "name": "update_product",
        "description": "Update product (admin only)",
        "parameters": [
            {"name": "product_id", "type": "int", "required": True},
            {"name": "product_data", "type": "ProductUpdate", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "ProductResponse",
        "is_async": True
    })

    client.create_function(project_id, product_service_id, {
        "name": "delete_product",
        "description": "Delete product (admin only)",
        "parameters": [
            {"name": "product_id", "type": "int", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "bool",
        "is_async": True
    })

    # Product Endpoints
    client.create_endpoint(project_id, product_service_id, {
        "path": "/products",
        "method": "POST",
        "function_name": "create_product",
        "summary": "Create product",
        "description": "Create a new product (requires admin privileges)",
        "tags": ["products"],
        "parameters": [
            {"name": "product_data", "location": "body", "type": "ProductCreate", "required": True}
        ],
        "request_schema": "ProductCreate",
        "response_schema": "ProductResponse",
        "status_code": 201,
        "middlewares": [verify_token_dep["id"]],
        "dependencies": [admin_guard_dep["id"]]
    })

    client.create_endpoint(project_id, product_service_id, {
        "path": "/products",
        "method": "GET",
        "function_name": "list_products",
        "summary": "List products",
        "description": "Get paginated list of products with optional filters",
        "tags": ["products"],
        "parameters": [
            {"name": "category_id", "location": "query", "type": "int", "required": False},
            {"name": "search", "location": "query", "type": "str", "required": False},
            {"name": "page", "location": "query", "type": "int", "required": False},
            {"name": "size", "location": "query", "type": "int", "required": False}
        ],
        "response_schema": "ProductListResponse",
        "status_code": 200
    })

    client.create_endpoint(project_id, product_service_id, {
        "path": "/products/{product_id}",
        "method": "GET",
        "function_name": "get_product",
        "summary": "Get product",
        "description": "Get product details by ID",
        "tags": ["products"],
        "parameters": [
            {"name": "product_id", "location": "path", "type": "int", "required": True}
        ],
        "response_schema": "ProductResponse",
        "status_code": 200
    })

    client.create_endpoint(project_id, product_service_id, {
        "path": "/products/{product_id}",
        "method": "PUT",
        "function_name": "update_product",
        "summary": "Update product",
        "description": "Update product details (requires admin privileges)",
        "tags": ["products"],
        "parameters": [
            {"name": "product_id", "location": "path", "type": "int", "required": True},
            {"name": "product_data", "location": "body", "type": "ProductUpdate", "required": True}
        ],
        "request_schema": "ProductUpdate",
        "response_schema": "ProductResponse",
        "status_code": 200,
        "middlewares": [verify_token_dep["id"]],
        "dependencies": [admin_guard_dep["id"]]
    })

    client.create_endpoint(project_id, product_service_id, {
        "path": "/products/{product_id}",
        "method": "DELETE",
        "function_name": "delete_product",
        "summary": "Delete product",
        "description": "Delete product (requires admin privileges)",
        "tags": ["products"],
        "parameters": [
            {"name": "product_id", "location": "path", "type": "int", "required": True}
        ],
        "status_code": 204,
        "middlewares": [verify_token_dep["id"]],
        "dependencies": [admin_guard_dep["id"]]
    })

    # ==================== ORDER SERVICE ====================
    order_service = client.create_service(project_id, {
        "name": "OrderService",
        "description": "Order and cart management",
        "scope": "singleton"
    })
    order_service_id = order_service["id"]

    # Order Schemas
    client.create_schema(project_id, order_service_id, {
        "name": "OrderItemCreate",
        "description": "Order item for creation",
        "fields": [
            {"name": "product_id", "type": "int", "required": True},
            {"name": "quantity", "type": "int", "required": True}
        ]
    })

    client.create_schema(project_id, order_service_id, {
        "name": "OrderCreate",
        "description": "Create order request",
        "fields": [
            {"name": "items", "type": "List[OrderItemCreate]", "required": True},
            {"name": "shipping_address", "type": "str", "required": True}
        ]
    })

    client.create_schema(project_id, order_service_id, {
        "name": "OrderItemResponse",
        "description": "Order item response",
        "fields": [
            {"name": "id", "type": "int", "required": True},
            {"name": "product_id", "type": "int", "required": True},
            {"name": "quantity", "type": "int", "required": True},
            {"name": "unit_price", "type": "float", "required": True},
            {"name": "subtotal", "type": "float", "required": True}
        ]
    })

    client.create_schema(project_id, order_service_id, {
        "name": "OrderResponse",
        "description": "Order response",
        "fields": [
            {"name": "id", "type": "int", "required": True},
            {"name": "order_number", "type": "str", "required": True},
            {"name": "status", "type": "str", "required": True},
            {"name": "total_amount", "type": "float", "required": True},
            {"name": "shipping_address", "type": "str", "required": True},
            {"name": "items", "type": "List[OrderItemResponse]", "required": True},
            {"name": "created_at", "type": "str", "required": True}
        ]
    })

    # Order Functions
    client.create_function(project_id, order_service_id, {
        "name": "create_order",
        "description": "Create a new order from cart items",
        "parameters": [
            {"name": "order_data", "type": "OrderCreate", "required": True},
            {"name": "user_id", "type": "int", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "OrderResponse",
        "is_async": True
    })

    client.create_function(project_id, order_service_id, {
        "name": "get_user_orders",
        "description": "Get all orders for current user",
        "parameters": [
            {"name": "user_id", "type": "int", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "List[OrderResponse]",
        "is_async": True
    })

    client.create_function(project_id, order_service_id, {
        "name": "get_order",
        "description": "Get order by ID",
        "parameters": [
            {"name": "order_id", "type": "int", "required": True},
            {"name": "user_id", "type": "int", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "OrderResponse",
        "is_async": True
    })

    client.create_function(project_id, order_service_id, {
        "name": "update_order_status",
        "description": "Update order status (admin only)",
        "parameters": [
            {"name": "order_id", "type": "int", "required": True},
            {"name": "status", "type": "str", "required": True},
            {"name": "db", "type": "Session", "required": True}
        ],
        "return_type": "OrderResponse",
        "is_async": True
    })

    # Order Endpoints
    client.create_endpoint(project_id, order_service_id, {
        "path": "/orders",
        "method": "POST",
        "function_name": "create_order",
        "summary": "Create order",
        "description": "Create a new order from cart items",
        "tags": ["orders"],
        "parameters": [
            {"name": "order_data", "location": "body", "type": "OrderCreate", "required": True}
        ],
        "request_schema": "OrderCreate",
        "response_schema": "OrderResponse",
        "status_code": 201,
        "middlewares": [verify_token_dep["id"]],
        "dependencies": [current_user_dep["id"]]
    })

    client.create_endpoint(project_id, order_service_id, {
        "path": "/orders",
        "method": "GET",
        "function_name": "get_user_orders",
        "summary": "Get user orders",
        "description": "Get all orders for authenticated user",
        "tags": ["orders"],
        "response_schema": "List[OrderResponse]",
        "status_code": 200,
        "middlewares": [verify_token_dep["id"]],
        "dependencies": [current_user_dep["id"]]
    })

    client.create_endpoint(project_id, order_service_id, {
        "path": "/orders/{order_id}",
        "method": "GET",
        "function_name": "get_order",
        "summary": "Get order",
        "description": "Get order details by ID",
        "tags": ["orders"],
        "parameters": [
            {"name": "order_id", "location": "path", "type": "int", "required": True}
        ],
        "response_schema": "OrderResponse",
        "status_code": 200,
        "middlewares": [verify_token_dep["id"]],
        "dependencies": [current_user_dep["id"]]
    })

    client.create_endpoint(project_id, order_service_id, {
        "path": "/orders/{order_id}/status",
        "method": "PATCH",
        "function_name": "update_order_status",
        "summary": "Update order status",
        "description": "Update order status (admin only)",
        "tags": ["orders"],
        "parameters": [
            {"name": "order_id", "location": "path", "type": "int", "required": True},
            {"name": "status", "location": "body", "type": "str", "required": True}
        ],
        "response_schema": "OrderResponse",
        "status_code": 200,
        "middlewares": [verify_token_dep["id"]],
        "dependencies": [admin_guard_dep["id"]]
    })

    # Step 9: Generate Code
    print("\n" + "="*60)
    print("STEP 9: Generating Code")
    print("="*60)

    result = client.generate_code(project_id, force=True)
    print(f"✅ Code generated successfully!")
    print(f"   Files created: {result.get('files_created', 'N/A')}")
    print(f"   Checksum: {result.get('checksum', 'N/A')[:16]}...")

    # Step 10: Download Project to Workspace
    print("\n" + "="*60)
    print("STEP 10: Downloading Project to Workspace")
    print("="*60)

    project_dir = client.download_to_workspace(project_id, "ShopHub", WORKSPACE_DIR)

    # Final Summary
    print("\n" + "="*60)
    print("✅ PROJECT GENERATION COMPLETE!")
    print("="*60)
    print(f"\nProject Name: ShopHub")
    print(f"Project ID: {project_id}")
    print(f"Location: {project_dir}")
    print(f"\nProject Statistics:")
    print(f"  - Data Models: 6 (User, Category, Product, Order, OrderItem, Review)")
    print(f"  - Relationships: 6 (one-to-many)")
    print(f"  - Services: 3 (Auth, Product, Order)")
    print(f"  - Endpoints: 14 REST API endpoints")
    print(f"  - Dependencies: 3 (JWT auth, current user, admin guard)")
    print(f"\nNext Steps:")
    print(f"  1. Navigate to project: cd {project_dir}")
    print(f"  2. Install dependencies: pip install -r requirements.txt")
    print(f"  3. Set environment variables (DATABASE_URL, JWT_SECRET_KEY)")
    print(f"  4. Run migrations: alembic upgrade head")
    print(f"  5. Start server: python server.py")
    print(f"  6. Visit API docs: http://localhost:8000/docs")
    print("\n" + "="*60)


if __name__ == "__main__":
    try:
        build_shophub_project()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
