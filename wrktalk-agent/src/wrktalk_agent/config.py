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

    # Database Configuration (NEW - replaces HTTP backend)
    db_host: str = Field(
        default="localhost",
        description="PostgreSQL host"
    )
    db_port: int = Field(
        default=5432,
        description="PostgreSQL port"
    )
    db_name: str = Field(
        default="wrktalk",
        description="PostgreSQL database name"
    )
    db_user: str = Field(
        default="postgres",
        description="PostgreSQL username"
    )
    db_password: str = Field(
        default="password",
        description="PostgreSQL password"
    )
    db_ssl_mode: str = Field(
        default="prefer",
        description="PostgreSQL SSL mode (disable, prefer, require)"
    )

    # Agent Settings
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

    # Task heartbeat
    heartbeat_interval: int = Field(
        default=60,
        description="Task heartbeat interval in seconds"
    )

    # Maintenance mode
    maintenance_mode_handler: str = Field(
        default="nginx",
        description="Maintenance mode handler (nginx or haproxy)"
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

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL.

        Returns:
            PostgreSQL DSN string
        """
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?sslmode={self.db_ssl_mode}"
        )
