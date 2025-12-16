"""Main agent implementation."""

import asyncio
import io
import os
import secrets
import signal
import tarfile
import tempfile
from typing import Optional

import structlog

from .client.email import EmailClient
from .config import AgentConfig, DeploymentType
from .db import AgentRepository, DatabasePool, TaskType
from .executor.compose import ComposeExecutor
from .executor.helm import HelmExecutor
from .utils.heartbeat import HeartbeatThread
from .utils.maintenance import MaintenanceHandler

logger = structlog.get_logger()


class Agent:
    """Stateless WrkTalk deployment agent."""

    def __init__(self, config: AgentConfig):
        """Initialize agent.

        Args:
            config: Agent configuration
        """
        self.config = config

        # Database connection (NEW - replaces HTTP/MinIO)
        self.db_pool = DatabasePool(config.database_url)
        self.repo: Optional[AgentRepository] = None

        # Email client (NEW - agent sends notifications)
        self.email_client: Optional[EmailClient] = None

        # Maintenance mode handler (NEW)
        self.maintenance = MaintenanceHandler(mode=config.maintenance_mode_handler)

        # Initialize executor based on deployment type
        if config.deployment_type == DeploymentType.KUBERNETES:
            self.executor = HelmExecutor(
                namespace=config.kube_namespace,
                release_name=config.helm_release_name,
                timeout=config.helm_timeout,
            )
        else:
            self.executor = ComposeExecutor(
                project_name=config.compose_project_name,
                working_dir=config.compose_working_dir,
            )

        self._running = False
        self._current_task: Optional[str] = None
        self._heartbeat: Optional[HeartbeatThread] = None

        logger.info(
            "agent.initialized",
            deployment_type=config.deployment_type.value,
            db_host=config.db_host,
            db_name=config.db_name,
        )

    async def start(self):
        """Start the agent main loop."""
        logger.info("agent.starting")

        # Initialize database connection
        await self.db_pool.connect()
        self.repo = AgentRepository(self.db_pool.pool)

        # Load SMTP configuration from database
        try:
            smtp_config = await self.repo.get_smtp_config()
            if smtp_config and smtp_config.get("smtp_host"):
                self.email_client = EmailClient(
                    smtp_host=smtp_config["smtp_host"],
                    smtp_port=smtp_config["smtp_port"],
                    smtp_user=smtp_config["smtp_user"],
                    smtp_password=smtp_config["smtp_password"],
                    smtp_from=smtp_config["smtp_from"],
                )
                logger.info("agent.email_client_initialized")
            else:
                logger.warning("agent.smtp_config_not_found")
        except Exception as e:
            logger.warning("agent.smtp_config_load_failed", error=str(e))

        self._running = True

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        try:
            # Main polling loop
            while self._running:
                try:
                    await self._poll_and_execute()
                except Exception as e:
                    logger.error("agent.poll_error", error=str(e), exc_info=True)

                # Wait before next poll
                await asyncio.sleep(self.config.poll_interval)
        finally:
            # Close database connection
            await self.db_pool.close()

        logger.info("agent.stopped")

    def _handle_shutdown(self):
        """Handle shutdown signals."""
        logger.info("agent.shutdown_requested")
        if self._current_task:
            logger.warning(
                "agent.shutdown_during_task", task_id=self._current_task
            )
        self._running = False

    async def _poll_and_execute(self):
        """Poll database for tasks and execute if available."""
        # Update last poll timestamp
        await self.repo.update_last_agent_poll()

        # Poll database for pending task (atomic with FOR UPDATE SKIP LOCKED)
        task = await self.repo.get_pending_task()

        if not task:
            logger.debug("agent.no_tasks")
            return

        logger.info("agent.task_received", task_id=task.id, task_type=task.type)
        self._current_task = task.id

        # Get release version early for error reporting
        release_version = "unknown"
        try:
            if task.type == TaskType.DEPLOY and task.release_artifact_id:
                artifact = await self.repo.get_artifact(task.release_artifact_id)
                if artifact:
                    release_version = artifact.release_version
        except Exception:
            pass  # If we can't get version, use "unknown"

        try:
            # Execute based on task type
            if task.type == TaskType.DEPLOY:
                result = await self._execute_deployment(task)
            elif task.type == TaskType.ROLLBACK:
                result = await self._execute_rollback(task)
            else:
                raise ValueError(f"Unknown task type: {task.type}")

            # Update task status to completed
            await self.repo.update_task_status(
                task_id=task.id,
                status="completed",
                result=result,
            )

            # Send success email notification
            if self.email_client:
                await self._send_notification(
                    status="SUCCESS",
                    release_version=result.get("release_version", "unknown"),
                    task_id=task.id,
                )

            logger.info("agent.task_completed", task_id=task.id, result=result)

        except Exception as e:
            logger.error(
                "agent.task_failed", task_id=task.id, error=str(e), exc_info=True
            )

            # Update task status to failed
            await self.repo.update_task_status(
                task_id=task.id,
                status="failed",
                error=str(e),
            )

            # Send failure email notification
            if self.email_client:
                await self._send_notification(
                    status="FAILED",
                    release_version=release_version,
                    error_message=str(e),
                    task_id=task.id,
                )

        finally:
            self._current_task = None
            if self._heartbeat:
                self._heartbeat.stop()
                self._heartbeat = None

    async def _execute_deployment(self, task) -> dict:
        """Execute deployment task.

        Args:
            task: AgentTask from database

        Returns:
            Result dict
        """
        logger.info("agent.deployment_starting", task_id=task.id)

        # 1. Get artifact from database (replaces MinIO download)
        artifact = await self.repo.get_artifact(task.release_artifact_id)
        if not artifact:
            raise ValueError(f"Artifact not found: {task.release_artifact_id}")

        logger.info(
            "agent.artifact_loaded",
            artifact_id=artifact.id,
            version=artifact.release_version,
            size_bytes=len(artifact.artifact_data),
        )

        # 2. Create temporary directory for extraction
        temp_dir = tempfile.mkdtemp(prefix="wrktalk-deploy-")

        try:
            # 3. Extract artifact bytes to temp directory
            tarball_path = os.path.join(temp_dir, "artifact.tar.gz")
            with open(tarball_path, "wb") as f:
                f.write(artifact.artifact_data)

            with tarfile.open(tarball_path, "r:gz") as tar:
                tar.extractall(path=temp_dir)

            logger.info("agent.artifact_extracted", temp_dir=temp_dir)

            # 4. Enable maintenance mode
            await self.maintenance.enable()
            await self.repo.set_maintenance_mode(True)

            # 5. Start heartbeat thread (uses database instead of HTTP)
            self._heartbeat = HeartbeatThread(
                repo=self.repo,
                task_id=task.id,
                interval=self.config.heartbeat_interval,
            )
            self._heartbeat.start()

            # 6. Prepare deployment based on type
            values_path = None
            env_path = None
            chart_path = None

            if self.config.deployment_type == DeploymentType.KUBERNETES:
                # For Kubernetes: find chart directory
                # First check for 'chart' subdirectory
                chart_path = os.path.join(temp_dir, "chart")
                if not os.path.exists(chart_path):
                    # Try to find Chart.yaml in extracted subdirectories
                    for item in os.listdir(temp_dir):
                        item_path = os.path.join(temp_dir, item)
                        if os.path.isdir(item_path):
                            chart_yaml = os.path.join(item_path, "Chart.yaml")
                            if os.path.exists(chart_yaml):
                                chart_path = item_path
                                break
                    else:
                        # Fallback to temp_dir root
                        chart_path = temp_dir

                logger.info("agent.chart_path_resolved", chart_path=chart_path)

                # Write values.yaml if provided in database
                if artifact.values_data:
                    values_path = os.path.join(temp_dir, "values.yaml")
                    with open(values_path, "w") as f:
                        f.write(artifact.values_data)
            else:
                # For Docker Compose: find compose file
                chart_path = os.path.join(temp_dir, "docker-compose.yaml")
                if not os.path.exists(chart_path):
                    chart_path = os.path.join(temp_dir, "docker-compose.yml")

                # Write .env if provided in database
                if artifact.env_data:
                    env_path = os.path.join(temp_dir, ".env")
                    with open(env_path, "w") as f:
                        f.write(artifact.env_data)

            # 7. Execute deployment
            deployment_result = await self.executor.deploy(
                artifact_path=chart_path,
                values_path=values_path,
                env_path=env_path,
                image_tags={},  # Image tags are baked into artifact
            )

            # Check deployment status - raise exception if failed
            if deployment_result.status != "success":
                error_msg = deployment_result.error or deployment_result.message
                raise RuntimeError(f"Deployment failed: {error_msg}")

            # 8. Update artifact flags (mark as current)
            chart_type = "helm" if self.config.deployment_type == DeploymentType.KUBERNETES else "compose"
            current_artifact_id = await self.repo.get_current_artifact_id(chart_type)
            await self.repo.update_artifact_flags(
                new_current_id=artifact.id,
                old_current_id=current_artifact_id,
                chart_type=chart_type,
            )

            # 9. Build result
            result = {
                "status": deployment_result.status,
                "message": deployment_result.message,
                "release_version": artifact.release_version,
            }

            if deployment_result.revision:
                result["helmRevision"] = deployment_result.revision

            if deployment_result.error:
                result["error"] = deployment_result.error

            return result

        finally:
            # 10. Disable maintenance mode
            await self.maintenance.disable()
            await self.repo.set_maintenance_mode(False)

            # 11. Stop heartbeat
            if self._heartbeat:
                self._heartbeat.stop()
                self._heartbeat = None

            # 12. Cleanup temp directory (secure delete)
            self._secure_delete_directory(temp_dir)

    async def _execute_rollback(self, task) -> dict:
        """Execute rollback task.

        Args:
            task: AgentTask from database

        Returns:
            Result dict
        """
        logger.info("agent.rollback_starting", task_id=task.id)

        # Get previous artifact from database for rollback
        chart_type = "helm" if self.config.deployment_type == DeploymentType.KUBERNETES else "compose"
        artifact = await self.repo.get_previous_artifact(chart_type)

        if not artifact:
            raise ValueError(f"No previous version available for rollback (chart_type={chart_type})")

        logger.info(
            "agent.rollback_artifact_loaded",
            artifact_id=artifact.id,
            version=artifact.release_version,
        )

        # For Kubernetes: Use Helm's built-in rollback (automatic with --atomic flag)
        # For Docker: Deploy the previous version from database
        if self.config.deployment_type == DeploymentType.KUBERNETES:
            # Helm rollback using history
            self._heartbeat = HeartbeatThread(
                repo=self.repo,
                task_id=task.id,
                interval=self.config.heartbeat_interval,
            )
            self._heartbeat.start()

            try:
                rollback_result = await self.executor.rollback(
                    target_revision=None,  # Use latest previous revision
                    target_version=None,
                )

                result = {
                    "status": rollback_result.status,
                    "message": rollback_result.message,
                    "release_version": artifact.release_version,
                }

                if rollback_result.revision:
                    result["helmRevision"] = rollback_result.revision

                if rollback_result.error:
                    result["error"] = rollback_result.error

                return result

            finally:
                if self._heartbeat:
                    self._heartbeat.stop()
                    self._heartbeat = None
        else:
            # Docker Compose: Re-deploy previous version from database
            # This is similar to deployment but with previous artifact
            temp_dir = tempfile.mkdtemp(prefix="wrktalk-rollback-")

            try:
                # Extract previous artifact
                tarball_path = os.path.join(temp_dir, "artifact.tar.gz")
                with open(tarball_path, "wb") as f:
                    f.write(artifact.artifact_data)

                with tarfile.open(tarball_path, "r:gz") as tar:
                    tar.extractall(path=temp_dir)

                # Enable maintenance mode
                await self.maintenance.enable()
                await self.repo.set_maintenance_mode(True)

                # Start heartbeat
                self._heartbeat = HeartbeatThread(
                    repo=self.repo,
                    task_id=task.id,
                    interval=self.config.heartbeat_interval,
                )
                self._heartbeat.start()

                # Find compose file
                chart_path = os.path.join(temp_dir, "docker-compose.yaml")
                if not os.path.exists(chart_path):
                    chart_path = os.path.join(temp_dir, "docker-compose.yml")

                # Write .env if provided
                env_path = None
                if artifact.env_data:
                    env_path = os.path.join(temp_dir, ".env")
                    with open(env_path, "w") as f:
                        f.write(artifact.env_data)

                # Execute rollback (re-deploy previous version)
                deployment_result = await self.executor.deploy(
                    artifact_path=chart_path,
                    values_path=None,
                    env_path=env_path,
                    image_tags={},
                )

                # Check deployment status - raise exception if failed
                if deployment_result.status != "success":
                    error_msg = deployment_result.error or deployment_result.message
                    raise RuntimeError(f"Rollback failed: {error_msg}")

                # Update artifact flags (mark previous as current again)
                current_artifact_id = await self.repo.get_current_artifact_id(chart_type)
                await self.repo.update_artifact_flags(
                    new_current_id=artifact.id,
                    old_current_id=current_artifact_id,
                    chart_type=chart_type,
                )

                result = {
                    "status": deployment_result.status,
                    "message": f"Rolled back to {artifact.release_version}",
                    "release_version": artifact.release_version,
                }

                if deployment_result.error:
                    result["error"] = deployment_result.error

                return result

            finally:
                # Disable maintenance mode
                await self.maintenance.disable()
                await self.repo.set_maintenance_mode(False)

                # Stop heartbeat
                if self._heartbeat:
                    self._heartbeat.stop()
                    self._heartbeat = None

                # Cleanup
                self._secure_delete_directory(temp_dir)

    async def _send_notification(
        self,
        status: str,
        release_version: str,
        error_message: str = None,
        task_id: str = None,
    ):
        """Send email notification to admins.

        Args:
            status: Notification status
            release_version: Release version
            error_message: Error message if failed
            task_id: Task ID
        """
        try:
            # Get active admin emails
            admins = await self.repo.get_active_admins()
            admin_emails = [admin.email for admin in admins]

            if not admin_emails:
                logger.warning("agent.no_admin_emails")
                return

            # Send notification
            self.email_client.send_deployment_notification(
                to_emails=admin_emails,
                status=status,
                release_version=release_version,
                error_message=error_message,
                task_id=task_id,
            )
        except Exception as e:
            logger.error("agent.notification_failed", error=str(e))

    def _secure_delete(self, path: str):
        """Securely delete file by overwriting with random data.

        Args:
            path: File path to delete
        """
        try:
            if os.path.exists(path):
                if os.path.isfile(path):
                    size = os.path.getsize(path)
                    with open(path, "wb") as f:
                        f.write(secrets.token_bytes(size))
                    os.remove(path)
                    logger.debug("agent.file_deleted", path=path)
        except Exception as e:
            logger.warning(
                "agent.secure_delete_failed", path=path, error=str(e)
            )

    def _secure_delete_directory(self, path: str):
        """Securely delete directory and all contents.

        Args:
            path: Directory path to delete
        """
        try:
            if os.path.exists(path) and os.path.isdir(path):
                # Securely delete all files in directory
                for root, dirs, files in os.walk(path, topdown=False):
                    for name in files:
                        file_path = os.path.join(root, name)
                        self._secure_delete(file_path)

                # Remove empty directories
                import shutil
                shutil.rmtree(path, ignore_errors=True)
                logger.debug("agent.directory_deleted", path=path)
        except Exception as e:
            logger.warning(
                "agent.secure_delete_directory_failed", path=path, error=str(e)
            )
