"""Database connection pool management using asyncpg."""

import asyncpg
import structlog
from typing import Optional

logger = structlog.get_logger()


class DatabasePool:
    """Manages PostgreSQL connection pool for agent operations."""

    def __init__(self, dsn: str):
        """Initialize database pool.

        Args:
            dsn: PostgreSQL connection string (postgresql://user:pass@host:port/db)
        """
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create and initialize connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            logger.info("database.pool.connected", dsn=self._safe_dsn())
        except Exception as e:
            logger.error("database.pool.connect_failed", error=str(e))
            raise

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("database.pool.closed")

    def _safe_dsn(self) -> str:
        """Return DSN with password masked for logging."""
        if "@" in self.dsn:
            parts = self.dsn.split("@")
            creds = parts[0].split("://")[1]
            if ":" in creds:
                user = creds.split(":")[0]
                return self.dsn.replace(creds, f"{user}:***")
        return self.dsn
