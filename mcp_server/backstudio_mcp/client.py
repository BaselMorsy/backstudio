"""HTTP client for BackStudio API."""

import os
from typing import Dict, Any, List, Optional
import httpx


class BackStudioClient:
    """Client for interacting with BackStudio API."""

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize BackStudio client.

        Args:
            base_url: Base URL for BackStudio API (default: http://localhost:8000)
        """
        self.base_url = base_url or os.getenv("BACKSTUDIO_API_URL", "http://localhost:8000")
        self.api_url = f"{self.base_url}/api"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    # ==================== Projects ====================

    async def create_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new project."""
        response = await self.client.post(f"{self.api_url}/projects/", json=data)
        response.raise_for_status()
        return response.json()

    async def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects."""
        response = await self.client.get(f"{self.api_url}/projects/")
        response.raise_for_status()
        return response.json()

    async def get_project(self, project_id: str) -> Dict[str, Any]:
        """Get project details."""
        response = await self.client.get(f"{self.api_url}/projects/{project_id}/")
        response.raise_for_status()
        return response.json()

    async def update_project(self, project_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update project."""
        response = await self.client.put(f"{self.api_url}/projects/{project_id}/", json=data)
        response.raise_for_status()
        return response.json()

    async def delete_project(self, project_id: str) -> None:
        """Delete project."""
        response = await self.client.delete(f"{self.api_url}/projects/{project_id}/")
        response.raise_for_status()

    async def get_project_state(self, project_id: str) -> Dict[str, Any]:
        """Get project state JSON."""
        response = await self.client.get(f"{self.api_url}/projects/{project_id}/state")
        response.raise_for_status()
        return response.json()

    # ==================== Data Models ====================

    async def create_data_model(self, project_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a data model."""
        response = await self.client.post(f"{self.api_url}/projects/{project_id}/models/", json=data)
        response.raise_for_status()
        return response.json()

    async def list_data_models(self, project_id: str) -> List[Dict[str, Any]]:
        """List all data models."""
        response = await self.client.get(f"{self.api_url}/projects/{project_id}/models/")
        response.raise_for_status()
        return response.json()

    async def get_data_model(self, project_id: str, model_id: str) -> Dict[str, Any]:
        """Get data model details."""
        response = await self.client.get(f"{self.api_url}/projects/{project_id}/models/{model_id}/")
        response.raise_for_status()
        return response.json()

    async def update_data_model(self, project_id: str, model_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update data model."""
        response = await self.client.put(f"{self.api_url}/projects/{project_id}/models/{model_id}/", json=data)
        response.raise_for_status()
        return response.json()

    async def delete_data_model(self, project_id: str, model_id: str) -> None:
        """Delete data model."""
        response = await self.client.delete(f"{self.api_url}/projects/{project_id}/models/{model_id}/")
        response.raise_for_status()

    # ==================== Relationships ====================

    async def create_relationship(self, project_id: str, model_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a relationship between models."""
        response = await self.client.post(
            f"{self.api_url}/projects/{project_id}/models/{model_id}/relations/",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def list_relationships(self, project_id: str, model_id: str) -> List[Dict[str, Any]]:
        """List relationships for a model."""
        response = await self.client.get(
            f"{self.api_url}/projects/{project_id}/models/{model_id}/relations/"
        )
        response.raise_for_status()
        return response.json()

    # ==================== Services ====================

    async def create_service(self, project_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a service."""
        response = await self.client.post(f"{self.api_url}/projects/{project_id}/services/", json=data)
        response.raise_for_status()
        return response.json()

    async def list_services(self, project_id: str) -> List[Dict[str, Any]]:
        """List all services."""
        response = await self.client.get(f"{self.api_url}/projects/{project_id}/services/")
        response.raise_for_status()
        return response.json()

    async def get_service(self, project_id: str, service_id: str) -> Dict[str, Any]:
        """Get service details."""
        response = await self.client.get(f"{self.api_url}/projects/{project_id}/services/{service_id}/")
        response.raise_for_status()
        return response.json()

    async def update_service(self, project_id: str, service_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update service."""
        response = await self.client.put(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def delete_service(self, project_id: str, service_id: str) -> None:
        """Delete service."""
        response = await self.client.delete(f"{self.api_url}/projects/{project_id}/services/{service_id}/")
        response.raise_for_status()

    # ==================== Service Schemas ====================

    async def create_service_schema(self, project_id: str, service_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a service schema (DTO)."""
        response = await self.client.post(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/schemas/",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def list_service_schemas(self, project_id: str, service_id: str) -> List[Dict[str, Any]]:
        """List service schemas."""
        response = await self.client.get(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/schemas/"
        )
        response.raise_for_status()
        return response.json()

    # ==================== Service Functions ====================

    async def create_service_function(self, project_id: str, service_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a service function."""
        response = await self.client.post(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/functions/",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def list_service_functions(self, project_id: str, service_id: str) -> List[Dict[str, Any]]:
        """List service functions."""
        response = await self.client.get(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/functions/"
        )
        response.raise_for_status()
        return response.json()

    # ==================== Endpoints ====================

    async def create_endpoint(self, project_id: str, service_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an API endpoint."""
        response = await self.client.post(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/endpoints/",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def list_endpoints(self, project_id: str, service_id: str) -> List[Dict[str, Any]]:
        """List service endpoints."""
        response = await self.client.get(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/endpoints/"
        )
        response.raise_for_status()
        return response.json()

    async def get_endpoint(self, project_id: str, service_id: str, endpoint_id: str) -> Dict[str, Any]:
        """Get endpoint details."""
        response = await self.client.get(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/endpoints/{endpoint_id}/"
        )
        response.raise_for_status()
        return response.json()

    async def update_endpoint(self, project_id: str, service_id: str, endpoint_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update endpoint."""
        response = await self.client.put(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/endpoints/{endpoint_id}/",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def delete_endpoint(self, project_id: str, service_id: str, endpoint_id: str) -> None:
        """Delete endpoint."""
        response = await self.client.delete(
            f"{self.api_url}/projects/{project_id}/services/{service_id}/endpoints/{endpoint_id}/"
        )
        response.raise_for_status()

    # ==================== Dependencies ====================

    async def create_dependency(self, project_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a dependency (guard or provider)."""
        response = await self.client.post(
            f"{self.api_url}/projects/{project_id}/dependencies/",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def list_dependencies(self, project_id: str) -> List[Dict[str, Any]]:
        """List all dependencies."""
        response = await self.client.get(f"{self.api_url}/projects/{project_id}/dependencies/")
        response.raise_for_status()
        return response.json()

    async def get_dependency(self, project_id: str, dependency_id: str) -> Dict[str, Any]:
        """Get dependency details."""
        response = await self.client.get(
            f"{self.api_url}/projects/{project_id}/dependencies/{dependency_id}/"
        )
        response.raise_for_status()
        return response.json()

    async def update_dependency(self, project_id: str, dependency_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update dependency."""
        response = await self.client.put(
            f"{self.api_url}/projects/{project_id}/dependencies/{dependency_id}/",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def delete_dependency(self, project_id: str, dependency_id: str) -> None:
        """Delete dependency."""
        response = await self.client.delete(
            f"{self.api_url}/projects/{project_id}/dependencies/{dependency_id}/"
        )
        response.raise_for_status()

    # ==================== Code Generation ====================

    async def generate_code(self, project_id: str, force: bool = False) -> Dict[str, Any]:
        """Generate code for the project."""
        response = await self.client.post(
            f"{self.api_url}/projects/{project_id}/generate",
            params={"force": force}
        )
        response.raise_for_status()
        return response.json()

    async def sync_project(self, project_id: str) -> Dict[str, Any]:
        """Sync project code with current state."""
        response = await self.client.post(f"{self.api_url}/projects/{project_id}/sync")
        response.raise_for_status()
        return response.json()

    async def download_project(self, project_id: str) -> bytes:
        """Download project as ZIP."""
        response = await self.client.get(f"{self.api_url}/projects/{project_id}/download")
        response.raise_for_status()
        return response.content
