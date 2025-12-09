# WrkTalk Agent - Quick Start Guide

## 🚀 Get Started in 5 Minutes

This guide will get you running the WrkTalk Agent locally with a mock backend.

## Prerequisites

- Python 3.11+
- Helm 3.x (for Kubernetes testing)
- MinIO running at localhost:9000/9001
- Docker (optional, for Docker Compose testing)

## Step 1: Setup

```bash
cd wrktalk-agent

# Automated setup
make setup

# Or manual setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install fastapi uvicorn
cp .env.example .env
```

## Step 2: Configure

The `.env` file is already configured for local testing with your MinIO setup:

```bash
cat .env
# Should show:
# WRKTALK_AGENT_MINIO_ENDPOINT=localhost:9000
# WRKTALK_AGENT_MINIO_ACCESS_KEY=admin
# WRKTALK_AGENT_MINIO_SECRET_KEY=admin123
# WRKTALK_AGENT_MINIO_BUCKET_NAME=wrktalk-artifacts
```

## Step 3: Prepare MinIO

### Create Test Helm Chart

```bash
# Create basic chart
mkdir -p test-chart/templates

cat > test-chart/Chart.yaml << 'EOF'
apiVersion: v2
name: wrktalk
version: 2.3.0
description: Test chart
EOF

cat > test-chart/values.yaml << 'EOF'
backend:
  image:
    repository: nginx
    tag: latest
EOF

cat > test-chart/templates/deployment.yaml << 'EOF'
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

# Package it
helm package test-chart
```

### Upload to MinIO

1. Open http://localhost:9001
2. Login: admin / admin123
3. Go to bucket: `wrktalk-artifacts`
4. Create folders: `artifacts/helm/` and `config/`
5. Upload `wrktalk-2.3.0.tgz` to `artifacts/helm/`
6. Upload `test-chart/values.yaml` to `config/values.yaml`

## Step 4: Run Mock Backend

**Terminal 1:**
```bash
source venv/bin/activate
python tests/mock_backend.py
```

You should see:
```
Mock WrkTalk Backend Server
Starting on http://localhost:3000
```

## Step 5: Run Agent

**Terminal 2:**
```bash
source venv/bin/activate

# Export environment variables
export $(cat .env | xargs)

# Run agent
python -m wrktalk_agent
```

Or use make:
```bash
make run-agent
```

You should see:
```json
{"event": "agent.starting", ...}
{"event": "agent.no_tasks", ...}
```

## Step 6: Create Test Task

**Terminal 3:**
```bash
./tests/create_test_task.sh
```

Or manually:
```bash
curl -X POST http://localhost:3000/test/add-task \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-001",
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

## Step 7: Watch It Work! 🎉

In Terminal 2 (agent), you'll see:
```json
{"event": "agent.task_received", "task_id": "test-001", "task_type": "deploy"}
{"event": "minio.downloading", "object_path": "artifacts/helm/wrktalk-2.3.0.tgz"}
{"event": "helm.upgrade.starting", ...}
{"event": "helm.upgrade.success", "revision": 1}
{"event": "agent.task_completed", ...}
```

In Terminal 1 (backend), you'll see:
```
[2024-01-15 10:00:00] 📝 Task added: test-001
[2024-01-15 10:00:10] Returning task: test-001
[2024-01-15 10:00:11] Task test-001 status: inProgress
[2024-01-15 10:01:11] ❤️  Heartbeat from task test-001
[2024-01-15 10:02:00] Task test-001 status: completed
  Result: {'status': 'success', 'helmRevision': 1}
```

## Verify Deployment

```bash
# Check Helm releases
helm list -n wrktalk

# Check Kubernetes resources
kubectl get all -n wrktalk
```

## Common Commands

```bash
# View all tasks
curl http://localhost:3000/test/tasks | jq

# View config store
curl http://localhost:3000/test/config | jq

# Clear all tasks
curl -X DELETE http://localhost:3000/test/clear

# Run agent with debug logging
make run-agent-debug

# Check status
make status
```

## Testing in Minikube

```bash
# Start minikube
minikube start

# Build and deploy
make minikube-deploy

# Watch logs
make minikube-logs

# Create test task (in another terminal)
./tests/create_test_task.sh
```

## Troubleshooting

### Agent not connecting to backend
```bash
# Check backend is running
curl http://localhost:3000

# Check environment
echo $WRKTALK_AGENT_BACKEND_URL
```

### MinIO connection failed
```bash
# Test MinIO
curl http://localhost:9000/minio/health/live

# Check credentials in .env
grep MINIO .env
```

### Helm command not found
```bash
# Install Helm
brew install helm  # macOS

# Verify
helm version
```

### Task not executing
```bash
# Check task queue
make view-tasks

# The executeAfter time must be in the past!
# Default is "2024-01-01T00:00:00Z" which is fine
```

## Next Steps

1. ✅ **Local testing works** → Read [TESTING_GUIDE.md](TESTING_GUIDE.md) for advanced testing
2. 🔨 **Implement Backend APIs** → See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for required endpoints
3. 🚀 **Deploy to Production** → Build Docker images and deploy to your K8s cluster

## File Structure

```
wrktalk-agent/
├── src/wrktalk_agent/        # Agent source code
│   ├── agent.py               # Main agent loop
│   ├── config.py              # Configuration
│   ├── client/                # API clients (Backend, MinIO)
│   ├── executor/              # Deployment executors (Helm, Compose)
│   └── utils/                 # Utilities (heartbeat, logging)
├── tests/
│   ├── mock_backend.py        # Mock WrkTalk Backend
│   └── create_test_task.sh    # Create test deployment
├── k8s/
│   └── agent-deployment.yaml  # Kubernetes manifests
├── Dockerfile.kubernetes      # K8s agent image
├── Dockerfile.docker          # Docker agent image
├── Makefile                   # Convenience commands
├── .env.example               # Configuration template
├── requirements.txt           # Python dependencies
└── README.md                  # Full documentation
```

## Questions?

- **Full documentation**: [README.md](README.md)
- **Testing guide**: [TESTING_GUIDE.md](TESTING_GUIDE.md)
- **Architecture**: [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
- **Your spec doc**: [../one_click_deployment.md](../one_click_deployment.md)

Happy deploying! 🚀
