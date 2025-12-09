"""Docker Compose executor for Docker deployments."""

import asyncio
import os
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from typing import Dict, Optional

import structlog

from .base import BaseExecutor, DeploymentResult

logger = structlog.get_logger()


@dataclass
class ComposeConfig:
    """Docker Compose configuration."""

    project_name: str
    working_dir: str


class ComposeExecutor(BaseExecutor):
    """Docker Compose executor."""

    def __init__(self, project_name: str, working_dir: str):
        """Initialize Compose executor.

        Args:
            project_name: Docker Compose project name
            working_dir: Working directory for extraction
        """
        self.config = ComposeConfig(
            project_name=project_name,
            working_dir=working_dir,
        )
        logger.info(
            "compose.executor_initialized",
            project=project_name,
            workdir=working_dir,
        )

    async def deploy(
        self,
        artifact_path: str,
        values_path: Optional[str],  # Not used for Compose
        env_path: Optional[str],
        image_tags: Dict[str, str],
    ) -> DeploymentResult:
        """Execute Docker Compose deployment.

        Args:
            artifact_path: Path to compose bundle (.tar.gz)
            values_path: Not used for Docker Compose
            env_path: Path to .env file
            image_tags: Dict of service -> image tag

        Returns:
            DeploymentResult
        """
        logger.info(
            "compose.deploy.starting",
            project=self.config.project_name,
            bundle=artifact_path,
            env_file=env_path,
        )

        try:
            # 1. Create working directory
            os.makedirs(self.config.working_dir, exist_ok=True)

            # 2. Extract compose bundle
            await self._extract_bundle(artifact_path, self.config.working_dir)

            # 3. Copy .env file if provided
            if env_path and os.path.exists(env_path):
                dest_env = os.path.join(self.config.working_dir, ".env")
                shutil.copy(env_path, dest_env)
                logger.info("compose.env_copied", src=env_path, dest=dest_env)

            # 4. Set image tag environment variables
            env_vars = os.environ.copy()
            for service, tag in image_tags.items():
                env_key = f"{service.upper()}_IMAGE_TAG"
                env_vars[env_key] = tag
                logger.debug("compose.env_var_set", key=env_key, value=tag)

            compose_file = os.path.join(self.config.working_dir, "docker-compose.yaml")
            if not os.path.exists(compose_file):
                # Try alternative name
                compose_file = os.path.join(self.config.working_dir, "docker-compose.yml")

            if not os.path.exists(compose_file):
                return DeploymentResult(
                    status="failed",
                    message="docker-compose.yaml not found in bundle",
                    error=f"No docker-compose file in {self.config.working_dir}",
                )

            # 5. Pull images
            logger.info("compose.pulling_images")
            pull_result = await asyncio.to_thread(
                subprocess.run,
                ["docker-compose", "-f", compose_file, "pull"],
                cwd=self.config.working_dir,
                capture_output=True,
                text=True,
                env=env_vars,
                timeout=600,  # 10 minutes for pulling images
            )

            if pull_result.returncode != 0:
                logger.warning(
                    "compose.pull_warning",
                    stderr=pull_result.stderr,
                    stdout=pull_result.stdout,
                )
                # Continue even if pull has warnings

            # 6. Deploy with docker-compose up
            logger.info("compose.deploying")
            up_result = await asyncio.to_thread(
                subprocess.run,
                [
                    "docker-compose",
                    "-f",
                    compose_file,
                    "-p",
                    self.config.project_name,
                    "up",
                    "-d",
                    "--remove-orphans",
                ],
                cwd=self.config.working_dir,
                capture_output=True,
                text=True,
                env=env_vars,
                timeout=300,  # 5 minutes for deployment
            )

            if up_result.returncode != 0:
                logger.error(
                    "compose.deploy.failed",
                    stderr=up_result.stderr,
                    stdout=up_result.stdout,
                )
                return DeploymentResult(
                    status="failed",
                    message="Docker Compose deployment failed",
                    error=up_result.stderr,
                )

            logger.info(
                "compose.deploy.success",
                project=self.config.project_name,
                stdout=up_result.stdout,
            )

            return DeploymentResult(
                status="success",
                message="Docker Compose deployment completed successfully",
            )

        except subprocess.TimeoutExpired as e:
            logger.error("compose.timeout", error=str(e))
            return DeploymentResult(
                status="failed",
                message="Docker Compose operation timed out",
                error=str(e),
            )

        except Exception as e:
            logger.error("compose.deploy.exception", error=str(e), exc_info=True)
            return DeploymentResult(
                status="failed",
                message="Docker Compose deployment failed with exception",
                error=str(e),
            )

    async def rollback(
        self,
        target_revision: Optional[int] = None,
        target_version: Optional[str] = None,
    ) -> DeploymentResult:
        """Execute Docker Compose rollback.

        Note: Rollback for Compose requires re-deploying previous version.
        This is handled by the Backend providing the old bundle/env paths.

        Args:
            target_revision: Not used for Compose
            target_version: Target version to rollback to

        Returns:
            DeploymentResult
        """
        logger.info(
            "compose.rollback.starting",
            project=self.config.project_name,
            target_version=target_version,
        )

        return DeploymentResult(
            status="failed",
            message="Rollback not implemented",
            error="Compose rollback requires Backend to provide previous version paths",
        )

    async def _extract_bundle(self, artifact_path: str, dest_dir: str):
        """Extract compose bundle tarball.

        Args:
            artifact_path: Path to .tar.gz bundle
            dest_dir: Destination directory
        """
        logger.info("compose.extracting", src=artifact_path, dest=dest_dir)

        await asyncio.to_thread(self._extract_tarball, artifact_path, dest_dir)

        logger.info("compose.extracted", dest=dest_dir)

    def _extract_tarball(self, artifact_path: str, dest_dir: str):
        """Sync tarball extraction.

        Args:
            artifact_path: Path to .tar.gz file
            dest_dir: Destination directory
        """
        with tarfile.open(artifact_path, "r:gz") as tar:
            tar.extractall(dest_dir)


class ComposeError(Exception):
    """Compose operation error."""

    pass
