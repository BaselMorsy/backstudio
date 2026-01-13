"""Configuration schemas"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class DatabaseType(str, Enum):
    """Database types"""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    MONGODB = "mongodb"
    REDIS = "redis"


class AuthStrategy(str, Enum):
    """Authentication strategies"""
    JWT = "jwt"
    SESSION = "session"
    OAUTH2 = "oauth2"
    API_KEY = "api_key"


class DatabaseConfig(BaseModel):
    """Database configuration"""
    type: DatabaseType = Field(..., description="Database type")
    host: Optional[str] = Field(default="localhost", description="Database host")
    port: Optional[int] = Field(None, description="Database port")
    database_name: str = Field(..., description="Database name")
    username: Optional[str] = Field(None, description="Database username")
    use_env_vars: bool = Field(default=True, description="Use environment variables for credentials")
    pool_size: int = Field(default=10, description="Connection pool size")
    echo: bool = Field(default=False, description="Echo SQL queries")
    additional_config: Dict[str, Any] = Field(default_factory=dict, description="Additional database config")


class DatabaseConfigCreate(DatabaseConfig):
    """Schema for creating database configuration"""
    pass


class DatabaseConfigUpdate(BaseModel):
    """Schema for updating database configuration"""
    type: Optional[DatabaseType] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    use_env_vars: Optional[bool] = None
    pool_size: Optional[int] = None
    echo: Optional[bool] = None
    additional_config: Optional[Dict[str, Any]] = None


class FrameworkConfig(BaseModel):
    """Framework-specific configuration - Python/FastAPI only"""
    language: str = Field(default="python", description="Programming language (Python)")
    framework: str = Field(default="fastapi", description="Framework name (FastAPI)")
    version: Optional[str] = Field(None, description="FastAPI version")
    use_async: bool = Field(default=True, description="Use async/await patterns")
    enable_cors: bool = Field(default=True, description="Enable CORS")
    api_prefix: str = Field(default="/api", description="API route prefix")
    additional_config: Dict[str, Any] = Field(default_factory=dict, description="Framework-specific config")


class FrameworkConfigCreate(FrameworkConfig):
    """Schema for creating framework configuration"""
    pass


class FrameworkConfigUpdate(BaseModel):
    """Schema for updating framework configuration"""
    language: Optional[str] = None
    framework: Optional[str] = None
    version: Optional[str] = None
    use_async: Optional[bool] = None
    enable_cors: Optional[bool] = None
    api_prefix: Optional[str] = None
    additional_config: Optional[Dict[str, Any]] = None


class SecurityConfig(BaseModel):
    """Security configuration"""
    auth_strategy: AuthStrategy = Field(..., description="Authentication strategy")
    jwt_secret_env_var: Optional[str] = Field(default="JWT_SECRET", description="Environment variable for JWT secret")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiration_minutes: int = Field(default=30, description="JWT token expiration in minutes")
    enable_https: bool = Field(default=True, description="Enforce HTTPS")
    allowed_origins: list[str] = Field(default_factory=list, description="Allowed CORS origins")
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Max requests per window")
    rate_limit_window_minutes: int = Field(default=1, description="Rate limit time window in minutes")
    additional_config: Dict[str, Any] = Field(default_factory=dict, description="Additional security config")


class SecurityConfigCreate(SecurityConfig):
    """Schema for creating security configuration"""
    pass


class SecurityConfigUpdate(BaseModel):
    """Schema for updating security configuration"""
    auth_strategy: Optional[AuthStrategy] = None
    jwt_secret_env_var: Optional[str] = None
    jwt_algorithm: Optional[str] = None
    jwt_expiration_minutes: Optional[int] = None
    enable_https: Optional[bool] = None
    allowed_origins: Optional[list[str]] = None
    rate_limit_enabled: Optional[bool] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_window_minutes: Optional[int] = None
    additional_config: Optional[Dict[str, Any]] = None
