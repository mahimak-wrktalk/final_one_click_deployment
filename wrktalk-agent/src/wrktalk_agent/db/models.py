"""Pydantic models for database records."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel


class TaskStatus(str, Enum):
    """Agent task status."""

    PENDING = "pending"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(str, Enum):
    """Agent task type."""

    DEPLOY = "deploy"
    ROLLBACK = "rollback"


class AgentTask(BaseModel):
    """Agent task from database."""

    id: str
    type: TaskType
    status: TaskStatus
    release_artifact_id: Optional[str] = None
    execute_after: datetime
    picked_up_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        use_enum_values = True


class ReleaseArtifact(BaseModel):
    """Release artifact from database."""

    id: str
    release_version: str
    chart_type: str  # 'helm' or 'compose'
    artifact_data: bytes  # Tarball bytes from BYTEA column
    env_data: Optional[str] = None  # .env content for Docker Compose
    values_data: Optional[str] = None  # values.yaml content for Kubernetes
    sha256: str
    is_current: bool
    is_previous: bool
    downloaded_at: Optional[datetime] = None
    prepared_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    created_at: datetime


class Admin(BaseModel):
    """Admin user for email notifications."""

    id: str
    name: Optional[str] = None
    email: str
    is_active: bool
    role: str
    created_at: datetime
    updated_at: datetime


class ServerEnv(BaseModel):
    """Non-essential environment variable from database."""

    id: str
    key: str
    value: str
    category: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DeploymentConfig(BaseModel):
    """Deployment configuration from database."""

    id: str
    deployment_type: str  # 'kubernetes' or 'docker'
    namespace: Optional[str] = None  # For K8s
    helm_release_name: Optional[str] = None  # For K8s
    compose_project_name: Optional[str] = None  # For Docker
    maintenance_mode_enabled: bool
    last_agent_poll: Optional[datetime] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    created_at: datetime
    updated_at: datetime
