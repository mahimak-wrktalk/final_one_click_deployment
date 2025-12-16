"""Database repository for agent operations."""

import asyncpg
import json
import structlog
from typing import Dict, List, Optional

from .models import Admin, AgentTask, DeploymentConfig, ReleaseArtifact, ServerEnv

logger = structlog.get_logger()


class AgentRepository:
    """Repository for agent database operations."""

    def __init__(self, pool: asyncpg.Pool):
        """Initialize repository.

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    async def get_pending_task(self) -> Optional[AgentTask]:
        """Get one pending task that's ready to execute.

        Uses FOR UPDATE SKIP LOCKED for atomic task picking.

        Returns:
            AgentTask if found, None otherwise
        """
        query = """
            UPDATE agent_task
            SET status = 'inProgress',
                picked_up_at = NOW(),
                updated_at = NOW()
            WHERE id = (
                SELECT id FROM agent_task
                WHERE status = 'pending'
                AND execute_after <= NOW()
                ORDER BY execute_after ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *
        """
        try:
            row = await self.pool.fetchrow(query)
            if row:
                task_dict = dict(row)
                # Convert UUIDs to strings
                if task_dict.get("id"):
                    task_dict["id"] = str(task_dict["id"])
                if task_dict.get("release_artifact_id"):
                    task_dict["release_artifact_id"] = str(task_dict["release_artifact_id"])
                # Convert result JSONB to dict if it's a string
                if task_dict.get("result") and isinstance(task_dict["result"], str):
                    task_dict["result"] = json.loads(task_dict["result"])
                logger.info("repository.task.acquired", task_id=task_dict["id"])
                return AgentTask(**task_dict)
            return None
        except Exception as e:
            logger.error("repository.task.acquire_failed", error=str(e))
            raise

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Update task status and result.

        Args:
            task_id: Task ID
            status: New status ('inProgress', 'completed', 'failed')
            result: Result dict (optional)
            error: Error message (optional)
        """
        query = """
            UPDATE agent_task
            SET status = $2::VARCHAR,
                completed_at = CASE
                    WHEN $2::VARCHAR IN ('completed', 'failed') THEN NOW()
                    ELSE completed_at
                END,
                result = $3::JSONB,
                error_message = $4,
                updated_at = NOW()
            WHERE id = $1
        """
        try:
            # Convert result dict to JSON
            result_json = json.dumps(result) if result else None
            await self.pool.execute(query, task_id, status, result_json, error)
            logger.info(
                "repository.task.status_updated",
                task_id=task_id,
                status=status,
            )
        except Exception as e:
            logger.error(
                "repository.task.status_update_failed",
                task_id=task_id,
                error=str(e),
            )
            raise

    async def update_heartbeat(self, task_id: str):
        """Update last heartbeat timestamp.

        Args:
            task_id: Task ID
        """
        try:
            await self.pool.execute(
                "UPDATE agent_task SET last_heartbeat = NOW(), updated_at = NOW() WHERE id = $1",
                task_id,
            )
            logger.debug("repository.heartbeat.updated", task_id=task_id)
        except Exception as e:
            logger.warning(
                "repository.heartbeat.update_failed",
                task_id=task_id,
                error=str(e),
            )

    async def get_artifact(self, artifact_id: str) -> Optional[ReleaseArtifact]:
        """Get release artifact with tarball bytes.

        Args:
            artifact_id: Artifact ID

        Returns:
            ReleaseArtifact if found, None otherwise
        """
        query = "SELECT * FROM release_artifact WHERE id = $1"
        try:
            row = await self.pool.fetchrow(query, artifact_id)
            if row:
                artifact_dict = dict(row)
                # Convert UUID to string
                if artifact_dict.get("id"):
                    artifact_dict["id"] = str(artifact_dict["id"])
                logger.info(
                    "repository.artifact.fetched",
                    artifact_id=artifact_id,
                    version=row["release_version"],
                    size_bytes=len(row["artifact_data"]),
                )
                return ReleaseArtifact(**artifact_dict)
            logger.warning("repository.artifact.not_found", artifact_id=artifact_id)
            return None
        except Exception as e:
            logger.error(
                "repository.artifact.fetch_failed",
                artifact_id=artifact_id,
                error=str(e),
            )
            raise

    async def get_previous_artifact(
        self, chart_type: str
    ) -> Optional[ReleaseArtifact]:
        """Get previous version for rollback.

        Args:
            chart_type: 'helm' or 'compose'

        Returns:
            ReleaseArtifact if found, None otherwise
        """
        query = """
            SELECT * FROM release_artifact
            WHERE is_previous = TRUE
            AND chart_type = $1
            LIMIT 1
        """
        try:
            row = await self.pool.fetchrow(query, chart_type)
            if row:
                artifact_dict = dict(row)
                # Convert UUID to string
                if artifact_dict.get("id"):
                    artifact_dict["id"] = str(artifact_dict["id"])
                logger.info(
                    "repository.previous_artifact.fetched",
                    chart_type=chart_type,
                    version=row["release_version"],
                )
                return ReleaseArtifact(**artifact_dict)
            logger.warning(
                "repository.previous_artifact.not_found", chart_type=chart_type
            )
            return None
        except Exception as e:
            logger.error(
                "repository.previous_artifact.fetch_failed",
                chart_type=chart_type,
                error=str(e),
            )
            raise

    async def get_current_artifact_id(self, chart_type: str) -> Optional[str]:
        """Get current artifact ID.

        Args:
            chart_type: 'helm' or 'compose'

        Returns:
            Artifact ID if found, None otherwise
        """
        query = """
            SELECT id FROM release_artifact
            WHERE is_current = TRUE
            AND chart_type = $1
            LIMIT 1
        """
        try:
            artifact_id = await self.pool.fetchval(query, chart_type)
            return str(artifact_id) if artifact_id else None
        except Exception as e:
            logger.error(
                "repository.current_artifact_id.fetch_failed",
                chart_type=chart_type,
                error=str(e),
            )
            raise

    async def update_artifact_flags(
        self, new_current_id: str, old_current_id: Optional[str], chart_type: str
    ):
        """Update isCurrent and isPrevious flags after successful deployment.

        Args:
            new_current_id: New current artifact ID
            old_current_id: Old current artifact ID (becomes previous)
            chart_type: 'helm' or 'compose'
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # Clear all current/previous flags for this chart type
                    await conn.execute(
                        """
                        UPDATE release_artifact
                        SET is_current = FALSE, is_previous = FALSE
                        WHERE chart_type = $1
                        """,
                        chart_type,
                    )

                    # Mark old current as previous
                    if old_current_id:
                        await conn.execute(
                            """
                            UPDATE release_artifact
                            SET is_previous = TRUE
                            WHERE id = $1
                            """,
                            old_current_id,
                        )

                    # Mark new as current
                    await conn.execute(
                        """
                        UPDATE release_artifact
                        SET is_current = TRUE,
                            is_previous = FALSE,
                            applied_at = NOW()
                        WHERE id = $1
                        """,
                        new_current_id,
                    )

                    logger.info(
                        "repository.artifact_flags.updated",
                        new_current_id=new_current_id,
                        old_current_id=old_current_id,
                    )
                except Exception as e:
                    logger.error(
                        "repository.artifact_flags.update_failed", error=str(e)
                    )
                    raise

    async def get_active_admins(self) -> List[Admin]:
        """Get all active admin emails for notifications.

        Returns:
            List of Admin objects
        """
        query = """
            SELECT id, name, email, is_active, role, created_at, updated_at
            FROM admin
            WHERE is_active = TRUE
        """
        try:
            rows = await self.pool.fetch(query)
            admins = []
            for row in rows:
                admin_dict = dict(row)
                # Convert UUID to string
                if admin_dict.get("id"):
                    admin_dict["id"] = str(admin_dict["id"])
                admins.append(Admin(**admin_dict))
            logger.info("repository.admins.fetched", count=len(admins))
            return admins
        except Exception as e:
            logger.error("repository.admins.fetch_failed", error=str(e))
            raise

    async def get_smtp_config(self) -> Dict:
        """Get SMTP configuration from deployment_config.

        Returns:
            Dict with SMTP settings
        """
        query = """
            SELECT smtp_host, smtp_port, smtp_user, smtp_password, smtp_from
            FROM deployment_config
            LIMIT 1
        """
        try:
            row = await self.pool.fetchrow(query)
            if row:
                config = dict(row)
                logger.info("repository.smtp_config.fetched")
                return config
            logger.warning("repository.smtp_config.not_found")
            return {}
        except Exception as e:
            logger.error("repository.smtp_config.fetch_failed", error=str(e))
            raise

    async def update_last_agent_poll(self):
        """Update last agent poll timestamp in deployment_config."""
        try:
            await self.pool.execute(
                "UPDATE deployment_config SET last_agent_poll = NOW()"
            )
            logger.debug("repository.agent_poll.updated")
        except Exception as e:
            logger.warning("repository.agent_poll.update_failed", error=str(e))

    async def get_maintenance_mode(self) -> bool:
        """Check if maintenance mode is enabled.

        Returns:
            True if enabled, False otherwise
        """
        try:
            enabled = await self.pool.fetchval(
                "SELECT maintenance_mode_enabled FROM deployment_config LIMIT 1"
            )
            return enabled or False
        except Exception as e:
            logger.error("repository.maintenance_mode.fetch_failed", error=str(e))
            return False

    async def set_maintenance_mode(self, enabled: bool):
        """Enable/disable maintenance mode.

        Args:
            enabled: True to enable, False to disable
        """
        try:
            await self.pool.execute(
                "UPDATE deployment_config SET maintenance_mode_enabled = $1",
                enabled,
            )
            logger.info("repository.maintenance_mode.updated", enabled=enabled)
        except Exception as e:
            logger.error(
                "repository.maintenance_mode.update_failed",
                enabled=enabled,
                error=str(e),
            )

    async def get_non_essential_envs(self) -> List[ServerEnv]:
        """Get active non-essential environment variables.

        Returns:
            List of ServerEnv objects
        """
        query = """
            SELECT * FROM server_env
            WHERE is_active = TRUE
        """
        try:
            rows = await self.pool.fetch(query)
            envs = []
            for row in rows:
                env_dict = dict(row)
                # Convert UUID to string
                if env_dict.get("id"):
                    env_dict["id"] = str(env_dict["id"])
                envs.append(ServerEnv(**env_dict))
            logger.debug("repository.server_envs.fetched", count=len(envs))
            return envs
        except Exception as e:
            logger.error("repository.server_envs.fetch_failed", error=str(e))
            raise

    async def get_deployment_config(self) -> Optional[DeploymentConfig]:
        """Get deployment configuration.

        Returns:
            DeploymentConfig if found, None otherwise
        """
        query = "SELECT * FROM deployment_config LIMIT 1"
        try:
            row = await self.pool.fetchrow(query)
            if row:
                config_dict = dict(row)
                # Convert UUID to string
                if config_dict.get("id"):
                    config_dict["id"] = str(config_dict["id"])
                logger.info("repository.deployment_config.fetched")
                return DeploymentConfig(**config_dict)
            logger.warning("repository.deployment_config.not_found")
            return None
        except Exception as e:
            logger.error("repository.deployment_config.fetch_failed", error=str(e))
            raise
