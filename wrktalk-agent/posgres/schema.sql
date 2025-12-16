-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Agent Task Queue
CREATE TABLE agent_task (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(50) NOT NULL,  -- 'deploy' or 'rollback'
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- 'pending', 'inProgress', 'completed', 'failed'
    release_artifact_id UUID,
    execute_after TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    picked_up_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    result JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Release Artifacts (with BYTEA for tarball storage)
CREATE TABLE release_artifact (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    release_version VARCHAR(100) NOT NULL,
    chart_type VARCHAR(20) NOT NULL,  -- 'helm' or 'compose'
    artifact_data BYTEA NOT NULL,  -- Tarball bytes
    env_data TEXT,  -- .env content for Docker Compose
    values_data TEXT,  -- values.yaml content for Kubernetes
    sha256 VARCHAR(64) NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    is_previous BOOLEAN DEFAULT FALSE,
    downloaded_at TIMESTAMP WITH TIME ZONE,
    prepared_at TIMESTAMP WITH TIME ZONE,
    applied_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Admin Users (for email notifications)
CREATE TABLE admin (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255),
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    role VARCHAR(50) NOT NULL DEFAULT 'ADMIN',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    profile_image_url VARCHAR(500)
);

-- Server Environment Variables
CREATE TABLE server_env (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by VARCHAR(255)
);

-- Deployment Configuration
CREATE TABLE deployment_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    deployment_type VARCHAR(20) NOT NULL,  -- 'kubernetes' or 'docker'
    namespace VARCHAR(100),
    helm_release_name VARCHAR(100),
    compose_project_name VARCHAR(100),
    maintenance_mode_enabled BOOLEAN DEFAULT FALSE,
    last_agent_poll TIMESTAMP WITH TIME ZONE,
    smtp_host VARCHAR(255),
    smtp_port INTEGER,
    smtp_user VARCHAR(255),
    smtp_password VARCHAR(255),
    smtp_from VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add foreign key constraint
ALTER TABLE agent_task ADD CONSTRAINT fk_release_artifact 
    FOREIGN KEY (release_artifact_id) REFERENCES release_artifact(id);

-- Create indexes for performance
CREATE INDEX idx_agent_task_status ON agent_task(status);
CREATE INDEX idx_agent_task_execute_after ON agent_task(execute_after);
CREATE INDEX idx_release_artifact_current ON release_artifact(is_current, chart_type);
CREATE INDEX idx_release_artifact_previous ON release_artifact(is_previous, chart_type);
