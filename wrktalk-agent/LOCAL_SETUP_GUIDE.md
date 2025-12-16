# WrkTalk Agent v4.2 - Local Environment Setup Guide

Complete step-by-step guide to set up and test the agent in your local environment.

---

## Part 1: PostgreSQL Installation and Setup

### Step 1: Install PostgreSQL on macOS

```bash
# Install PostgreSQL using Homebrew
brew install postgresql@14

# Start PostgreSQL service
brew services start postgresql@14

# Verify installation
psql --version
# Expected: psql (PostgreSQL) 14.x
```

### Step 2: Create Database and User

```bash
# Connect to PostgreSQL as superuser
psql postgres

# Inside psql shell, run:
CREATE DATABASE wrktalk;
CREATE USER wrktalk_user WITH PASSWORD 'wrktalk_password';
GRANT ALL PRIVILEGES ON DATABASE wrktalk TO wrktalk_user;

# Exit psql
\q
```

### Step 3: Create Database Schema

Create a file `schema.sql`:

```bash
cat > schema.sql << 'SQL'
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
SQL
```

Apply the schema:

```bash
psql -U wrktalk_user -d wrktalk -f schema.sql
```

### Step 4: Insert Initial Configuration

```bash
cat > insert_config.sql << 'SQL'
-- Insert deployment configuration
INSERT INTO deployment_config (
    id, deployment_type, namespace, helm_release_name,
    smtp_host, smtp_port, smtp_user, smtp_password, smtp_from
) VALUES (
    uuid_generate_v4(),
    'kubernetes',
    'wrktalk',
    'wrktalk',
    'smtp.gmail.com',
    587,
    'mahimakesharwani1@gmail.com',
    'pymjschmdmbyxkpn',
    'mahimakesharwani1@gmail.com'
);

-- Insert admin user for email notifications
INSERT INTO admin (id, name, email, is_active, role) VALUES
    (uuid_generate_v4(), 'Admin User', 'mahimakesharwani1@gmail.com', true, 'ADMIN');
SQL

psql -U wrktalk_user -d wrktalk -f insert_config.sql
```

**Note:** Replace email credentials with your actual Gmail app password.

### Step 5: Verify Database Setup

```bash
# Connect to database
psql -U wrktalk_user -d wrktalk

# Verify tables
\dt

# Expected output:
#              List of relations
#  Schema |       Name        | Type  |    Owner
# --------+-------------------+-------+-------------
#  public | admin             | table | wrktalk_user
#  public | agent_task        | table | wrktalk_user
#  public | deployment_config | table | wrktalk_user
#  public | release_artifact  | table | wrktalk_user
#  public | server_env        | table | wrktalk_user

# Check deployment config
SELECT deployment_type, smtp_host, smtp_port FROM deployment_config;

# Check admin users
SELECT name, email, is_active FROM admin;

# Exit
\q
```

---

## Part 2: Agent Installation and Configuration

### Step 1: Install Agent Dependencies

```bash
cd /Users/admin/Documents/vscode_testing/one_click_new_n/wrktalk-agent

# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install agent package in development mode
pip install -e .
```

### Step 2: Configure Environment Variables

```bash
# Create .env file
cat > .env << 'ENV'
# Database Configuration
WRKTALK_AGENT_DB_HOST=localhost
WRKTALK_AGENT_DB_PORT=5432
WRKTALK_AGENT_DB_NAME=wrktalk
WRKTALK_AGENT_DB_USER=wrktalk_user
WRKTALK_AGENT_DB_PASSWORD=wrktalk_password
WRKTALK_AGENT_DB_SSL_MODE=prefer

# Deployment Type
WRKTALK_AGENT_DEPLOYMENT_TYPE=kubernetes

# Kubernetes Settings
WRKTALK_AGENT_KUBE_NAMESPACE=wrktalk
WRKTALK_AGENT_HELM_RELEASE_NAME=wrktalk
WRKTALK_AGENT_HELM_TIMEOUT=10m

# Agent Settings
WRKTALK_AGENT_POLL_INTERVAL=10
WRKTALK_AGENT_HEARTBEAT_INTERVAL=30
WRKTALK_AGENT_MAINTENANCE_MODE_HANDLER=nginx
WRKTALK_AGENT_LOG_LEVEL=DEBUG
ENV

# Load environment variables
export $(cat .env | xargs)
```

### Step 3: Test Database Connection

```bash
# Test Python connection to database
python << 'PYTHON'
import asyncio
import asyncpg

async def test_connection():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='wrktalk',
        user='wrktalk_user',
        password='wrktalk_password'
    )
    
    # Test query
    rows = await conn.fetch('SELECT * FROM deployment_config')
    print(f"✅ Connection successful! Found {len(rows)} deployment config(s)")
    
    await conn.close()

asyncio.run(test_connection())
PYTHON
```

---

## Part 3: Create and Upload Test Helm Chart

### Step 1: Create a Simple Test Helm Chart

```bash
# Navigate to project directory
cd /Users/admin/Documents/vscode_testing/one_click_new_n/wrktalk-agent

# Create test chart (if not exists)
mkdir -p test-chart-simple/templates

# Create Chart.yaml
cat > test-chart-simple/Chart.yaml << 'YAML'
apiVersion: v2
name: wrktalk-test
description: Test chart for WrkTalk agent
type: application
version: 1.0.0
appVersion: "1.0.0"
YAML

# Create values.yaml
cat > test-chart-simple/values.yaml << 'YAML'
replicaCount: 1

image:
  repository: nginx
  tag: "1.21"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
YAML

# Create deployment template
cat > test-chart-simple/templates/deployment.yaml << 'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Chart.Name }}
  namespace: {{ .Release.Namespace }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: {{ .Chart.Name }}
  template:
    metadata:
      labels:
        app: {{ .Chart.Name }}
    spec:
      containers:
      - name: nginx
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        ports:
        - containerPort: 80
YAML

# Package the chart
helm package test-chart-simple
# Output: wrktalk-test-1.0.0.tgz
```

### Step 2: Upload Helm Chart to PostgreSQL

Create a Python script to upload the chart:

```bash
cat > upload_chart.py << 'PYTHON'
import asyncio
import asyncpg
import hashlib
from pathlib import Path

async def upload_chart(chart_path: str, release_version: str):
    """Upload Helm chart tarball to PostgreSQL."""
    
    # Read tarball bytes
    chart_data = Path(chart_path).read_bytes()
    
    # Calculate SHA256
    sha256 = hashlib.sha256(chart_data).hexdigest()
    
    print(f"📦 Chart: {chart_path}")
    print(f"📏 Size: {len(chart_data)} bytes")
    print(f"🔐 SHA256: {sha256}")
    
    # Connect to database
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='wrktalk',
        user='wrktalk_user',
        password='wrktalk_password'
    )
    
    # Read values.yaml content
    values_data = None
    if Path('test-chart-simple/values.yaml').exists():
        values_data = Path('test-chart-simple/values.yaml').read_text()
    
    # Insert artifact
    artifact_id = await conn.fetchval("""
        INSERT INTO release_artifact (
            release_version, chart_type, artifact_data, 
            values_data, sha256, is_current, is_previous
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
    """, release_version, 'helm', chart_data, values_data, sha256, False, False)
    
    print(f"✅ Artifact uploaded! ID: {artifact_id}")
    
    await conn.close()
    return artifact_id

if __name__ == '__main__':
    chart_path = 'wrktalk-test-1.0.0.tgz'
    release_version = 'wrktalk-test-v1.0.0'
    
    artifact_id = asyncio.run(upload_chart(chart_path, release_version))
    print(f"\n🎉 Chart uploaded successfully!")
    print(f"   Artifact ID: {artifact_id}")
PYTHON

# Run the upload script
python upload_chart.py
```

### Step 3: Create Deployment Task

Create a script to create a deployment task:

```bash
cat > create_task.py << 'PYTHON'
import asyncio
import asyncpg
from datetime import datetime, timezone

async def create_deploy_task(artifact_id: str):
    """Create a deployment task in the database."""
    
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='wrktalk',
        user='wrktalk_user',
        password='wrktalk_password'
    )
    
    # Create task
    task_id = await conn.fetchval("""
        INSERT INTO agent_task (
            type, status, release_artifact_id, execute_after
        ) VALUES ($1, $2, $3, $4)
        RETURNING id
    """, 'deploy', 'pending', artifact_id, datetime.now(timezone.utc))
    
    print(f"✅ Deployment task created!")
    print(f"   Task ID: {task_id}")
    print(f"   Artifact ID: {artifact_id}")
    print(f"   Status: pending")
    
    await conn.close()
    return task_id

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python create_task.py <artifact_id>")
        sys.exit(1)
    
    artifact_id = sys.argv[1]
    task_id = asyncio.run(create_deploy_task(artifact_id))
    
    print(f"\n🚀 Task is ready for agent to pick up!")
PYTHON

# Run the script with the artifact ID from previous step
# python create_task.py <artifact-id-from-upload>
```

---

## Part 4: Run the Agent Locally

### Step 1: Start Minikube (for Kubernetes deployments)

```bash
# Start Minikube
minikube start

# Verify cluster is running
kubectl cluster-info
kubectl get nodes

# Create wrktalk namespace
kubectl create namespace wrktalk
```

### Step 2: Run the Agent

```bash
# Make sure you're in the project directory
cd /Users/admin/Documents/vscode_testing/one_click_new_n/wrktalk-agent

# Activate virtual environment
source venv/bin/activate

# Export environment variables
export $(cat .env | xargs)

# Run the agent
python -m wrktalk_agent
```

Expected output:
```
{"event": "agent.initialized", "deployment_type": "kubernetes", "db_host": "localhost", "db_name": "wrktalk"}
{"event": "agent.starting"}
{"event": "database.pool.connected", "dsn": "postgresql://wrktalk_user:***@localhost:5432/wrktalk"}
{"event": "agent.email_client_initialized"}
{"event": "agent.task_received", "task_id": "...", "task_type": "deploy"}
{"event": "agent.artifact_loaded", "artifact_id": "...", "version": "wrktalk-test-v1.0.0", "size_bytes": 1234}
{"event": "agent.artifact_extracted", "temp_dir": "/tmp/wrktalk-deploy-..."}
{"event": "maintenance.enabled", "mode": "nginx"}
{"event": "heartbeat.started", "task_id": "..."}
{"event": "helm.upgrade.starting", "release": "wrktalk", "namespace": "wrktalk"}
{"event": "helm.upgrade.success", "revision": 1}
{"event": "agent.task_completed", "task_id": "..."}
{"event": "email.sent", "to": ["admin@example.com"], "status": "SUCCESS"}
```

---

## Part 5: Monitor and Verify

### Step 1: Check Task Status in Database

```bash
# Connect to PostgreSQL
psql -U wrktalk_user -d wrktalk

-- View all tasks
SELECT id, type, status, execute_after, completed_at, last_heartbeat 
FROM agent_task 
ORDER BY created_at DESC;

-- View task result
SELECT id, status, result, error_message 
FROM agent_task 
WHERE id = '019fcefc-3959-4814-ab83-791c89e039a8';

-- Check heartbeat updates
SELECT id, status, last_heartbeat, 
       NOW() - last_heartbeat as time_since_heartbeat
FROM agent_task
WHERE status = 'inProgress';

-- Exit
\q
```

### Step 2: Verify Kubernetes Deployment

```bash
# Check Helm releases
helm list -n wrktalk

# Check deployed resources
kubectl get all -n wrktalk

# Check specific deployment
kubectl get deployment wrktalk-test -n wrktalk

# Check pods
kubectl get pods -n wrktalk

# View pod logs
kubectl logs -l app=wrktalk-test -n wrktalk
```

### Step 3: Check Artifact Flags

```bash
psql -U wrktalk_user -d wrktalk << 'SQL'
-- Check which artifact is current
SELECT id, release_version, is_current, is_previous, applied_at
FROM release_artifact
WHERE is_current = TRUE OR is_previous = TRUE;
SQL
```

---

## Part 6: Testing Complete Workflow

### Test 1: Deploy Second Version (for rollback testing)

```bash
# 1. Create another chart version
cat > test-chart-simple/Chart.yaml << 'YAML'
apiVersion: v2
name: wrktalk-test
description: Test chart for WrkTalk agent
type: application
version: 2.0.0
appVersion: "2.0.0"
YAML

# 2. Package new version
helm package test-chart-simple
# Output: wrktalk-test-2.0.0.tgz

# 3. Upload to database
python << 'PYTHON'
import asyncio
import asyncpg
import hashlib
from pathlib import Path

async def upload():
    chart_data = Path('wrktalk-test-2.0.0.tgz').read_bytes()
    sha256 = hashlib.sha256(chart_data).hexdigest()
    values_data = Path('test-chart-simple/values.yaml').read_text()
    
    conn = await asyncpg.connect(
        host='localhost', port=5432, database='wrktalk',
        user='wrktalk_user', password='wrktalk_password'
    )
    
    artifact_id = await conn.fetchval("""
        INSERT INTO release_artifact (
            release_version, chart_type, artifact_data, 
            values_data, sha256, is_current, is_previous
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
    """, 'wrktalk-test-v2.0.0', 'helm', chart_data, values_data, sha256, False, False)
    
    # Create deployment task
    task_id = await conn.fetchval("""
        INSERT INTO agent_task (type, status, release_artifact_id, execute_after)
        VALUES ('deploy', 'pending', $1, NOW())
        RETURNING id
    """, artifact_id)
    
    print(f"Artifact ID: {artifact_id}")
    print(f"Task ID: {task_id}")
    
    await conn.close()

asyncio.run(upload())
PYTHON

# Agent will automatically pick up the new task
```

### Test 2: Trigger Rollback

```bash
python << 'PYTHON'
import asyncio
import asyncpg

async def create_rollback_task():
    conn = await asyncpg.connect(
        host='localhost', port=5432, database='wrktalk',
        user='wrktalk_user', password='wrktalk_password'
    )
    
    task_id = await conn.fetchval("""
        INSERT INTO agent_task (type, status, execute_after)
        VALUES ('rollback', 'pending', NOW())
        RETURNING id
    """)
    
    print(f"Rollback task created: {task_id}")
    await conn.close()

asyncio.run(create_rollback_task())
PYTHON

# Agent will rollback to previous version
```

---

## Part 7: Troubleshooting

### Issue: Agent can't connect to database

```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Test connection manually
psql -U wrktalk_user -d wrktalk -h localhost

# Check firewall/port
netstat -an | grep 5432
```

### Issue: No tasks being picked up

```bash
# Check task status
psql -U wrktalk_user -d wrktalk << 'SQL'
SELECT id, type, status, execute_after, execute_after <= NOW() as ready
FROM agent_task
WHERE status = 'pending';
SQL

# Make sure execute_after is in the past
```

### Issue: Email not sending

```bash
# Verify SMTP config in database
psql -U wrktalk_user -d wrktalk << 'SQL'
SELECT smtp_host, smtp_port, smtp_user, smtp_from
FROM deployment_config;
SQL

# Check admin email addresses
psql -U wrktalk_user -d wrktalk << 'SQL'
SELECT email, is_active FROM admin WHERE is_active = TRUE;
SQL
```

### Issue: Helm deployment fails

```bash
# Check Minikube is running
minikube status

# Check namespace exists
kubectl get namespaces | grep wrktalk

# Check Helm CLI
helm version

# View agent logs with more detail
WRKTALK_AGENT_LOG_LEVEL=DEBUG python -m wrktalk_agent
```

---

## Next Steps

Once local testing is successful, proceed to Minikube deployment guide:
- See `MINIKUBE_DEPLOYMENT_GUIDE.md` (will be created next)

