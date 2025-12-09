"""Base executor interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class DeploymentResult:
    """Result of a deployment operation."""

    status: str  # "success" or "failed"
    revision: Optional[int] = None  # Helm revision (K8s only)
    message: Optional[str] = None
    error: Optional[str] = None


class BaseExecutor(ABC):
    """Base class for deployment executors."""

    @abstractmethod
    async def deploy(
        self,
        artifact_path: str,
        values_path: Optional[str],
        env_path: Optional[str],
        image_tags: Dict[str, str],
    ) -> DeploymentResult:
        """Execute deployment.

        Args:
            artifact_path: Path to chart/compose bundle
            values_path: Path to values.yaml (K8s only)
            env_path: Path to .env file (Compose only)
            image_tags: Dict of service -> image tag

        Returns:
            DeploymentResult
        """
        pass

    @abstractmethod
    async def rollback(
        self,
        target_revision: Optional[int] = None,
        target_version: Optional[str] = None,
    ) -> DeploymentResult:
        """Execute rollback.

        Args:
            target_revision: Target Helm revision (K8s)
            target_version: Target version (both)

        Returns:
            DeploymentResult
        """
        pass
