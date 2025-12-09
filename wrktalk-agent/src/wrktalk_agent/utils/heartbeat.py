"""Heartbeat thread for keeping long-running tasks alive."""

import asyncio
import threading
import time
from typing import Optional

import structlog

logger = structlog.get_logger()


class HeartbeatThread:
    """Background thread to send task heartbeats during long-running operations."""

    def __init__(self, backend, task_id: str, interval: int = 60):
        """Initialize heartbeat thread.

        Args:
            backend: BackendClient instance
            task_id: Task ID to send heartbeats for
            interval: Heartbeat interval in seconds
        """
        self.backend = backend
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
            self._stop_event.wait(self.interval)

            if not self._stop_event.is_set():
                try:
                    # Run async call in sync context
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.backend.send_heartbeat(self.task_id))
                    loop.close()
                    logger.debug("heartbeat.sent", task_id=self.task_id)
                except Exception as e:
                    logger.warning(
                        "heartbeat.failed", task_id=self.task_id, error=str(e)
                    )
