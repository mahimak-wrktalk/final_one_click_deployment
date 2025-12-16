"""Heartbeat thread for keeping long-running tasks alive."""

import asyncio
import threading
from typing import Optional

import structlog

logger = structlog.get_logger()


class HeartbeatThread:
    """Background thread to send task heartbeats during long-running operations."""

    def __init__(self, repo, task_id: str, interval: int = 60):
        """Initialize heartbeat thread.

        Args:
            repo: AgentRepository instance (replaces BackendClient)
            task_id: Task ID to send heartbeats for
            interval: Heartbeat interval in seconds
        """
        self.repo = repo
        self.task_id = task_id
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the heartbeat thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.debug("heartbeat.started", task_id=self.task_id)

    def stop(self):
        """Stop the heartbeat thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.debug("heartbeat.stopped", task_id=self.task_id)

    def _run(self):
        """Heartbeat loop running in background thread."""
        while not self._stop_event.is_set():
            # Wait for interval or until stop event is set
            if self._stop_event.wait(self.interval):
                break  # Stop event was set during wait

            try:
                # Use asyncio.run() which properly manages event loop lifecycle
                asyncio.run(self.repo.update_heartbeat(self.task_id))
                logger.debug("heartbeat.sent", task_id=self.task_id)
            except Exception as e:
                logger.warning(
                    "heartbeat.failed", task_id=self.task_id, error=str(e)
                )
