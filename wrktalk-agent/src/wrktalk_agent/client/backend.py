"""Backend API client for communicating with WrkTalk Backend."""

from datetime import datetime
from typing import Any, Dict, Optional

import httpx
import structlog

logger = structlog.get_logger()


class BackendClient:
    """Client for WrkTalk Backend API."""

    def __init__(self, base_url: str, agent_secret: str, timeout: int = 30):
        """Initialize Backend client.

        Args:
            base_url: Backend base URL
            agent_secret: Secret key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.agent_secret = agent_secret
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    def _get_headers(self) -> Dict[str, str]:
        """Get common headers for API requests."""
        return {
            "X-Agent-Secret": self.agent_secret,
            "Content-Type": "application/json",
        }

    async def get_pending_task(self) -> Optional[Dict[str, Any]]:
        """Poll for pending agent tasks.

        Returns:
            Task dict if available, None otherwise
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/internal/agent/tasks",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            data = response.json()

            task = data.get("task")
            if task:
                logger.info(
                    "backend.task_received",
                    task_id=task.get("id"),
                    task_type=task.get("type"),
                )
            return task

        except httpx.HTTPError as e:
            logger.error("backend.poll_error", error=str(e))
            return None

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        picked_up_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update task status.

        Args:
            task_id: Task ID
            status: New status (inProgress, completed, failed)
            picked_up_at: ISO timestamp when task was picked up
            completed_at: ISO timestamp when task completed
            result: Result data for completed tasks
            error_message: Error message for failed tasks

        Returns:
            True if update successful
        """
        payload = {"status": status}

        if picked_up_at:
            payload["pickedUpAt"] = picked_up_at
        if completed_at:
            payload["completedAt"] = completed_at
        if result:
            payload["result"] = result
        if error_message:
            payload["errorMessage"] = error_message

        try:
            response = await self.client.post(
                f"{self.base_url}/internal/agent/tasks/{task_id}/status",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            logger.info("backend.task_status_updated", task_id=task_id, status=status)
            return True

        except httpx.HTTPError as e:
            logger.error(
                "backend.status_update_error",
                task_id=task_id,
                status=status,
                error=str(e),
            )
            return False

    async def send_heartbeat(self, task_id: str) -> bool:
        """Send task heartbeat to keep it alive.

        Args:
            task_id: Task ID

        Returns:
            True if heartbeat sent successfully
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/internal/agent/tasks/{task_id}/heartbeat",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return True

        except httpx.HTTPError as e:
            logger.warning("backend.heartbeat_error", task_id=task_id, error=str(e))
            return False

    async def insert_config(self, key: str, value: str) -> bool:
        """Insert non-essential environment variable.

        Args:
            key: Config key
            value: Config value

        Returns:
            True if inserted successfully
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/internal/config",
                headers=self._get_headers(),
                json={"key": key, "value": value},
            )
            response.raise_for_status()
            logger.info("backend.config_inserted", key=key)
            return True

        except httpx.HTTPError as e:
            logger.warning("backend.config_insert_error", key=key, error=str(e))
            return False

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
