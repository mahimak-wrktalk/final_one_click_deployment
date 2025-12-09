"""Mock Backend API server for testing the agent."""

from fastapi import FastAPI, Header, HTTPException
from typing import Optional, List, Dict, Any
import uvicorn
from datetime import datetime
from pydantic import BaseModel

app = FastAPI(title="Mock WrkTalk Backend")

# In-memory task queue
task_queue: List[Dict[str, Any]] = []
task_statuses: Dict[str, Dict[str, Any]] = {}
config_store: Dict[str, str] = {}


class TaskStatus(BaseModel):
    """Task status update model."""
    status: str
    pickedUpAt: Optional[str] = None
    completedAt: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    errorMessage: Optional[str] = None


class ConfigEntry(BaseModel):
    """Config entry model."""
    key: str
    value: str


@app.get("/internal/agent/tasks")
async def get_tasks(x_agent_secret: str = Header(None)):
    """Get pending task for agent."""
    if x_agent_secret != "agent-secret-key":
        raise HTTPException(status_code=401, detail="Invalid agent secret")

    if not task_queue:
        return {"task": None}

    # Return first pending task
    for task in task_queue:
        if task_statuses.get(task["id"], {}).get("status") != "completed":
            print(f"[{datetime.now()}] Returning task: {task['id']}")
            return {"task": task}

    return {"task": None}


@app.post("/internal/agent/tasks/{task_id}/status")
async def update_status(
    task_id: str,
    status_update: TaskStatus,
    x_agent_secret: str = Header(None)
):
    """Update task status."""
    if x_agent_secret != "agent-secret-key":
        raise HTTPException(status_code=401, detail="Invalid agent secret")

    task_statuses[task_id] = status_update.dict()
    print(f"[{datetime.now()}] Task {task_id} status: {status_update.status}")

    if status_update.result:
        print(f"  Result: {status_update.result}")
    if status_update.errorMessage:
        print(f"  Error: {status_update.errorMessage}")

    # Remove from queue if completed or failed
    if status_update.status in ["completed", "failed"]:
        global task_queue
        task_queue = [t for t in task_queue if t["id"] != task_id]
        print(f"  Task removed from queue. Remaining: {len(task_queue)}")

    return {"success": True}


@app.post("/internal/agent/tasks/{task_id}/heartbeat")
async def heartbeat(task_id: str, x_agent_secret: str = Header(None)):
    """Receive task heartbeat."""
    if x_agent_secret != "agent-secret-key":
        raise HTTPException(status_code=401, detail="Invalid agent secret")

    print(f"[{datetime.now()}] ❤️  Heartbeat from task {task_id}")
    return {"received": True}


@app.post("/internal/config")
async def insert_config(
    config: ConfigEntry,
    x_agent_secret: str = Header(None)
):
    """Insert non-essential config."""
    if x_agent_secret != "agent-secret-key":
        raise HTTPException(status_code=401, detail="Invalid agent secret")

    config_store[config.key] = config.value
    print(f"[{datetime.now()}] Config inserted: {config.key}={config.value}")
    return {"created": True}


# ============================================================================
# Test Helpers - Not part of real API
# ============================================================================

@app.post("/test/add-task")
async def add_task(task: dict):
    """Add a test task to the queue."""
    task_queue.append(task)
    task_statuses[task["id"]] = {"status": "pending"}
    print(f"\n[{datetime.now()}] 📝 Task added: {task['id']}")
    print(f"  Type: {task['type']}")
    print(f"  Total tasks in queue: {len(task_queue)}\n")
    return {"queued": True, "task_id": task["id"]}


@app.get("/test/tasks")
async def list_tasks():
    """List all tasks and their statuses."""
    return {
        "queue": task_queue,
        "statuses": task_statuses,
        "total": len(task_queue)
    }


@app.get("/test/config")
async def list_config():
    """List all stored config."""
    return config_store


@app.delete("/test/clear")
async def clear_all():
    """Clear all tasks and state."""
    global task_queue, task_statuses, config_store
    task_queue = []
    task_statuses = {}
    config_store = {}
    print(f"[{datetime.now()}] 🧹 All data cleared")
    return {"cleared": True}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Mock WrkTalk Backend",
        "version": "1.0.0",
        "tasks_in_queue": len(task_queue),
        "endpoints": {
            "agent": {
                "get_tasks": "GET /internal/agent/tasks",
                "update_status": "POST /internal/agent/tasks/{task_id}/status",
                "heartbeat": "POST /internal/agent/tasks/{task_id}/heartbeat",
                "insert_config": "POST /internal/config"
            },
            "test": {
                "add_task": "POST /test/add-task",
                "list_tasks": "GET /test/tasks",
                "list_config": "GET /test/config",
                "clear": "DELETE /test/clear"
            }
        }
    }


if __name__ == "__main__":
    print("=" * 70)
    print("Mock WrkTalk Backend Server")
    print("=" * 70)
    print("Starting on http://localhost:3000")
    print("\nEndpoints:")
    print("  - GET  /                            - API info")
    print("  - POST /test/add-task               - Add test task")
    print("  - GET  /test/tasks                  - List all tasks")
    print("  - GET  /test/config                 - List config store")
    print("  - DELETE /test/clear                - Clear all data")
    print("\nAgent endpoints:")
    print("  - GET  /internal/agent/tasks        - Poll for tasks")
    print("  - POST /internal/agent/tasks/{id}/status - Update status")
    print("  - POST /internal/agent/tasks/{id}/heartbeat - Heartbeat")
    print("=" * 70)
    print()

    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
