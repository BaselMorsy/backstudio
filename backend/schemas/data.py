"""Data model and relationship schemas"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class Cardinality(str, Enum):
    """Relationship cardinality types"""
    ONE_TO_MANY = "one-to-many"
    MANY_TO_ONE = "many-to-one"
    ONE_TO_ONE = "one-to-one"
    MANY_TO_MANY = "many-to-many"


class LazyStrategy(str, Enum):
    """SQLAlchemy lazy loading strategies"""
    SELECT = "select"
    JOINED = "joined"
    SELECTIN = "selectin"
    SUBQUERY = "subquery"
    RAISE = "raise"


class FieldType(str, Enum):
    """Data model field types"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    TEXT = "text"
    JSON = "json"
    UUID = "uuid"


class ForeignKeySpec(BaseModel):
    """Foreign key specification"""
    model: str = Field(..., description="Model containing the FK column")
    column: str = Field(..., description="FK column name")
    references: str = Field(..., description="Target in form Model.column")
    nullable: bool = True
    unique: bool = False
    ondelete: Optional[str] = None  # CASCADE, SET NULL, RESTRICT


class RelationshipSide(BaseModel):
    """One side of a relationship"""
    model: str
    attribute: str

    uselist: Optional[bool] = None
    lazy: Optional[LazyStrategy] = None
    order_by: Optional[str] = None
    viewonly: bool = False


class JoinCondition(BaseModel):
    """Custom join conditions for relationships"""
    primaryjoin: Optional[str] = None
    secondaryjoin: Optional[str] = None
    foreign_keys: Optional[List[str]] = None


class CascadeSpec(BaseModel):
    """Cascade behavior specification"""
    cascade: Optional[str] = None
    passive_deletes: bool = False
    passive_updates: bool = False
    enable_typechecks: bool = True


class AssociationTableSpec(BaseModel):
    """Association table for many-to-many relationships"""
    table_name: str
    left_foreign_key: ForeignKeySpec
    right_foreign_key: ForeignKeySpec


class RelationshipSpec(BaseModel):
    """Complete relationship specification"""
    id: str
    name: str

    cardinality: Cardinality

    source: RelationshipSide
    target: RelationshipSide

    foreign_key: Optional[ForeignKeySpec] = None
    association_table: Optional[AssociationTableSpec] = None

    joins: Optional[JoinCondition] = None
    behavior: Optional[CascadeSpec] = None

    @field_validator('foreign_key', 'association_table')
    @classmethod
    def validate_structure(cls, v, info):
        """Validate relationship structure based on cardinality"""
        if info.data.get('cardinality') == Cardinality.MANY_TO_MANY:
            if info.field_name == 'foreign_key' and v is not None:
                raise ValueError("many-to-many must not define foreign_key")
        else:
            if info.field_name == 'association_table' and v is not None:
                raise ValueError(f"{info.data.get('cardinality')} must not define association_table")
        return v

    class Config:
        extra = "forbid"


class ModelField(BaseModel):
    """Data model field specification"""
    name: str = Field(..., description="Field name")
    type: FieldType = Field(..., description="Field data type")
    nullable: bool = Field(default=True, description="Whether field can be null")
    unique: bool = Field(default=False, description="Whether field must be unique")
    default: Optional[Any] = Field(None, description="Default value")
    primary_key: bool = Field(default=False, description="Whether this is a primary key")
    index: bool = Field(default=False, description="Whether to create an index")
    max_length: Optional[int] = Field(None, description="Max length for string fields")


class DataModelBase(BaseModel):
    """Base schema for data models"""
    name: str = Field(..., description="Model name", min_length=1)
    table_name: Optional[str] = Field(None, description="Database table name")
    fields: List[ModelField] = Field(default_factory=list, description="Model fields")


class DataModelCreate(DataModelBase):
    """Schema for creating a data model"""
    pass


class DataModelUpdate(BaseModel):
    """Schema for updating a data model"""
    name: Optional[str] = None
    table_name: Optional[str] = None
    fields: Optional[List[ModelField]] = None


class DataModel(DataModelBase):
    """Complete data model with metadata"""
    id: str
    project_id: str
    created_at: str
    updated_at: str


class RelationshipCreate(BaseModel):
    """Schema for creating a relationship"""
    name: str
    cardinality: Cardinality
    source: RelationshipSide
    target: RelationshipSide
    foreign_key: Optional[ForeignKeySpec] = None
    association_table: Optional[AssociationTableSpec] = None
    joins: Optional[JoinCondition] = None
    behavior: Optional[CascadeSpec] = None


class RelationshipUpdate(BaseModel):
    """Schema for updating a relationship"""
    name: Optional[str] = None
    cardinality: Optional[Cardinality] = None
    source: Optional[RelationshipSide] = None
    target: Optional[RelationshipSide] = None
    foreign_key: Optional[ForeignKeySpec] = None
    association_table: Optional[AssociationTableSpec] = None
    joins: Optional[JoinCondition] = None
    behavior: Optional[CascadeSpec] = None
