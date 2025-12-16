# WrkTalk Agent v4.2 - PostgreSQL-Based Architecture

## Overview

WrkTalk Agent v4.2 is a complete architectural refactor that transitions from HTTP/MinIO-based polling to **direct PostgreSQL database polling**. The agent now reads artifacts from database BYTEA columns and sends deployment notifications via SMTP.

## Key Changes from v1.x

| Feature | v1.x | v4.2 |
|---------|------|------|
| Task Polling | HTTP REST API | PostgreSQL Direct |
| Artifact Storage | MinIO/S3 | PostgreSQL BYTEA |
| Status Updates | HTTP POST | PostgreSQL UPDATE |
| Heartbeat | HTTP POST | PostgreSQL UPDATE |
| Email Notifications | Backend sends | Agent sends via SMTP |
| Maintenance Mode | Not implemented | nginx/haproxy control |
| License Validation | Implemented | **Removed** |
| Docker Image | Separate images | **Single image** |
| Rollback Resilience | Depends on Backend | Works when Backend DOWN |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      WrkTalk Agent v4.2                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────────────────────┐
         │      PostgreSQL Database           │
         │  ┌──────────────────────────────┐  │
         │  │ agent_task (Task Queue)      │  │
         │  │ - id, type, status           │  │
         │  │ - release_artifact_id (FK)   │  │
         │  │ - execute_after, heartbeat   │  │
         │  └──────────────────────────────┘  │
         │  ┌──────────────────────────────┐  │
         │  │ release_artifact (Artifacts) │  │
         │  │ - artifact_data (BYTEA)      │  │  ⭐ Tarball bytes
         │  │ - env_data, values_data      │  │
         │  │ - is_current, is_previous    │  │
         │  └──────────────────────────────┘  │
         │  ┌──────────────────────────────┐  │
         │  │ admin (Email Recipients)     │  │
         │  │ - email, is_active           │  │
         │  └──────────────────────────────┘  │
         │  ┌──────────────────────────────┐  │
         │  │ deployment_config (SMTP)     │  │
         │  │ - smtp_host, smtp_user       │  │
         │  └──────────────────────────────┘  │
         └────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────────────────────┐
         │      Deployment Executors          │
         │  ┌─────────────┐  ┌─────────────┐  │
         │  │ Helm CLI    │  │ Compose CLI │  │
         │  └─────────────┘  └─────────────┘  │
         └────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────────────────────┐
         │      Email Notifications           │
         │  SMTP → Active Admins              │
         └────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ with WrkTalk schema
- Kubernetes cluster (for K8s deployments) OR Docker (for Compose deployments)
- SMTP server credentials

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database and deployment settings
```

### 3. Database Setup

Ensure your PostgreSQL database has the required tables:

```sql
-- Example: Insert SMTP configuration
INSERT INTO deployment_config (
    id, deployment_type, smtp_host, smtp_port,
    smtp_user, smtp_password, smtp_from,
    maintenance_mode_enabled
) VALUES (
    gen_random_uuid(), 'kubernetes', 'smtp.gmail.com', 587,
    'your-email@gmail.com', 'your-app-password', 'noreply@wrktalk.com',
    false
);

-- Example: Create admin user for notifications
INSERT INTO admin (id, email, is_active, role, name) VALUES
    (gen_random_uuid(), 'admin@example.com', true, 'ADMIN', 'Admin User');
```

### 4. Run Agent

```bash
python -m wrktalk_agent
```

## Configuration

### Environment Variables

#### Database (Required)
```bash
WRKTALK_AGENT_DB_HOST=localhost
WRKTALK_AGENT_DB_PORT=5432
WRKTALK_AGENT_DB_NAME=wrktalk
WRKTALK_AGENT_DB_USER=postgres
WRKTALK_AGENT_DB_PASSWORD=password
WRKTALK_AGENT_DB_SSL_MODE=prefer
```

#### Deployment Type (Required)
```bash
WRKTALK_AGENT_DEPLOYMENT_TYPE=kubernetes  # or 'docker'
```

#### Kubernetes Settings
```bash
WRKTALK_AGENT_KUBE_NAMESPACE=wrktalk
WRKTALK_AGENT_HELM_RELEASE_NAME=wrktalk
WRKTALK_AGENT_HELM_TIMEOUT=10m
```

#### Docker Compose Settings
```bash
WRKTALK_AGENT_COMPOSE_PROJECT_NAME=wrktalk
WRKTALK_AGENT_COMPOSE_WORKING_DIR=/tmp/wrktalk
```

#### Agent Settings
```bash
WRKTALK_AGENT_POLL_INTERVAL=30              # seconds
WRKTALK_AGENT_HEARTBEAT_INTERVAL=60         # seconds
WRKTALK_AGENT_MAINTENANCE_MODE_HANDLER=nginx
WRKTALK_AGENT_LOG_LEVEL=INFO
```

## Deployment

### Kubernetes

```bash
# 1. Build Docker image
docker build -f Dockerfile.kubernetes -t wrktalk-agent:v4.2 .

# 2. Load image to cluster (minikube example)
minikube image load wrktalk-agent:v4.2

# 3. Update ConfigMap in k8s/agent-deployment.yaml with your database settings

# 4. Deploy
kubectl apply -f k8s/agent-deployment.yaml

# 5. Verify
kubectl get pods -n wrktalk
kubectl logs -f deployment/wrktalk-agent -n wrktalk
```

### Docker Environment

```bash
# 1. Build image (same as K8s)
docker build -f Dockerfile.kubernetes -t wrktalk-agent:v4.2 .

# 2. Run with environment variables
docker run -d \
  --name wrktalk-agent \
  -e WRKTALK_AGENT_DEPLOYMENT_TYPE=docker \
  -e WRKTALK_AGENT_DB_HOST=host.docker.internal \
  -e WRKTALK_AGENT_DB_PORT=5432 \
  -e WRKTALK_AGENT_DB_NAME=wrktalk \
  -e WRKTALK_AGENT_DB_USER=postgres \
  -e WRKTALK_AGENT_DB_PASSWORD=password \
  -v /var/run/docker.sock:/var/run/docker.sock \
  wrktalk-agent:v4.2
```

## How It Works

### 1. Polling for Tasks

Every 30 seconds (configurable), the agent:

```python
task = await repo.get_pending_task()
# SQL: UPDATE agent_task SET status='inProgress'
#      WHERE id = (SELECT id FROM agent_task
#                  WHERE status='pending' AND execute_after <= NOW()
#                  ORDER BY execute_after ASC LIMIT 1
#                  FOR UPDATE SKIP LOCKED)
```

### 2. Fetching Artifacts

```python
artifact = await repo.get_artifact(task.release_artifact_id)
# Returns: ReleaseArtifact with artifact_data (bytes)

# Extract tarball bytes to temp directory
with open("artifact.tar.gz", "wb") as f:
    f.write(artifact.artifact_data)
```

### 3. Deployment Process

#### Kubernetes (Helm)
```bash
# 1. Enable maintenance mode
touch /tmp/maintenance-mode && nginx -s reload

# 2. Extract chart from BYTEA
tar -xzf artifact.tar.gz

# 3. Write values.yaml from database
cat > values.yaml << EOF
${artifact.values_data}
EOF

# 4. Execute Helm upgrade
helm upgrade --install --atomic --wait \
  wrktalk ./chart -f values.yaml \
  --namespace wrktalk --timeout 10m

# 5. Disable maintenance mode
rm /tmp/maintenance-mode && nginx -s reload
```

#### Docker Compose
```bash
# 1. Enable maintenance mode
touch /tmp/maintenance-mode

# 2. Extract compose file
tar -xzf artifact.tar.gz

# 3. Write .env from database
cat > .env << EOF
${artifact.env_data}
EOF

# 4. Execute compose up
docker-compose -f docker-compose.yaml up -d

# 5. Disable maintenance mode
rm /tmp/maintenance-mode
```

### 4. Email Notification

```python
admins = await repo.get_active_admins()
emails = [admin.email for admin in admins]

email_client.send_deployment_notification(
    to_emails=emails,
    status='SUCCESS',  # or 'FAILED', 'ROLLBACK_SUCCESS', etc.
    release_version=artifact.release_version,
    task_id=task.id
)
```

### 5. Update Status

```python
await repo.update_task_status(
    task_id=task.id,
    status='completed',
    result={
        'status': 'success',
        'message': 'Deployment successful',
        'release_version': artifact.release_version,
        'helmRevision': 5
    }
)
```

## Rollback

### Kubernetes (Helm History)

```python
# Agent executes
rollback_result = await executor.rollback()
# Helm command: helm rollback wrktalk --namespace wrktalk
```

### Docker (Re-deploy Previous Version)

```python
# 1. Get previous artifact from database
artifact = await repo.get_previous_artifact('compose')
# SELECT * FROM release_artifact WHERE is_previous=TRUE

# 2. Extract and deploy previous version
# (Same as deployment process)
```

## Monitoring

### Agent Logs

```bash
# Kubernetes
kubectl logs -f deployment/wrktalk-agent -n wrktalk

# Docker
docker logs -f wrktalk-agent
```

### Database Monitoring

```sql
-- Check pending tasks
SELECT id, type, execute_after, created_at
FROM agent_task
WHERE status = 'pending'
ORDER BY execute_after;

-- Check task heartbeats
SELECT id, status, last_heartbeat,
       NOW() - last_heartbeat as time_since_heartbeat
FROM agent_task
WHERE status = 'inProgress';

-- Check current/previous artifacts
SELECT release_version, chart_type, is_current, is_previous, applied_at
FROM release_artifact
WHERE is_current = TRUE OR is_previous = TRUE;

-- Check last agent poll
SELECT last_agent_poll, NOW() - last_agent_poll as time_since_poll
FROM deployment_config;
```

## Troubleshooting

### Agent Can't Connect to Database

**Check:**
```bash
# Test PostgreSQL connection
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME

# Check agent logs
kubectl logs deployment/wrktalk-agent -n wrktalk | grep "database.pool"
```

### No Tasks Being Picked Up

**Check:**
```sql
-- Verify tasks exist
SELECT * FROM agent_task WHERE status = 'pending';

-- Check execute_after timestamp
SELECT id, execute_after, execute_after <= NOW() as ready
FROM agent_task WHERE status = 'pending';
```

### Email Notifications Not Sending

**Check:**
```sql
-- Verify SMTP config in database
SELECT smtp_host, smtp_port, smtp_user, smtp_from
FROM deployment_config;

-- Verify active admins
SELECT email, is_active FROM admin WHERE is_active = TRUE;
```

**Test SMTP:**
```python
python -c "
import smtplib
from email.mime.text import MIMEText

msg = MIMEText('Test email')
msg['From'] = 'noreply@wrktalk.com'
msg['To'] = 'admin@example.com'
msg['Subject'] = 'Test'

with smtplib.SMTP('smtp.gmail.com', 587) as server:
    server.starttls()
    server.login('user@gmail.com', 'password')
    server.send_message(msg)
"
```

### Artifact Extraction Fails

**Check:**
```sql
-- Verify artifact data is not null
SELECT id, release_version,
       length(artifact_data) as size_bytes,
       chart_type
FROM release_artifact
WHERE id = 'artifact-id';
```

### Maintenance Mode Not Working

**Check nginx config:**
```nginx
# /etc/nginx/conf.d/maintenance.conf
location / {
    if (-f /tmp/maintenance-mode) {
        return 503;
    }
    # ... normal config
}

error_page 503 @maintenance;
location @maintenance {
    return 503 "Service under maintenance";
}
```

## Migration from v1.x

See [MIGRATION_V4.2_SUMMARY.md](MIGRATION_V4.2_SUMMARY.md) for detailed migration guide.

**Key Steps:**
1. Set up PostgreSQL database with schema
2. Insert SMTP configuration in `deployment_config`
3. Create admin users in `admin` table
4. Upload artifacts to `release_artifact` table (BYTEA column)
5. Update environment variables (remove Backend/MinIO, add Database)
6. Rebuild Docker image
7. Deploy new agent

## API Reference

### AgentRepository Methods

```python
# Task Management
task = await repo.get_pending_task() → Optional[AgentTask]
await repo.update_task_status(task_id, status, result, error)
await repo.update_heartbeat(task_id)

# Artifact Management
artifact = await repo.get_artifact(artifact_id) → Optional[ReleaseArtifact]
previous = await repo.get_previous_artifact(chart_type) → Optional[ReleaseArtifact]
await repo.update_artifact_flags(new_current_id, old_current_id, chart_type)

# Configuration
smtp_config = await repo.get_smtp_config() → Dict
admins = await repo.get_active_admins() → List[Admin]

# Maintenance
enabled = await repo.get_maintenance_mode() → bool
await repo.set_maintenance_mode(True)

# Monitoring
await repo.update_last_agent_poll()
```

### EmailClient Methods

```python
email_client.send_deployment_notification(
    to_emails=['admin@example.com'],
    status='SUCCESS',  # or 'FAILED', 'ROLLBACK_SUCCESS', 'ROLLBACK_FAILED'
    release_version='wrktalk-v2.5.0',
    error_message=None,  # Optional for failures
    task_id='task-uuid'
)
```

### MaintenanceHandler Methods

```python
await maintenance.enable()   # Creates /tmp/maintenance-mode
await maintenance.disable()  # Removes /tmp/maintenance-mode
```

## Security

### Database Credentials

**Production:** Use Kubernetes Secrets instead of ConfigMap:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: wrktalk-agent-db-secret
type: Opaque
stringData:
  db-password: your-secure-password
---
# In Deployment:
env:
- name: WRKTALK_AGENT_DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: wrktalk-agent-db-secret
      key: db-password
```

### SMTP Credentials

Store in database with encryption or use application-level secrets.

### Secure File Deletion

Agent overwrites temporary files with random bytes before deletion:

```python
# Securely delete all files in temp directory
self._secure_delete_directory(temp_dir)
```

## Performance

### Connection Pooling

```python
# asyncpg pool: min=2, max=10 connections
pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
```

### Concurrent Agents

Multiple agents can run simultaneously:
- `FOR UPDATE SKIP LOCKED` prevents task conflicts
- Each agent picks different tasks atomically

### Binary Storage

PostgreSQL BYTEA columns efficiently store 500KB-2MB tarballs.

## License

[Your License Here]

## Support

For issues or questions, refer to:
- [MIGRATION_V4.2_SUMMARY.md](MIGRATION_V4.2_SUMMARY.md) - Migration details
- [WrkTalk_Deployment_HighLevel_v5.md](WrkTalk_Deployment_HighLevel_v5.md) - Architecture spec
- GitHub Issues: [Your Repo URL]

---

**Version:** 4.2
**Last Updated:** December 2024
**Architecture:** PostgreSQL-Based Polling
