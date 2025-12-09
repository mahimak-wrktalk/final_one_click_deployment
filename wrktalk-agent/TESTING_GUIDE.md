# WrkTalk Agent Testing Guide

Complete guide for testing the WrkTalk deployment agent in local and Minikube environments.

## Table of Contents

1. [Local Testing Setup](#local-testing-setup)
2. [Testing with MinIO](#testing-with-minio)
3. [Testing in Minikube](#testing-in-minikube)
4. [Docker Compose Testing](#docker-compose-testing)
5. [Troubleshooting](#troubleshooting)

---

## Local Testing Setup

### Prerequisites

- Python 3.11+
- Helm 3.x (for Kubernetes mode)
- Docker & docker-compose (for Docker mode)
- MinIO running at localhost:9000

### Step 1: Install Dependencies

```bash
cd wrktalk-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install fastapi uvicorn  # For mock backend
```

### Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```bash
WRKTALK_AGENT_BACKEND_URL=http://localhost:3000
WRKTALK_AGENT_AGENT_SECRET=agent-secret-key
WRKTALK_AGENT_DEPLOYMENT_TYPE=kubernetes
WRKTALK_AGENT_MINIO_ENDPOINT=localhost:9000
WRKTALK_AGENT_MINIO_ACCESS_KEY=admin
WRKTALK_AGENT_MINIO_SECRET_KEY=admin123
WRKTALK_AGENT_MINIO_BUCKET_NAME=wrktalk-artifacts
WRKTALK_AGENT_MINIO_SECURE=false
WRKTALK_AGENT_LOG_LEVEL=DEBUG
```

### Step 3: Start Mock Backend

In terminal 1:
```bash
cd tests
python mock_backend.py
```

You should see:
```
======================================================================
Mock WrkTalk Backend Server
======================================================================
Starting on http://localhost:3000
...
```

### Step 4: Verify MinIO Access

Check that MinIO is accessible:
```bash
curl http://localhost:9001
```

Access MinIO Console:
- URL: http://localhost:9001
- Username: admin
- Password: admin123

---

## Testing with MinIO

### Setup 1: Create Test Helm Chart (Kubernetes)

```bash
# Create chart structure
mkdir -p test-chart/templates

# Create Chart.yaml
cat > test-chart/Chart.yaml << 'EOF'
apiVersion: v2
name: wrktalk
version: 2.3.0
appVersion: 2.3.0
description: WrkTalk test chart
EOF

# Create values.yaml
cat > test-chart/values.yaml << 'EOF'
backend:
  image:
    repository: nginx
    tag: latest
  replicaCount: 1

media:
  image:
    repository: nginx
    tag: latest
  replicaCount: 1
EOF

# Create deployment template
cat > test-chart/templates/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wrktalk-backend
spec:
  replicas: {{ .Values.backend.replicaCount }}
  selector:
    matchLabels:
      app: wrktalk
      component: backend
  template:
    metadata:
      labels:
        app: wrktalk
        component: backend
    spec:
      containers:
      - name: backend
        image: {{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}
        ports:
        - containerPort: 80
EOF

# Package chart
helm package test-chart
# Output: wrktalk-2.3.0.tgz
```

### Setup 2: Upload to MinIO

**Option A: Using MinIO Console (Web UI)**

1. Open http://localhost:9001
2. Login with admin/admin123
3. Navigate to bucket `wrktalk-artifacts`
4. Create folders:
   - `artifacts/helm/`
   - `config/`
5. Upload files:
   - Upload `wrktalk-2.3.0.tgz` to `artifacts/helm/`
   - Upload `test-chart/values.yaml` to `config/values.yaml`

**Option B: Using MinIO Client (mc)**

```bash
# Install mc
brew install minio/stable/mc  # macOS
# Or download from https://min.io/docs/minio/linux/reference/minio-mc.html

# Configure mc
mc alias set local http://localhost:9000 admin admin123

# Create bucket (if not exists)
mc mb local/wrktalk-artifacts

# Upload files
mc cp wrktalk-2.3.0.tgz local/wrktalk-artifacts/artifacts/helm/
mc cp test-chart/values.yaml local/wrktalk-artifacts/config/values.yaml

# Verify
mc ls local/wrktalk-artifacts/artifacts/helm/
mc ls local/wrktalk-artifacts/config/
```

### Setup 3: Create Test Deployment Task

```bash
cd tests
./create_test_task.sh
```

Or manually:
```bash
curl -X POST http://localhost:3000/test/add-task \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-deploy-001",
    "type": "deploy",
    "payload": {
      "chart": {
        "bucketPath": "artifacts/helm/wrktalk-2.3.0.tgz",
        "version": "2.3.0"
      },
      "valuesBucketPath": "config/values.yaml",
      "imageTags": {
        "backend": "latest",
        "media": "latest"
      },
      "newNonEssentialEnvs": [
        {"key": "FEATURE_X", "value": "true"}
      ]
    },
    "executeAfter": "2024-01-01T00:00:00Z"
  }'
```

### Step 4: Run Agent

In terminal 2:
```bash
cd wrktalk-agent
source venv/bin/activate
export $(cat .env | xargs)
python -m wrktalk_agent
```

### Step 5: Observe Execution

Watch the agent logs. You should see:
1. Agent polling every 30 seconds
2. Task received
3. Downloading from MinIO
4. Helm upgrade execution
5. Status reported back

Mock backend will show:
```
[2024-01-15 10:00:00] 📝 Task added: test-deploy-001
[2024-01-15 10:00:30] Returning task: test-deploy-001
[2024-01-15 10:00:31] Task test-deploy-001 status: inProgress
[2024-01-15 10:01:00] ❤️  Heartbeat from task test-deploy-001
[2024-01-15 10:02:15] Task test-deploy-001 status: completed
  Result: {'status': 'success', 'helmRevision': 1, 'message': '...'}
```

---

## Testing in Minikube

### Step 1: Start Minikube

```bash
minikube start --driver=docker
```

### Step 2: Build Agent Image

```bash
cd wrktalk-agent
docker build -f Dockerfile.kubernetes -t wrktalk-agent:latest .
minikube image load wrktalk-agent:latest
```

### Step 3: Create Kubernetes Manifests

Create `k8s/agent-deployment.yaml`:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: wrktalk
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: wrktalk-agent
  namespace: wrktalk
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: wrktalk-agent-role
  namespace: wrktalk
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps", "secrets", "persistentvolumeclaims"]
  verbs: ["*"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets", "replicasets"]
  verbs: ["*"]
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["*"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: wrktalk-agent-binding
  namespace: wrktalk
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: wrktalk-agent-role
subjects:
- kind: ServiceAccount
  name: wrktalk-agent
  namespace: wrktalk
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: wrktalk-agent-config
  namespace: wrktalk
data:
  WRKTALK_AGENT_BACKEND_URL: "http://host.minikube.internal:3000"
  WRKTALK_AGENT_AGENT_SECRET: "agent-secret-key"
  WRKTALK_AGENT_DEPLOYMENT_TYPE: "kubernetes"
  WRKTALK_AGENT_KUBE_NAMESPACE: "wrktalk"
  WRKTALK_AGENT_HELM_RELEASE_NAME: "wrktalk"
  WRKTALK_AGENT_MINIO_ENDPOINT: "host.minikube.internal:9000"
  WRKTALK_AGENT_MINIO_ACCESS_KEY: "admin"
  WRKTALK_AGENT_MINIO_SECRET_KEY: "admin123"
  WRKTALK_AGENT_MINIO_BUCKET_NAME: "wrktalk-artifacts"
  WRKTALK_AGENT_MINIO_SECURE: "false"
  WRKTALK_AGENT_LOG_LEVEL: "DEBUG"
  WRKTALK_AGENT_POLL_INTERVAL: "10"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wrktalk-agent
  namespace: wrktalk
spec:
  replicas: 1
  selector:
    matchLabels:
      app: wrktalk-agent
  template:
    metadata:
      labels:
        app: wrktalk-agent
    spec:
      serviceAccountName: wrktalk-agent
      containers:
      - name: agent
        image: wrktalk-agent:latest
        imagePullPolicy: Never
        envFrom:
        - configMapRef:
            name: wrktalk-agent-config
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### Step 4: Deploy to Minikube

```bash
kubectl apply -f k8s/agent-deployment.yaml
```

### Step 5: Verify Deployment

```bash
# Check namespace
kubectl get ns wrktalk

# Check pod status
kubectl get pods -n wrktalk

# View agent logs
kubectl logs -f -n wrktalk deployment/wrktalk-agent

# Check ServiceAccount
kubectl get sa -n wrktalk
kubectl get role,rolebinding -n wrktalk
```

### Step 6: Add Test Task

Make sure mock backend is running on your host machine, then:
```bash
./tests/create_test_task.sh
```

### Step 7: Watch Execution

```bash
# Follow agent logs
kubectl logs -f -n wrktalk deployment/wrktalk-agent

# Check if deployment was created
kubectl get deployments -n wrktalk

# Check helm releases
kubectl exec -n wrktalk deployment/wrktalk-agent -- helm list -n wrktalk
```

---

## Docker Compose Testing

### Step 1: Create Test Compose Bundle

```bash
mkdir -p test-compose

cat > test-compose/docker-compose.yaml << 'EOF'
version: '3.8'

services:
  backend:
    image: nginx:${BACKEND_IMAGE_TAG:-latest}
    container_name: wrktalk-backend
    ports:
      - "8080:80"
    environment:
      - ENV=production

  media:
    image: nginx:${MEDIA_IMAGE_TAG:-latest}
    container_name: wrktalk-media
    ports:
      - "8081:80"
EOF

cat > test-compose/.env << 'EOF'
BACKEND_IMAGE_TAG=latest
MEDIA_IMAGE_TAG=latest
EOF

# Create tarball
tar -czf wrktalk-2.3.0-compose.tar.gz -C test-compose .
```

### Step 2: Upload to MinIO

```bash
mc cp wrktalk-2.3.0-compose.tar.gz local/wrktalk-artifacts/artifacts/compose/
mc cp test-compose/.env local/wrktalk-artifacts/config/.env
```

### Step 3: Configure Agent for Docker Mode

Edit `.env`:
```bash
WRKTALK_AGENT_DEPLOYMENT_TYPE=docker
WRKTALK_AGENT_COMPOSE_WORKING_DIR=/tmp/wrktalk-test
```

### Step 4: Create Compose Test Task

```bash
curl -X POST http://localhost:3000/test/add-task \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-compose-001",
    "type": "deploy",
    "payload": {
      "chart": {
        "bucketPath": "artifacts/compose/wrktalk-2.3.0-compose.tar.gz",
        "version": "2.3.0"
      },
      "envBucketPath": "config/.env",
      "imageTags": {
        "backend": "latest",
        "media": "latest"
      },
      "newNonEssentialEnvs": []
    },
    "executeAfter": "2024-01-01T00:00:00Z"
  }'
```

### Step 5: Run Agent

```bash
export $(cat .env | xargs)
python -m wrktalk_agent
```

### Step 6: Verify Deployment

```bash
# Check running containers
docker ps | grep wrktalk

# Check logs
docker logs wrktalk-backend
docker logs wrktalk-media

# Test access
curl http://localhost:8080
curl http://localhost:8081
```

---

## Troubleshooting

### Agent Can't Connect to Backend

**Symptom:** `backend.poll_error` in logs

**Solutions:**
```bash
# Test connectivity
curl http://localhost:3000

# Check backend is running
ps aux | grep mock_backend

# Verify environment variable
echo $WRKTALK_AGENT_BACKEND_URL
```

### MinIO Download Failures

**Symptom:** `minio.download_error` in logs

**Solutions:**
```bash
# Test MinIO connectivity
curl http://localhost:9000/minio/health/live

# Check bucket exists
mc ls local/wrktalk-artifacts/

# Verify credentials
mc admin info local

# Check object exists
mc stat local/wrktalk-artifacts/artifacts/helm/wrktalk-2.3.0.tgz

# Test from Python
python3 << EOF
from minio import Minio
client = Minio("localhost:9000", access_key="admin", secret_key="admin123", secure=False)
print(list(client.list_buckets()))
EOF
```

### Helm Command Not Found (Minikube)

**Symptom:** `helm: command not found` in pod logs

**Solution:**
```bash
# Verify Helm in Docker image
docker run --rm wrktalk-agent:latest helm version

# Rebuild if needed
docker build -f Dockerfile.kubernetes -t wrktalk-agent:latest .
minikube image load wrktalk-agent:latest

# Restart pod
kubectl rollout restart deployment/wrktalk-agent -n wrktalk
```

### Minikube Can't Access Host Services

**Symptom:** Connection refused to `host.minikube.internal`

**Solution:**
```bash
# Check minikube IP
minikube ip

# Test from inside pod
kubectl run -it --rm debug --image=alpine --restart=Never -- sh
# Inside pod:
apk add curl
curl http://host.minikube.internal:3000
curl http://host.minikube.internal:9000/minio/health/live

# Alternative: Use minikube tunnel
minikube tunnel
```

### RBAC Permission Errors

**Symptom:** `forbidden: User "system:serviceaccount:wrktalk:wrktalk-agent" cannot...`

**Solution:**
```bash
# Check role permissions
kubectl describe role wrktalk-agent-role -n wrktalk

# Check binding
kubectl describe rolebinding wrktalk-agent-binding -n wrktalk

# Grant additional permissions if needed
kubectl edit role wrktalk-agent-role -n wrktalk
```

### Docker Socket Permission Denied

**Symptom:** `Cannot connect to Docker daemon` in Docker mode

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Or run with sudo (not recommended for production)
sudo -E python -m wrktalk_agent
```

### Task Not Being Picked Up

**Symptom:** Agent polls but doesn't execute task

**Debug:**
```bash
# Check task queue
curl http://localhost:3000/test/tasks

# Check executeAfter time (must be in past)
# The task is only executed if executeAfter <= now

# Check agent secret matches
echo $WRKTALK_AGENT_AGENT_SECRET

# View detailed logs
WRKTALK_AGENT_LOG_LEVEL=DEBUG python -m wrktalk_agent
```

---

## Quick Test Commands

```bash
# Clear all tasks
curl -X DELETE http://localhost:3000/test/clear

# View task queue
curl http://localhost:3000/test/tasks | jq

# View config store
curl http://localhost:3000/test/config | jq

# Check agent is polling
tail -f agent.log | grep "agent.no_tasks"

# Force a deployment (K8s)
helm list -n wrktalk
kubectl get all -n wrktalk

# Force a deployment (Docker)
docker ps
docker-compose -p wrktalk ps

# Cleanup
kubectl delete ns wrktalk  # Minikube
docker-compose -p wrktalk down  # Docker mode
```

---

## Next Steps

After successful local testing:
1. Implement the actual WrkTalk Backend APIs
2. Set up production MinIO/S3
3. Configure GHCR image pull secrets
4. Deploy to production Kubernetes cluster
5. Set up monitoring and alerting
