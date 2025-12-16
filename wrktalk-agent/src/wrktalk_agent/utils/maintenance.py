"""Maintenance mode handler for controlling nginx/haproxy during deployments."""

import subprocess
import structlog
from typing import Literal

logger = structlog.get_logger()


class MaintenanceHandler:
    """Controls nginx/haproxy to return 503 during deployments."""

    def __init__(self, mode: Literal["nginx", "haproxy"] = "nginx"):
        """Initialize maintenance handler.

        Args:
            mode: Handler mode ('nginx' or 'haproxy')
        """
        self.mode = mode
        self.maintenance_flag = "/tmp/maintenance-mode"

    async def enable(self):
        """Enable maintenance mode - return 503 for incoming requests."""
        try:
            if self.mode == "nginx":
                await self._enable_nginx()
            elif self.mode == "haproxy":
                await self._enable_haproxy()

            logger.info("maintenance.enabled", mode=self.mode)
        except Exception as e:
            logger.error("maintenance.enable_failed", mode=self.mode, error=str(e))
            # Don't raise - maintenance mode is non-critical

    async def disable(self):
        """Disable maintenance mode - resume normal traffic."""
        try:
            if self.mode == "nginx":
                await self._disable_nginx()
            elif self.mode == "haproxy":
                await self._disable_haproxy()

            logger.info("maintenance.disabled", mode=self.mode)
        except Exception as e:
            logger.error("maintenance.disable_failed", mode=self.mode, error=str(e))
            # Don't raise - maintenance mode is non-critical

    async def _enable_nginx(self):
        """Enable nginx maintenance mode by creating a flag file.

        This assumes nginx configuration checks for the flag file and returns 503:

        location / {
            if (-f /tmp/maintenance-mode) {
                return 503;
            }
            # ... normal config
        }
        """
        result = subprocess.run(
            ["touch", self.maintenance_flag],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "maintenance.nginx.flag_create_failed",
                stderr=result.stderr,
            )
            return

        # Reload nginx to pick up change
        result = subprocess.run(
            ["nginx", "-s", "reload"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "maintenance.nginx.reload_failed",
                stderr=result.stderr,
            )

    async def _disable_nginx(self):
        """Disable nginx maintenance mode by removing the flag file."""
        result = subprocess.run(
            ["rm", "-f", self.maintenance_flag],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "maintenance.nginx.flag_remove_failed",
                stderr=result.stderr,
            )
            return

        # Reload nginx to pick up change
        result = subprocess.run(
            ["nginx", "-s", "reload"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "maintenance.nginx.reload_failed",
                stderr=result.stderr,
            )

    async def _enable_haproxy(self):
        """Enable haproxy maintenance mode.

        This assumes haproxy checks for a flag file in its configuration.
        Implementation depends on specific haproxy setup.
        """
        # Create maintenance flag
        result = subprocess.run(
            ["touch", self.maintenance_flag],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "maintenance.haproxy.flag_create_failed",
                stderr=result.stderr,
            )
            return

        # Reload haproxy (command may vary)
        # Note: This is a placeholder - adjust based on actual haproxy setup
        logger.info("maintenance.haproxy.enabled_via_flag")

    async def _disable_haproxy(self):
        """Disable haproxy maintenance mode.

        This assumes haproxy checks for a flag file in its configuration.
        Implementation depends on specific haproxy setup.
        """
        # Remove maintenance flag
        result = subprocess.run(
            ["rm", "-f", self.maintenance_flag],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "maintenance.haproxy.flag_remove_failed",
                stderr=result.stderr,
            )
            return

        logger.info("maintenance.haproxy.disabled_via_flag")
