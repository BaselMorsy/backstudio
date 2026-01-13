# BackStudio MCP Server - Examples

This guide demonstrates how to use the BackStudio MCP Server to build complete FastAPI backends through natural language.

## Prerequisites

1. BackStudio API running on `http://localhost:8000`
2. MCP client configured (Claude Desktop, Cline, etc.)

## Example 1: Simple User Management API

### Step 1: Create Project
```
Use the create_project tool with:
- name: "user_api"
- description: "Simple user management API"
- framework: "fastapi"
```

**Result**: You'll get a project ID (e.g., `proj_abc123`)

### Step 2: Create User Model
```
Use create_data_model with:
- project_id: "proj_abc123"
- name: "User"
- fields:
  - name: "email", type: "str", unique: true, index: true
  - name: "username", type: "str", unique: true
  - name: "full_name", type: "str"
  - name: "is_active", type: "bool", default: true
  - name: "created_at", type: "datetime"
```

### Step 3: Create UserService
```
Use create_service with:
- project_id: "proj_abc123"
- name: "UserService"
- description: "Handles user operations"
```

**Result**: You'll get a service ID (e.g., `svc_xyz789`)

### Step 4: Create Request/Response Schemas
```
Use create_service_schema twice:

Schema 1 - UserCreate:
- project_id: "proj_abc123"
- service_id: "svc_xyz789"
- name: "UserCreate"
- fields:
  - name: "email", type: "str", required: true
  - name: "username", type: "str", required: true
  - name: "full_name", type: "str", required: true

Schema 2 - UserResponse:
- project_id: "proj_abc123"
- service_id: "svc_xyz789"
- name: "UserResponse"
- fields:
  - name: "id", type: "int", required: true
  - name: "email", type: "str", required: true
  - name: "username", type: "str", required: true
  - name: "full_name", type: "str", required: true
  - name: "is_active", type: "bool", required: true
```

### Step 5: Create Service Functions
```
Use create_service_function multiple times:

Function 1 - create_user:
- project_id: "proj_abc123"
- service_id: "svc_xyz789"
- name: "create_user"
- parameters:
  - name: "user_data", type: "UserCreate"
- return_type: "User"

Function 2 - get_user_by_id:
- project_id: "proj_abc123"
- service_id: "svc_xyz789"
- name: "get_user_by_id"
- parameters:
  - name: "user_id", type: "int"
- return_type: "Optional[User]"

Function 3 - list_users:
- project_id: "proj_abc123"
- service_id: "svc_xyz789"
- name: "list_users"
- parameters:
  - name: "skip", type: "int", required: false
  - name: "limit", type: "int", required: false
- return_type: "List[User]"
```

### Step 6: Create Endpoints
```
Use create_endpoint multiple times:

Endpoint 1 - Create User:
- project_id: "proj_abc123"
- service_id: "svc_xyz789"
- path: "/users"
- method: "POST"
- function_name: "create_user"
- summary: "Create a new user"
- request_schema: "UserCreate"
- response_schema: "UserResponse"
- status_code: 201
- tags: ["users"]

Endpoint 2 - Get User:
- project_id: "proj_abc123"
- service_id: "svc_xyz789"
- path: "/users/{user_id}"
- method: "GET"
- function_name: "get_user_by_id"
- summary: "Get user by ID"
- parameters:
  - name: "user_id", location: "path", type: "int", required: true
- response_schema: "UserResponse"
- tags: ["users"]

Endpoint 3 - List Users:
- project_id: "proj_abc123"
- service_id: "svc_xyz789"
- path: "/users"
- method: "GET"
- function_name: "list_users"
- summary: "List all users"
- parameters:
  - name: "skip", location: "query", type: "int", required: false
  - name: "limit", location: "query", type: "int", required: false
- response_schema: "List[UserResponse]"
- tags: ["users"]
```

### Step 7: Generate Code
```
Use generate_code with:
- project_id: "proj_abc123"
```

**Done!** You now have a complete FastAPI application with:
- User model with SQLAlchemy
- CRUD endpoints
- Request/response validation
- OpenAPI documentation
- Database migrations

---

## Example 2: Blog API with Authentication

This example shows how to build a blog API with authentication using provider dependencies.

### Step 1: Create Project
```
create_project:
- name: "blog_api"
- description: "Blog API with authentication"
```

### Step 2: Create Models
```
create_data_model (User):
- name: "User"
- fields:
  - name: "email", type: "str", unique: true
  - name: "hashed_password", type: "str"
  - name: "is_active", type: "bool", default: true

create_data_model (Post):
- name: "Post"
- fields:
  - name: "title", type: "str"
  - name: "content", type: "str"
  - name: "published", type: "bool", default: false
  - name: "author_id", type: "int", index: true
  - name: "created_at", type: "datetime"
```

### Step 3: Create Relationship
```
create_relationship:
- source_model_id: <Post model ID>
- target_model_name: "User"
- type: "many_to_one"
- foreign_key: "author_id"
```

### Step 4: Create Authentication Provider
```
create_dependency:
- type: "provider"
- name: "get_current_user"
- description: "Get currently authenticated user from token"
- parameters:
  - name: "token", type: "str"
- return_type: "User"
- raises_exception: true
```

**Result**: You'll get a dependency ID (e.g., `dep_auth123`)

### Step 5: Create Authorization Guard
```
create_dependency:
- type: "guard"
- name: "verify_active_user"
- description: "Verify user is active"
- parameters:
  - name: "user", type: "User"
- raises_exception: true
```

### Step 6: Create Services
```
create_service:
- name: "AuthService"

create_service:
- name: "PostService"
```

### Step 7: Create Endpoints with Provider Dependency

**Get Current User Profile** (uses provider):
```
create_endpoint:
- path: "/users/me"
- method: "GET"
- function_name: "get_current_user_profile"
- providers:
  - dependency_id: "dep_auth123"
    variable_name: "current_user"
- summary: "Get current user profile"
```

**Create Post** (uses provider):
```
create_endpoint:
- path: "/posts"
- method: "POST"
- function_name: "create_post"
- request_schema: "PostCreate"
- providers:
  - dependency_id: "dep_auth123"
    variable_name: "current_user"
- summary: "Create a new post"
- description: "Creates a post for the authenticated user"
```

The `current_user` variable will be automatically injected into your endpoint and you can use it in the service logic!

### Step 8: Generate Code
```
generate_code:
- project_id: <project_id>
```

**Result**: Complete blog API with:
- User authentication
- Protected endpoints
- Relationship between users and posts
- Automatic user injection via providers

---

## Example 3: E-commerce API

A more complex example with multiple relationships and business logic.

### Models
1. **User** - customers and admins
2. **Product** - items for sale
3. **Category** - product categories
4. **Order** - customer orders
5. **OrderItem** - individual items in an order

### Relationships
- User → Orders (one-to-many)
- Order → OrderItems (one-to-many)
- Product → OrderItems (one-to-many)
- Category → Products (one-to-many)

### Dependencies
1. **get_current_user** (provider) - authentication
2. **require_admin** (guard) - admin-only endpoints
3. **get_db_session** (provider) - database session

### Services
1. **AuthService** - login, registration
2. **ProductService** - product CRUD
3. **OrderService** - order management
4. **PaymentService** - payment processing

### Key Endpoints
- `POST /auth/register` - register new user
- `POST /auth/login` - login
- `GET /products` - list products
- `POST /products` - create product (admin only, uses guard)
- `GET /orders/my` - get current user's orders (uses provider)
- `POST /orders` - create order (uses provider for current_user)

This demonstrates the full power of BackStudio:
- Complex data models with relationships
- Role-based access control
- Provider dependencies for user context
- Guard dependencies for authorization

---

## Tips for Using the MCP Server

### 1. Always Get IDs
After creating resources, save their IDs:
- Project ID
- Service ID
- Model IDs
- Dependency IDs

You'll need these for subsequent operations.

### 2. Use list_* Tools
Before creating, use list tools to check what exists:
- `list_projects`
- `list_data_models`
- `list_services`
- `list_dependencies`

### 3. Provider vs Guard
- **Guards**: Validate/authorize (throw exceptions to block access)
  - Example: `verify_admin`, `check_permissions`
  - Applied at decorator level

- **Providers**: Inject values into endpoints
  - Example: `get_current_user`, `get_db_session`
  - Create a variable you can use in the endpoint
  - Specify `variable_name` when adding to endpoint

### 4. Test as You Build
After generating code:
1. Navigate to generated directory
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `alembic upgrade head`
4. Start server: `uvicorn main:app --reload`
5. Visit `/docs` for interactive API documentation

### 5. Iterative Development
You don't need to build everything at once:
1. Start with core models
2. Add one service
3. Add a few endpoints
4. Generate and test
5. Add more features
6. Use `sync_project` to update code

---

## Common Patterns

### Pattern 1: CRUD Endpoints
For each model, typically create:
- `POST /resource` - Create
- `GET /resource/{id}` - Read one
- `GET /resource` - Read many (with pagination)
- `PUT /resource/{id}` - Update
- `DELETE /resource/{id}` - Delete

### Pattern 2: Nested Resources
For relationships:
- `GET /users/{user_id}/posts` - Get user's posts
- `POST /orders/{order_id}/items` - Add item to order

### Pattern 3: Authentication Flow
1. Create User model
2. Create `get_current_user` provider
3. Add `providers` to protected endpoints
4. Use `current_user` variable in service logic

### Pattern 4: Search and Filter
Add query parameters:
```
parameters:
  - name: "search", location: "query", type: "str"
  - name: "category", location: "query", type: "str"
  - name: "min_price", location: "query", type: "float"
```

---

## Next Steps

1. **Read the main README.md** for installation and setup
2. **Try Example 1** to get familiar with the workflow
3. **Experiment with Example 2** to learn about dependencies
4. **Build your own API** using the patterns above

Happy coding! 🚀
