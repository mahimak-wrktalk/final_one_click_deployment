"""Helm executor for Kubernetes deployments."""

import asyncio
import json
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional

import structlog

from .base import BaseExecutor, DeploymentResult

logger = structlog.get_logger()


@dataclass
class HelmConfig:
    """Helm configuration."""

    namespace: str
    release_name: str
    timeout: str = "10m"


class HelmExecutor(BaseExecutor):
    """Kubernetes Helm executor."""

    def __init__(self, namespace: str, release_name: str, timeout: str = "10m"):
        """Initialize Helm executor.

        Args:
            namespace: Kubernetes namespace
            release_name: Helm release name
            timeout: Helm operation timeout
        """
        self.config = HelmConfig(
            namespace=namespace,
            release_name=release_name,
            timeout=timeout,
        )
        logger.info(
            "helm.executor_initialized",
            namespace=namespace,
            release=release_name,
            timeout=timeout,
        )

    async def deploy(
        self,
        artifact_path: str,
        values_path: Optional[str],
        env_path: Optional[str],  # Not used for K8s
        image_tags: Dict[str, str],
    ) -> DeploymentResult:
        """Execute Helm upgrade with atomic rollback.

        Args:
            artifact_path: Path to Helm chart (.tgz)
            values_path: Path to values.yaml
            env_path: Not used for Kubernetes
            image_tags: Dict of service -> image tag

        Returns:
            DeploymentResult
        """
        logger.info(
            "helm.upgrade.starting",
            release=self.config.release_name,
            chart=artifact_path,
            values=values_path,
        )

        # Build helm upgrade command
        cmd = [
            "helm",
            "upgrade",
            self.config.release_name,
            artifact_path,
            "--install",  # Install if doesn't exist
            "--namespace",
            self.config.namespace,
            "--create-namespace",  # Create namespace if doesn't exist
            "--timeout",
            self.config.timeout,
            "--atomic",  # Auto-rollback on failure
            "--wait",  # Wait for pods to be ready
            "--output",
            "json",
        ]

        # Add values file if provided
        if values_path:
            cmd.extend(["--values", values_path])

        # Add image tag overrides
        for service, tag in image_tags.items():
            cmd.extend(["--set", f"{service}.image.tag={tag}"])

        logger.info("helm.command", cmd=" ".join(cmd))

        try:
            # Execute helm upgrade
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=660,  # 11 minutes (slightly more than helm timeout)
            )

            if result.returncode != 0:
                logger.error(
                    "helm.upgrade.failed",
                    stderr=result.stderr,
                    stdout=result.stdout,
                    returncode=result.returncode,
                )
                return DeploymentResult(
                    status="failed",
                    message="Helm upgrade failed",
                    error=result.stderr,
                )

            # Parse output to get revision
            output = {}
            if result.stdout:
                try:
                    output = json.loads(result.stdout)
                except json.JSONDecodeError:
                    logger.warning("helm.output_not_json", stdout=result.stdout)

            revision = output.get("version")
            if not revision:
                # Fallback: get current revision
                revision = await self._get_current_revision()

            logger.info(
                "helm.upgrade.success",
                revision=revision,
                release=self.config.release_name,
            )

            return DeploymentResult(
                status="success",
                revision=revision,
                message=f"Helm upgrade completed successfully (revision {revision})",
            )

        except subprocess.TimeoutExpired:
            logger.error("helm.upgrade.timeout")
            return DeploymentResult(
                status="failed",
                message="Helm upgrade timed out",
                error=f"Operation exceeded {self.config.timeout}",
            )

        except Exception as e:
            logger.error("helm.upgrade.exception", error=str(e), exc_info=True)
            return DeploymentResult(
                status="failed",
                message="Helm upgrade failed with exception",
                error=str(e),
            )

    async def rollback(
        self,
        target_revision: Optional[int] = None,
        target_version: Optional[str] = None,
    ) -> DeploymentResult:
        """Execute Helm rollback.

        Args:
            target_revision: Target Helm revision number
            target_version: Not used for Helm rollback

        Returns:
            DeploymentResult
        """
        logger.info(
            "helm.rollback.starting",
            release=self.config.release_name,
            target_revision=target_revision,
        )

        cmd = [
            "helm",
            "rollback",
            self.config.release_name,
            "--namespace",
            self.config.namespace,
            "--timeout",
            self.config.timeout,
            "--wait",
        ]

        if target_revision:
            cmd.append(str(target_revision))

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=660,
            )

            if result.returncode != 0:
                logger.error("helm.rollback.failed", stderr=result.stderr)
                return DeploymentResult(
                    status="failed",
                    message="Helm rollback failed",
                    error=result.stderr,
                )

            current_revision = await self._get_current_revision()

            logger.info(
                "helm.rollback.success",
                revision=current_revision,
                release=self.config.release_name,
            )

            return DeploymentResult(
                status="success",
                revision=current_revision,
                message=f"Helm rollback completed (revision {current_revision})",
            )

        except Exception as e:
            logger.error("helm.rollback.exception", error=str(e), exc_info=True)
            return DeploymentResult(
                status="failed",
                message="Helm rollback failed with exception",
                error=str(e),
            )

    async def _get_current_revision(self) -> Optional[int]:
        """Get current Helm revision.

        Returns:
            Current revision number or None
        """
        try:
            result = subprocess.run(
                [
                    "helm",
                    "list",
                    "-n",
                    self.config.namespace,
                    "-f",
                    self.config.release_name,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout:
                releases = json.loads(result.stdout)
                if releases and len(releases) > 0:
                    revision = releases[0].get("revision")
                    return int(revision) if revision else None

        except Exception as e:
            logger.warning("helm.get_revision_error", error=str(e))

        return None


class HelmError(Exception):
    """Helm operation error."""

    pass
