"""Main agent implementation."""

import asyncio
import os
import secrets
import signal
from datetime import datetime
from typing import Optional

import structlog

from .client.backend import BackendClient
from .client.bucket import MinIOClient
from .config import AgentConfig, DeploymentType
from .executor.compose import ComposeExecutor
from .executor.helm import HelmExecutor
from .utils.heartbeat import HeartbeatThread

logger = structlog.get_logger()


class Agent:
    """Stateless WrkTalk deployment agent."""

    def __init__(self, config: AgentConfig):
        """Initialize agent.

        Args:
            config: Agent configuration
        """
        self.config = config

        # Initialize clients
        self.backend = BackendClient(
            base_url=config.backend_url,
            agent_secret=config.agent_secret,
            timeout=config.backend_timeout,
        )

        self.bucket = MinIOClient(
            endpoint=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            bucket_name=config.minio_bucket_name,
            secure=config.minio_secure,
        )

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
            backend_url=config.backend_url,
            minio_endpoint=config.minio_endpoint,
            bucket=config.minio_bucket_name,
        )

    async def start(self):
        """Start the agent main loop."""
        logger.info("agent.starting")

        self._running = True

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        # Main polling loop
        while self._running:
            try:
                await self._poll_and_execute()
            except Exception as e:
                logger.error("agent.poll_error", error=str(e), exc_info=True)

            # Wait before next poll
            await asyncio.sleep(self.config.poll_interval)

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
        """Poll for tasks and execute if available."""
        # Poll Backend for pending task
        task = await self.backend.get_pending_task()

        if not task:
            logger.debug("agent.no_tasks")
            return

        task_id = task["id"]
        task_type = task["type"]

        logger.info("agent.task_received", task_id=task_id, task_type=task_type)
        self._current_task = task_id

        try:
            # Mark task as in progress
            await self.backend.update_task_status(
                task_id=task_id,
                status="inProgress",
                picked_up_at=datetime.utcnow().isoformat(),
            )

            # Execute based on task type
            if task_type == "deploy":
                result = await self._execute_deployment(task)
            elif task_type == "rollback":
                result = await self._execute_rollback(task)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

            # Report success
            await self.backend.update_task_status(
                task_id=task_id,
                status="completed",
                completed_at=datetime.utcnow().isoformat(),
                result=result,
            )

            logger.info("agent.task_completed", task_id=task_id, result=result)

        except Exception as e:
            logger.error(
                "agent.task_failed", task_id=task_id, error=str(e), exc_info=True
            )

            # Report failure
            await self.backend.update_task_status(
                task_id=task_id,
                status="failed",
                completed_at=datetime.utcnow().isoformat(),
                error_message=str(e),
            )

        finally:
            self._current_task = None
            if self._heartbeat:
                self._heartbeat.stop()
                self._heartbeat = None

    async def _execute_deployment(self, task: dict) -> dict:
        """Execute deployment task.

        Args:
            task: Task payload from Backend

        Returns:
            Result dict
        """
        payload = task["payload"]
        task_id = task["id"]

        logger.info("agent.deployment_starting", task_id=task_id)

        # 1. Insert non-essential envs (continue on failure)
        new_envs = payload.get("newNonEssentialEnvs", [])
        for env in new_envs:
            try:
                await self.backend.insert_config(env["key"], env["value"])
            except Exception as e:
                logger.warning(
                    "agent.env_insert_failed", key=env["key"], error=str(e)
                )

        # 2. Download chart/bundle from MinIO
        chart_info = payload["chart"]
        chart_bucket_path = chart_info["bucketPath"]

        # Determine local path based on deployment type
        if self.config.deployment_type == DeploymentType.KUBERNETES:
            local_chart_path = "/tmp/wrktalk-chart.tgz"
        else:
            local_chart_path = "/tmp/wrktalk-compose.tar.gz"

        chart_path = await self.bucket.download(
            object_path=chart_bucket_path,
            local_path=local_chart_path,
        )

        # 3. Download values.yaml (K8s) or .env (Compose)
        values_path = None
        env_path = None

        if self.config.deployment_type == DeploymentType.KUBERNETES:
            # Download values.yaml
            values_bucket_path = payload.get("valuesBucketPath", "config/values.yaml")
            values_path = await self.bucket.download(
                object_path=values_bucket_path,
                local_path="/tmp/values.yaml",
            )
        else:
            # Download .env file
            env_bucket_path = payload.get("envBucketPath", "config/.env")
            env_path = await self.bucket.download(
                object_path=env_bucket_path,
                local_path="/tmp/.env",
            )

        try:
            # 4. Start heartbeat thread
            self._heartbeat = HeartbeatThread(
                backend=self.backend,
                task_id=task_id,
                interval=self.config.heartbeat_interval,
            )
            self._heartbeat.start()

            # 5. Execute deployment
            image_tags = payload.get("imageTags", {})
            deployment_result = await self.executor.deploy(
                artifact_path=chart_path,
                values_path=values_path,
                env_path=env_path,
                image_tags=image_tags,
            )

            # 6. Build result
            result = {
                "status": deployment_result.status,
                "message": deployment_result.message,
            }

            if deployment_result.revision:
                result["helmRevision"] = deployment_result.revision

            if deployment_result.error:
                result["error"] = deployment_result.error

            return result

        finally:
            # 7. Stop heartbeat
            if self._heartbeat:
                self._heartbeat.stop()
                self._heartbeat = None

            # 8. Cleanup temp files
            self._secure_delete(chart_path)
            if values_path:
                self._secure_delete(values_path)
            if env_path:
                self._secure_delete(env_path)

    async def _execute_rollback(self, task: dict) -> dict:
        """Execute rollback task.

        Args:
            task: Task payload from Backend

        Returns:
            Result dict
        """
        payload = task["payload"]
        task_id = task["id"]

        logger.info("agent.rollback_starting", task_id=task_id)

        # Start heartbeat
        self._heartbeat = HeartbeatThread(
            backend=self.backend,
            task_id=task_id,
            interval=self.config.heartbeat_interval,
        )
        self._heartbeat.start()

        try:
            rollback_result = await self.executor.rollback(
                target_revision=payload.get("targetRevision"),
                target_version=payload.get("targetVersion"),
            )

            result = {
                "status": rollback_result.status,
                "message": rollback_result.message,
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

    def _secure_delete(self, path: str):
        """Securely delete file by overwriting with random data.

        Args:
            path: File path to delete
        """
        try:
            if os.path.exists(path):
                size = os.path.getsize(path)
                with open(path, "wb") as f:
                    f.write(secrets.token_bytes(size))
                os.remove(path)
                logger.debug("agent.file_deleted", path=path)
        except Exception as e:
            logger.warning(
                "agent.secure_delete_failed", path=path, error=str(e)
            )
