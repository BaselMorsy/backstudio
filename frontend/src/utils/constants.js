// Framework configurations - Python backend only
export const FRAMEWORKS = [
  {
    id: 'fastapi',
    name: 'FastAPI',
    language: 'Python',
    icon: '🐍',
    color: 'bg-green-500',
  },
];

// Field types for data models (database types)
export const DB_FIELD_TYPES = [
  'string',
  'integer',
  'float',
  'boolean',
  'datetime',
  'date',
  'text',
  'json',
  'uuid',
];

// Python primitive types for schemas
export const PYTHON_TYPES = [
  'str',
  'int',
  'float',
  'bool',
  'dict',
  'list',
  'Any',
];

// Python types for function parameters (includes Session for DB)
export const FUNCTION_PARAM_TYPES = [
  'str',
  'int',
  'float',
  'bool',
  'dict',
  'list',
  'Any',
  'Session',
];

// Cardinality types for relationships
export const CARDINALITY_TYPES = [
  { value: 'one-to-many', label: 'One-to-Many' },
  { value: 'many-to-one', label: 'Many-to-One' },
  { value: 'one-to-one', label: 'One-to-One' },
  { value: 'many-to-many', label: 'Many-to-Many' },
];

// Lazy loading strategies
export const LAZY_STRATEGIES = [
  'select',
  'joined',
  'selectin',
  'subquery',
  'raise',
];

// HTTP Methods
export const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

// Parameter locations
export const PARAM_LOCATIONS = ['path', 'query', 'body', 'header'];

// Middleware types
export const MIDDLEWARE_TYPES = [
  'authentication',
  'authorization',
  'cors',
  'rate_limiting',
  'logging',
  'compression',
  'custom',
];

// Dependency types
export const DEPENDENCY_TYPES = [
  { value: 'guard', label: 'Guard' },
  { value: 'provider', label: 'Provider' },
];

// Dependency scopes
export const DEPENDENCY_SCOPES = [
  { value: 'singleton', label: 'Singleton' },
  { value: 'request', label: 'Request' },
  { value: 'transient', label: 'Transient' },
];

// Database types
export const DATABASE_TYPES = [
  'postgresql',
  'mysql',
  'sqlite',
];

// Framework-specific database compatibility
export const FRAMEWORK_DATABASE_SUPPORT = {
  fastapi: ['postgresql', 'mysql', 'sqlite'],
};

// Auth strategies
export const AUTH_STRATEGIES = [
  'jwt',
  'session',
  'oauth2',
  'api_key',
];

// JWT algorithms
export const JWT_ALGORITHMS = ['HS256', 'HS384', 'HS512', 'RS256', 'RS384', 'RS512'];

// OnDelete options
export const ON_DELETE_OPTIONS = ['CASCADE', 'SET NULL', 'RESTRICT', 'NO ACTION'];

// Cascade behavior options for relationships
export const CASCADE_OPTIONS = [
  { value: 'save-update', label: 'Save-Update' },
  { value: 'merge', label: 'Merge' },
  { value: 'delete', label: 'Delete' },
  { value: 'delete-orphan', label: 'Delete-Orphan' },
  { value: 'all', label: 'All' },
  { value: 'all, delete-orphan', label: 'All, Delete-Orphan' },
];
