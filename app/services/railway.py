"""
Railway GraphQL API client for programmatic instance provisioning.
"""

import httpx
from app.config import get_settings


class RailwayAPIError(Exception):
    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []


class RailwayClient:
    """Async client for Railway's GraphQL API."""

    def __init__(self):
        settings = get_settings()
        self.url = settings.railway_api_url
        self.token = settings.railway_api_token
        self.workspace_id = settings.railway_workspace_id

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _execute(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query/mutation and return the data."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.url,
                json={"query": query, "variables": variables or {}},
                headers=self._headers(),
            )
            resp.raise_for_status()
            body = resp.json()

            if "errors" in body:
                msgs = [e.get("message", "Unknown error") for e in body["errors"]]
                raise RailwayAPIError(f"Railway API error: {'; '.join(msgs)}", body["errors"])

            return body.get("data", {})

    # ── Project Operations ────────────────────────────────────────────────

    async def create_project(self, name: str, description: str = "") -> dict:
        """Create a new Railway project in the workspace."""
        query = """
        mutation($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                id
                name
            }
        }
        """
        data = await self._execute(query, {
            "input": {
                "name": name,
                "description": description,
                "teamId": self.workspace_id,
            }
        })
        return data["projectCreate"]

    async def delete_project(self, project_id: str) -> bool:
        """Delete a Railway project."""
        query = """
        mutation($id: String!) {
            projectDelete(id: $id)
        }
        """
        await self._execute(query, {"id": project_id})
        return True

    # ── Environment Operations ────────────────────────────────────────────

    async def get_environments(self, project_id: str) -> list[dict]:
        """Get all environments for a project."""
        query = """
        query($projectId: String!) {
            environments(projectId: $projectId) {
                edges {
                    node {
                        id
                        name
                    }
                }
            }
        }
        """
        data = await self._execute(query, {"projectId": project_id})
        return [edge["node"] for edge in data["environments"]["edges"]]

    # ── Service Operations ────────────────────────────────────────────────

    async def create_service(self, project_id: str, name: str) -> dict:
        """Create a new service in a project."""
        query = """
        mutation($input: ServiceCreateInput!) {
            serviceCreate(input: $input) {
                id
                name
            }
        }
        """
        data = await self._execute(query, {
            "input": {
                "projectId": project_id,
                "name": name,
            }
        })
        return data["serviceCreate"]

    async def connect_service_to_repo(self, service_id: str, repo: str, branch: str = "main") -> bool:
        """Connect a service to a GitHub repository."""
        query = """
        mutation($id: String!, $input: ServiceConnectInput!) {
            serviceConnect(id: $id, input: $input) {
                id
            }
        }
        """
        await self._execute(query, {
            "id": service_id,
            "input": {
                "repo": repo,
                "branch": branch,
            }
        })
        return True

    async def delete_service(self, service_id: str) -> bool:
        """Delete a service."""
        query = """
        mutation($id: String!) {
            serviceDelete(id: $id)
        }
        """
        await self._execute(query, {"id": service_id})
        return True

    # ── Variable Operations ───────────────────────────────────────────────

    async def upsert_variables(
        self, project_id: str, environment_id: str, service_id: str, variables: dict[str, str]
    ) -> bool:
        """Set multiple environment variables at once."""
        query = """
        mutation($input: VariableCollectionUpsertInput!) {
            variableCollectionUpsert(input: $input)
        }
        """
        await self._execute(query, {
            "input": {
                "projectId": project_id,
                "environmentId": environment_id,
                "serviceId": service_id,
                "variables": variables,
            }
        })
        return True

    # ── Volume Operations ─────────────────────────────────────────────────

    async def create_volume(
        self, project_id: str, environment_id: str, mount_path: str = "/data/generations"
    ) -> dict:
        """Create a persistent volume."""
        query = """
        mutation($input: VolumeCreateInput!) {
            volumeCreate(input: $input) {
                id
                name
            }
        }
        """
        data = await self._execute(query, {
            "input": {
                "projectId": project_id,
                "environmentId": environment_id,
                "mountPath": mount_path,
                "name": "generations",
            }
        })
        return data["volumeCreate"]

    # ── Domain Operations ─────────────────────────────────────────────────

    async def create_service_domain(self, service_id: str, environment_id: str) -> dict:
        """Create a Railway-provided domain for a service."""
        query = """
        mutation($input: ServiceDomainCreateInput!) {
            serviceDomainCreate(input: $input) {
                id
                domain
            }
        }
        """
        data = await self._execute(query, {
            "input": {
                "serviceId": service_id,
                "environmentId": environment_id,
            }
        })
        return data["serviceDomainCreate"]

    # ── Deploy Operations ─────────────────────────────────────────────────

    async def deploy_service(self, service_id: str, environment_id: str) -> dict:
        """Trigger a deployment for a service."""
        query = """
        mutation($serviceId: String!, $environmentId: String!) {
            serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
        }
        """
        data = await self._execute(query, {
            "serviceId": service_id,
            "environmentId": environment_id,
        })
        return data

    # ── Status Operations ─────────────────────────────────────────────────

    async def get_service_deployments(self, project_id: str, service_id: str, environment_id: str) -> list:
        """Get recent deployments for a service."""
        query = """
        query($input: DeploymentListInput!) {
            deployments(input: $input) {
                edges {
                    node {
                        id
                        status
                        createdAt
                    }
                }
            }
        }
        """
        data = await self._execute(query, {
            "input": {
                "projectId": project_id,
                "serviceId": service_id,
                "environmentId": environment_id,
            }
        })
        return [edge["node"] for edge in data["deployments"]["edges"]]
