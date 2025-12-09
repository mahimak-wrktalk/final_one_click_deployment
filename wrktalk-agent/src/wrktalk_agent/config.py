"""Configuration module for WrkTalk Agent."""

from enum import Enum
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class DeploymentType(str, Enum):
    """Deployment environment type."""
    KUBERNETES = "kubernetes"
    DOCKER = "docker"


class AgentConfig(BaseSettings):
    """Agent configuration from environment variables."""

    # Backend connection
    backend_url: str = Field(
        default="http://localhost:3000",
        description="WrkTalk Backend URL"
    )
    backend_timeout: int = Field(
        default=30,
        description="HTTP timeout in seconds"
    )
    agent_secret: str = Field(
        default="agent-secret-key",
        description="Secret key for authenticating with Backend"
    )
    poll_interval: int = Field(
        default=30,
        description="Poll interval in seconds"
    )

    # Deployment type
    deployment_type: DeploymentType = Field(
        default=DeploymentType.KUBERNETES,
        description="Deployment environment (kubernetes or docker)"
    )

    # Kubernetes settings
    kube_namespace: str = Field(
        default="wrktalk",
        description="Kubernetes namespace"
    )
    helm_release_name: str = Field(
        default="wrktalk",
        description="Helm release name"
    )
    helm_timeout: str = Field(
        default="10m",
        description="Helm operation timeout"
    )

    # Docker Compose settings
    compose_project_name: str = Field(
        default="wrktalk",
        description="Docker Compose project name"
    )
    compose_working_dir: str = Field(
        default="/tmp/wrktalk",
        description="Docker Compose working directory"
    )

    # MinIO settings
    minio_endpoint: str = Field(
        default="localhost:9000",
        description="MinIO endpoint (without http://)"
    )
    minio_access_key: str = Field(
        default="admin",
        description="MinIO access key"
    )
    minio_secret_key: str = Field(
        default="admin123",
        description="MinIO secret key"
    )
    minio_bucket_name: str = Field(
        default="wrktalk-artifacts",
        description="MinIO bucket name"
    )
    minio_secure: bool = Field(
        default=False,
        description="Use HTTPS for MinIO"
    )

    # Task heartbeat
    heartbeat_interval: int = Field(
        default=60,
        description="Task heartbeat interval in seconds"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    class Config:
        """Pydantic config."""
        env_prefix = "WRKTALK_AGENT_"
        case_sensitive = False
