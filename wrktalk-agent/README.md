# WrkTalk Deployment Agent

Python-based deployment agent for WrkTalk that supports both Kubernetes (Helm) and Docker Compose deployments.

## Features

- ✅ Poll-based task execution from WrkTalk Backend
- ✅ MinIO bucket integration for artifact downloads
- ✅ Kubernetes deployments via Helm
- ✅ Docker Compose deployments
- ✅ Automatic heartbeat during long-running tasks
- ✅ Atomic rollback support (Kubernetes)
- ✅ Secure file cleanup after operations

## Architecture

The agent is a stateless daemon that:
1. Polls WrkTalk Backend every 30 seconds for pending tasks
2. Downloads Helm charts or Docker Compose bundles from MinIO
3. Executes deployments using Helm or Docker Compose CLI
4. Reports status back to Backend
5. Sends heartbeats during long operations

## Installation

### Prerequisites

- Python 3.11+
- Helm 3.x (for Kubernetes deployments)
- Docker & docker-compose (for Docker deployments)
- Access to MinIO bucket

### Local Development Setup

1. Clone the repository and navigate to the agent directory:
```bash
cd wrktalk-agent
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy environment configuration:
```bash
cp .env.example .env
```

5. Edit `.env` with your settings:
```bash
# Update MinIO credentials
WRKTALK_AGENT_MINIO_ENDPOINT=localhost:9000
WRKTALK_AGENT_MINIO_ACCESS_KEY=admin
WRKTALK_AGENT_MINIO_SECRET_KEY=admin123

# Update Backend URL
WRKTALK_AGENT_BACKEND_URL=http://localhost:3000
WRKTALK_AGENT_AGENT_SECRET=your-secret-key

# Choose deployment type
WRKTALK_AGENT_DEPLOYMENT_TYPE=kubernetes  # or docker
```

## Running the Agent

### Local Testing (without Backend)

For testing the agent locally, you can create a mock Backend API server.

Create `mock_backend.py`:
```python
from fastapi import FastAPI, Header
from typing import Optional
import uvicorn

app = FastAPI()

# Mock task queue
task_queue = []

@app.get("/internal/agent/tasks")
async def get_tasks(x_agent_secret: str = Header(None)):
    if not task_queue:
        return {"task": None}

    task = task_queue[0]
    return {"task": task}

@app.post("/internal/agent/tasks/{task_id}/status")
async def update_status(task_id: str, x_agent_secret: str = Header(None)):
    print(f"Task {task_id} status updated")
    if task_queue and task_queue[0]["id"] == task_id:
        task_queue.pop(0)
    return {"success": True}

@app.post("/internal/agent/tasks/{task_id}/heartbeat")
async def heartbeat(task_id: str, x_agent_secret: str = Header(None)):
    print(f"Heartbeat from task {task_id}")
    return {"received": True}

@app.post("/internal/config")
async def insert_config(x_agent_secret: str = Header(None)):
    return {"created": True}

@app.get("/internal/license/status")
async def license_status(x_agent_secret: str = Header(None)):
    return {"valid": True, "expiresAt": "2025-12-31T23:59:59Z"}

# Helper to add test tasks
@app.post("/test/add-task")
async def add_task(task: dict):
    task_queue.append(task)
    return {"queued": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
```

Run mock backend:
```bash
pip install fastapi uvicorn
python mock_backend.py
```

### Run Agent Locally

```bash
# Load environment variables
source .env  # or export variables manually

# Run the agent
python -m wrktalk_agent
```

Or install and run as a package:
```bash
pip install -e .
wrktalk-agent
```

## Testing with MinIO

### 1. Setup MinIO

Your MinIO is already running at `http://localhost:9001`.

### 2. Upload Test Artifacts

#### For Kubernetes Testing:

Create a sample Helm chart:
```bash
# Create basic chart structure
mkdir -p test-chart/templates
cat > test-chart/Chart.yaml << EOF
apiVersion: v2
name: wrktalk
version: 2.3.0
appVersion: 2.3.0
description: WrkTalk test chart
EOF

cat > test-chart/values.yaml << EOF
backend:
  image:
    repository: nginx
    tag: latest
EOF

cat > test-chart/templates/deployment.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wrktalk-backend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: wrktalk
  template:
    metadata:
      labels:
        app: wrktalk
    spec:
      containers:
      - name: backend
        image: {{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}
EOF

# Package the chart
helm package test-chart
# This creates: wrktalk-2.3.0.tgz
```

Upload to MinIO:
1. Access MinIO console: http://localhost:9001
2. Login with admin/admin123
3. Navigate to `wrktalk-artifacts` bucket
4. Create folder: `artifacts/helm/`
5. Upload `wrktalk-2.3.0.tgz` to `artifacts/helm/`
6. Create folder: `config/`
7. Upload `test-chart/values.yaml` to `config/values.yaml`

#### For Docker Testing:

Create compose bundle:
```bash
mkdir -p test-compose
cat > test-compose/docker-compose.yaml << EOF
version: '3.8'
services:
  backend:
    image: nginx:\${BACKEND_IMAGE_TAG:-latest}
    ports:
      - "8080:80"
EOF

# Create tarball
tar -czf wrktalk-2.3.0-compose.tar.gz -C test-compose .
```

Upload to MinIO:
1. Create folder: `artifacts/compose/`
2. Upload `wrktalk-2.3.0-compose.tar.gz` to `artifacts/compose/`
3. Create `.env` file and upload to `config/.env`

### 3. Create Test Task

Using the mock backend, add a test deployment task:

```bash
curl -X POST http://localhost:3000/test/add-task \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-task-001",
    "type": "deploy",
    "payload": {
      "chart": {
        "bucketPath": "artifacts/helm/wrktalk-2.3.0.tgz",
        "version": "2.3.0"
      },
      "valuesBucketPath": "config/values.yaml",
      "imageTags": {
        "backend": "latest"
      },
      "newNonEssentialEnvs": []
    },
    "executeAfter": "2024-01-01T00:00:00Z"
  }'
```

### 4. Watch Agent Execute

The agent will:
1. Poll and receive the task
2. Download chart from MinIO
3. Download values.yaml
4. Execute `helm upgrade`
5. Report status back

## Testing with Minikube

### 1. Start Minikube

```bash
minikube start
```

### 2. Build and Load Agent Image

```bash
# Build Kubernetes agent image
docker build -f Dockerfile.kubernetes -t wrktalk-agent:latest .

# Load into Minikube
minikube image load wrktalk-agent:latest
```

### 3. Create Kubernetes Resources

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
  resources: ["pods", "services", "configmaps", "secrets"]
  verbs: ["*"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets"]
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
```

### 4. Deploy Agent to Minikube

```bash
kubectl apply -f k8s/agent-deployment.yaml
```

### 5. Check Agent Logs

```bash
# Watch agent logs
kubectl logs -f -n wrktalk deployment/wrktalk-agent

# Check if agent is running
kubectl get pods -n wrktalk
```

### 6. Test Deployment

With mock backend running on your host and MinIO accessible, the agent should:
1. Poll the backend (via host.minikube.internal:3000)
2. Download artifacts from MinIO (via host.minikube.internal:9000)
3. Execute Helm deployments in the wrktalk namespace

## Environment Variables Reference

See [.env.example](.env.example) for all available configuration options.

Key variables:
- `WRKTALK_AGENT_DEPLOYMENT_TYPE`: `kubernetes` or `docker`
- `WRKTALK_AGENT_BACKEND_URL`: WrkTalk Backend API URL
- `WRKTALK_AGENT_MINIO_ENDPOINT`: MinIO server endpoint
- `WRKTALK_AGENT_MINIO_BUCKET_NAME`: Bucket name for artifacts

## Troubleshooting

### Agent not connecting to Backend
- Check `WRKTALK_AGENT_BACKEND_URL` is correct
- Verify network connectivity: `curl $BACKEND_URL/health`
- Check agent secret matches Backend configuration

### MinIO download failures
- Verify MinIO endpoint is reachable
- Check credentials are correct
- Ensure bucket and objects exist
- For Minikube: use `host.minikube.internal` instead of `localhost`

### Helm deployment failures
- Check Helm is installed: `helm version`
- Verify namespace exists
- Check ServiceAccount has proper RBAC permissions
- Review Helm logs with `--debug` flag

### Docker Compose failures
- Ensure Docker socket is mounted (for containerized agent)
- Check docker-compose is installed
- Verify images can be pulled from registry

## Project Structure

```
wrktalk-agent/
├── src/
│   └── wrktalk_agent/
│       ├── __init__.py
│       ├── __main__.py       # Entry point
│       ├── agent.py           # Main agent loop
│       ├── config.py          # Configuration
│       ├── client/
│       │   ├── backend.py     # Backend API client
│       │   └── bucket.py      # MinIO client
│       ├── executor/
│       │   ├── base.py        # Base executor
│       │   ├── helm.py        # Helm executor
│       │   └── compose.py     # Compose executor
│       └── utils/
│           ├── heartbeat.py   # Heartbeat thread
│           └── logging.py     # Logging setup
├── Dockerfile.kubernetes      # K8s agent image
├── Dockerfile.docker          # Docker agent image
├── requirements.txt
├── setup.py
└── README.md
```

## License

Proprietary - WrkTalk Engineering Team
