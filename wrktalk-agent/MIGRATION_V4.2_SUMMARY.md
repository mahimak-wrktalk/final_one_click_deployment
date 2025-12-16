# WrkTalk Agent v4.2 - PostgreSQL Migration Summary

## Overview

Successfully refactored wrktalk-agent from HTTP/MinIO-based polling to **direct PostgreSQL database polling** as specified in `WrkTalk_Deployment_HighLevel_v5.md`.

---

## Architecture Changes

### Before (v1.x)
```
Agent → HTTP Poll → Backend API → Backend manages DB → MinIO for artifacts
```

### After (v4.2)
```
Agent → Direct PostgreSQL Poll → Read artifacts from DB → SMTP notifications
```

---

## Files Created

### 1. Database Layer (`src/wrktalk_agent/db/`)

#### `db/__init__.py`
- Package initialization with exports

#### `db/connection.py`
- **DatabasePool** class using asyncpg
- Connection pool management (min=2, max=10)
- Automatic DSN password masking for logs

#### `db/models.py`
- **Pydantic models** for database records:
  - `AgentTask` - Task queue model
  - `ReleaseArtifact` - Artifact with BYTEA data
  - `Admin` - Admin users for email notifications
  - `ServerEnv` - Non-essential environment variables
  - `DeploymentConfig` - Deployment configuration
  - `TaskStatus` enum (pending, inProgress, completed, failed)
  - `TaskType` enum (deploy, rollback)

#### `db/repository.py`
- **AgentRepository** class with database operations:
  - `get_pending_task()` - Atomic task picking with `FOR UPDATE SKIP LOCKED`
  - `update_task_status()` - Update task status and result
  - `update_heartbeat()` - Update last heartbeat timestamp
  - `get_artifact()` - Fetch artifact with tarball bytes from BYTEA
  - `get_previous_artifact()` - Get previous version for rollback
  - `update_artifact_flags()` - Update isCurrent/isPrevious flags
  - `get_active_admins()` - Get admin emails for notifications
  - `get_smtp_config()` - Get SMTP settings from database
  - `update_last_agent_poll()` - Track agent polling
  - `get_maintenance_mode()` / `set_maintenance_mode()` - Maintenance mode control

### 2. Email Client (`src/wrktalk_agent/client/email.py`)

- **EmailClient** class for SMTP notifications
- HTML email templates for:
  - ✅ Deployment SUCCESS
  - ❌ Deployment FAILED
  - 🔄 Rollback SUCCESS
  - ⚠️ Rollback FAILED
- Uses smtplib with TLS
- Configuration loaded from database

### 3. Maintenance Mode Handler (`src/wrktalk_agent/utils/maintenance.py`)

- **MaintenanceHandler** class
- Controls nginx/haproxy to return 503 during deployments
- Creates `/tmp/maintenance-mode` flag file
- Supports both nginx and haproxy modes

---

## Files Modified

### 1. `src/wrktalk_agent/config.py`
**Changes:**
- ❌ Removed: `backend_url`, `agent_secret`, `backend_timeout`
- ❌ Removed: `minio_endpoint`, `minio_access_key`, `minio_secret_key`, `minio_bucket_name`, `minio_secure`
- ✅ Added: `db_host`, `db_port`, `db_name`, `db_user`, `db_password`, `db_ssl_mode`
- ✅ Added: `maintenance_mode_handler`
- ✅ Added: `database_url` property (constructs PostgreSQL DSN)

### 2. `src/wrktalk_agent/agent.py`
**Major Refactor:**
- ❌ Removed: `BackendClient` and `MinIOClient` initialization
- ✅ Added: `DatabasePool`, `AgentRepository`, `EmailClient`, `MaintenanceHandler`
- ✅ Modified: `start()` - Initialize database connection and SMTP config
- ✅ Modified: `_poll_and_execute()` - Use `repo.get_pending_task()` instead of HTTP
- ✅ Modified: `_execute_deployment()`:
  - Download artifacts from PostgreSQL BYTEA instead of MinIO
  - Extract tarball bytes to temp directory
  - Enable/disable maintenance mode
  - Update artifact flags after successful deployment
  - Send email notifications on success/failure
- ✅ Modified: `_execute_rollback()`:
  - Get previous artifact from database
  - Kubernetes: Use Helm rollback
  - Docker: Re-deploy previous version from database
- ✅ Added: `_send_notification()` - Send emails to active admins
- ✅ Added: `_secure_delete_directory()` - Securely delete temp directories

### 3. `src/wrktalk_agent/utils/heartbeat.py`
**Changes:**
- ❌ Removed: `backend` parameter (BackendClient)
- ✅ Added: `repo` parameter (AgentRepository)
- ✅ Fixed: Use `asyncio.run()` instead of manual event loop management
- ✅ Fixed: Proper stop event handling in `_run()`

### 4. `requirements.txt`
**Changes:**
- ❌ Removed: `httpx==0.25.2` (no longer needed)
- ❌ Removed: `minio==7.2.0` (no longer needed)
- ❌ Removed: `asyncio==3.4.3` (built-in to Python 3.11)
- ✅ Added: `asyncpg==0.29.0` (PostgreSQL driver)
- ✅ Kept: `pydantic`, `pydantic-settings`, `structlog`, `typing-extensions`

### 5. `Dockerfile.kubernetes`
**Changes:**
- ✅ Added: Docker Compose CLI installation (for single image strategy)
- ✅ Removed: Hardcoded `ENV WRKTALK_AGENT_DEPLOYMENT_TYPE=kubernetes`
- Now supports both Kubernetes and Docker environments with same image

### 6. `k8s/agent-deployment.yaml`
**Changes:**
- ❌ Removed: `WRKTALK_AGENT_BACKEND_URL`, `WRKTALK_AGENT_AGENT_SECRET`, `WRKTALK_AGENT_BACKEND_TIMEOUT`
- ❌ Removed: `WRKTALK_AGENT_MINIO_*` environment variables
- ✅ Added: Database configuration:
  - `WRKTALK_AGENT_DB_HOST`
  - `WRKTALK_AGENT_DB_PORT`
  - `WRKTALK_AGENT_DB_NAME`
  - `WRKTALK_AGENT_DB_USER`
  - `WRKTALK_AGENT_DB_PASSWORD`
  - `WRKTALK_AGENT_DB_SSL_MODE`
- ✅ Added: `WRKTALK_AGENT_MAINTENANCE_MODE_HANDLER`

### 7. `src/wrktalk_agent/client/__init__.py`
**Changes:**
- ✅ Updated exports to only include `EmailClient`

---

## Files Deleted

1. ❌ `src/wrktalk_agent/client/backend.py` - HTTP client (obsolete)
2. ❌ `src/wrktalk_agent/client/bucket.py` - MinIO client (obsolete)

---

## Key Features Implemented

### ✅ 1. Direct PostgreSQL Polling
- Agent polls `agent_task` table directly
- Uses `FOR UPDATE SKIP LOCKED` for atomic task picking
- Multiple agents can run concurrently without conflicts

### ✅ 2. Artifacts from Database
- Tarballs stored in `release_artifact.artifact_data` (BYTEA column)
- `env_data` and `values_data` stored as TEXT
- Extracted to temporary directory for deployment
- Securely deleted after use

### ✅ 3. Email Notifications
- Agent sends notifications directly via SMTP
- SUCCESS, FAILED, ROLLBACK_SUCCESS, ROLLBACK_FAILED statuses
- HTML email templates with task details
- Notifies all active admins from database

### ✅ 4. Maintenance Mode
- Controls nginx/haproxy during deployments
- Returns 503 to clients during updates
- Automatically enabled before deployment, disabled after

### ✅ 5. Heartbeat Thread
- Updates `agent_task.last_heartbeat` every 60 seconds
- Uses database instead of HTTP
- Fixed event loop issue with `asyncio.run()`

### ✅ 6. Rollback Support
- **Kubernetes**: Uses Helm rollback with history
- **Docker**: Re-deploys previous version from database
- Works even when Backend is DOWN (only needs PostgreSQL)

### ✅ 7. Single Docker Image
- Includes both Helm CLI and docker-compose CLI
- Same image for Kubernetes and Docker environments
- Deployment type configured via environment variable

### ✅ 8. Structured Logging
- Preserved existing structlog implementation
- All database operations logged
- Email notifications logged

---

## Database Schema Used

### `agent_task`
```sql
- id (UUID)
- type (VARCHAR) - 'deploy' or 'rollback'
- status (VARCHAR) - 'pending', 'inProgress', 'completed', 'failed'
- release_artifact_id (UUID FK)
- execute_after (TIMESTAMP)
- picked_up_at (TIMESTAMP)
- completed_at (TIMESTAMP)
- last_heartbeat (TIMESTAMP)
- result (JSONB)
- error_message (TEXT)
```

### `release_artifact`
```sql
- id (UUID)
- release_version (VARCHAR)
- chart_type (VARCHAR) - 'helm' or 'compose'
- artifact_data (BYTEA) ⭐ Tarball bytes
- env_data (TEXT) - .env content
- values_data (TEXT) - values.yaml content
- sha256 (VARCHAR)
- is_current (BOOLEAN)
- is_previous (BOOLEAN)
- applied_at (TIMESTAMP)
```

### `admin`
```sql
- id (UUID)
- name (VARCHAR)
- email (VARCHAR) ⭐ For notifications
- is_active (BOOLEAN)
- role (VARCHAR)
```

### `deployment_config`
```sql
- smtp_host (VARCHAR)
- smtp_port (INTEGER)
- smtp_user (VARCHAR)
- smtp_password (VARCHAR)
- smtp_from (VARCHAR)
- maintenance_mode_enabled (BOOLEAN)
- last_agent_poll (TIMESTAMP)
```

---

## Environment Variables

### Required (Database)
```bash
WRKTALK_AGENT_DB_HOST=localhost
WRKTALK_AGENT_DB_PORT=5432
WRKTALK_AGENT_DB_NAME=wrktalk
WRKTALK_AGENT_DB_USER=postgres
WRKTALK_AGENT_DB_PASSWORD=password
WRKTALK_AGENT_DB_SSL_MODE=prefer
```

### Required (Deployment)
```bash
WRKTALK_AGENT_DEPLOYMENT_TYPE=kubernetes  # or 'docker'
```

### Optional (Kubernetes)
```bash
WRKTALK_AGENT_KUBE_NAMESPACE=wrktalk
WRKTALK_AGENT_HELM_RELEASE_NAME=wrktalk
WRKTALK_AGENT_HELM_TIMEOUT=10m
```

### Optional (Docker Compose)
```bash
WRKTALK_AGENT_COMPOSE_PROJECT_NAME=wrktalk
WRKTALK_AGENT_COMPOSE_WORKING_DIR=/tmp/wrktalk
```

### Optional (Agent Settings)
```bash
WRKTALK_AGENT_POLL_INTERVAL=30
WRKTALK_AGENT_HEARTBEAT_INTERVAL=60
WRKTALK_AGENT_MAINTENANCE_MODE_HANDLER=nginx  # or 'haproxy'
WRKTALK_AGENT_LOG_LEVEL=INFO
```

---

## Testing Checklist

### Prerequisites
- [ ] PostgreSQL database running with schema
- [ ] Database populated with:
  - `deployment_config` with SMTP settings
  - `admin` table with active admins
  - `release_artifact` with test artifact (BYTEA data)
  - `agent_task` with pending task

### Test Steps
1. [ ] Agent starts and connects to database
2. [ ] Agent loads SMTP configuration
3. [ ] Agent polls and picks up pending task
4. [ ] Heartbeat updates every 60 seconds
5. [ ] Artifact extracted from BYTEA column
6. [ ] Maintenance mode enabled/disabled
7. [ ] Deployment executes successfully
8. [ ] Artifact flags updated (isCurrent, isPrevious)
9. [ ] Email notification sent to admins
10. [ ] Task status updated to completed
11. [ ] Temp files securely deleted

### Rollback Test
1. [ ] Create rollback task
2. [ ] Agent fetches previous artifact from database
3. [ ] Rollback executes (Helm or Docker)
4. [ ] Email notification sent
5. [ ] Task status updated

---

## Migration Steps from v1.x

### 1. Database Setup
```sql
-- Ensure schema exists (from WrkTalk_Deployment_HighLevel_v5.md)
-- Insert SMTP configuration
INSERT INTO deployment_config (
    id, deployment_type, smtp_host, smtp_port,
    smtp_user, smtp_password, smtp_from
) VALUES (
    gen_random_uuid(), 'kubernetes', 'smtp.gmail.com', 587,
    'user@gmail.com', 'password', 'noreply@wrktalk.com'
);

-- Ensure admin users exist
INSERT INTO admin (id, email, is_active, role) VALUES
    (gen_random_uuid(), 'admin@wrktalk.com', true, 'ADMIN');
```

### 2. Update Environment Variables
- Remove: `BACKEND_URL`, `AGENT_SECRET`, `MINIO_*`
- Add: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

### 3. Rebuild Docker Image
```bash
docker build -f Dockerfile.kubernetes -t wrktalk-agent:v4.2 .
```

### 4. Deploy
```bash
# Update k8s/agent-deployment.yaml with new ConfigMap
kubectl apply -f k8s/agent-deployment.yaml
```

---

## Breaking Changes

1. **No HTTP Backend Client** - Agent no longer calls Backend API
2. **No MinIO Client** - Artifacts must be in PostgreSQL BYTEA
3. **Email Configuration** - Must be in `deployment_config` table
4. **Environment Variables** - Database config required instead of Backend/MinIO

---

## Backward Compatibility

❌ **NOT backward compatible with v1.x**

This is a major architectural change. You cannot mix v1.x and v4.2 agents.

---

## License Validation

✅ **Removed as requested by user**

No license validation code included in v4.2.

---

## Next Steps

1. Test agent with PostgreSQL database
2. Verify email notifications working
3. Test both Kubernetes and Docker deployment modes
4. Test rollback scenarios
5. Monitor heartbeat updates in database
6. Test maintenance mode with nginx/haproxy

---

## References

- Architecture Spec: `WrkTalk_Deployment_HighLevel_v5.md`
- Database Schema: See sections in spec document
- Plan Document: `~/.claude/plans/synchronous-rolling-micali.md`
