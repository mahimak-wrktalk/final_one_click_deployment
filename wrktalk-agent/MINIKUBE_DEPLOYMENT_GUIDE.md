# WrkTalk Agent v4.2 - Minikube Kubernetes Deployment Guide

Complete guide for deploying the agent in a Minikube Kubernetes cluster.

---

## Prerequisites

✅ Completed local environment setup (see [LOCAL_SETUP_GUIDE.md](LOCAL_SETUP_GUIDE.md))
✅ PostgreSQL running and accessible
✅ Minikube installed and running

---

## Part 1: Prepare Minikube Environment

### Step 1: Start Minikube with Sufficient Resources

```bash
# Stop existing Minikube (if running)
minikube stop

# Start Minikube with more resources
minikube start \
  --cpus=4 \
  --memory=8192 \
  --disk-size=20g \
  --driver=docker

# Verify Minikube is running
minikube status

# Expected output:
# minikube
# type: Control Plane
# host: Running
# kubelet: Running
# apiserver: Running
# kubeconfig: Configured
```

### Step 2: Enable Required Addons

```bash
# Enable ingress (optional, for external access)
minikube addons enable ingress

# Enable metrics-server (optional, for monitoring)
minikube addons enable metrics-server

# Verify addons
minikube addons list
```

### Step 3: Configure kubectl Context

```bash
# Set kubectl context to minikube
kubectl config use-context minikube

# Verify context
kubectl config current-context
# Output: minikube

# Test cluster access
kubectl cluster-info
kubectl get nodes
```

---

## Part 2: Deploy PostgreSQL in Minikube (Optional)

**Option A:** Use external PostgreSQL (localhost) - **Recommended for testing**

**Option B:** Deploy PostgreSQL inside Minikube - **For full cluster setup**

### Option B: Deploy PostgreSQL in Minikube

```bash
# Create PostgreSQL deployment
cat > postgres-deployment.yaml << 'YAML'
apiVersion: v1
kind: Namespace
metadata:
  name: wrktalk
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-config
  namespace: wrktalk
data:
  POSTGRES_DB: wrktalk
  POSTGRES_USER: wrktalk_user
  POSTGRES_PASSWORD: wrktalk_password
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: wrktalk
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: wrktalk
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:14-alpine
        ports:
        - containerPort: 5432
        envFrom:
        - configMapRef:
            name: postgres-config
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: wrktalk
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
  type: ClusterIP
YAML

# Deploy PostgreSQL
kubectl apply -f postgres-deployment.yaml

# Wait for PostgreSQL to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n wrktalk --timeout=300s

# Verify PostgreSQL is running
kubectl get pods -n wrktalk
```

### Initialize PostgreSQL Database in Minikube

```bash
# Copy schema file to PostgreSQL pod
kubectl cp schema.sql wrktalk/$(kubectl get pod -n wrktalk -l app=postgres -o jsonpath='{.items[0].metadata.name}'):/tmp/schema.sql

# Execute schema inside PostgreSQL pod
kubectl exec -n wrktalk deployment/postgres -- psql -U wrktalk_user -d wrktalk -f /tmp/schema.sql

# Insert configuration
cat > init_config.sql << 'SQL'
INSERT INTO deployment_config (
    id, deployment_type, namespace, helm_release_name,
    smtp_host, smtp_port, smtp_user, smtp_password, smtp_from
) VALUES (
    uuid_generate_v4(), 'kubernetes', 'wrktalk', 'wrktalk',
    'smtp.gmail.com', 587, 'your-email@gmail.com', 'your-app-password', 'noreply@wrktalk.com'
);

INSERT INTO admin (id, name, email, is_active, role) VALUES
    (uuid_generate_v4(), 'Admin User', 'admin@example.com', true, 'ADMIN');
SQL

kubectl cp init_config.sql wrktalk/$(kubectl get pod -n wrktalk -l app=postgres -o jsonpath='{.items[0].metadata.name}'):/tmp/init_config.sql
kubectl exec -n wrktalk deployment/postgres -- psql -U wrktalk_user -d wrktalk -f /tmp/init_config.sql
```

---

## Part 3: Build and Load Agent Docker Image

### Step 1: Build Docker Image

```bash
cd /Users/admin/Documents/vscode_testing/one_click_new_n/wrktalk-agent

# Build the image
docker build -f Dockerfile.kubernetes -t wrktalk-agent:v4.2 .

# Verify image was created
docker images | grep wrktalk-agent
```

### Step 2: Load Image into Minikube

```bash
# Load image to Minikube
minikube image load wrktalk-agent:v4.2

# Verify image is in Minikube
minikube ssh docker images | grep wrktalk-agent
```

---

## Part 4: Deploy Agent in Minikube

### Step 1: Update ConfigMap with Database Settings

Edit `k8s/agent-deployment.yaml`:

**For Option A (External PostgreSQL on localhost):**
```yaml
data:
  WRKTALK_AGENT_DB_HOST: "host.minikube.internal"  # Points to host machine
  WRKTALK_AGENT_DB_PORT: "5432"
  WRKTALK_AGENT_DB_NAME: "wrktalk"
  WRKTALK_AGENT_DB_USER: "wrktalk_user"
  WRKTALK_AGENT_DB_PASSWORD: "wrktalk_password"
  WRKTALK_AGENT_DB_SSL_MODE: "prefer"
```

**For Option B (PostgreSQL inside Minikube):**
```yaml
data:
  WRKTALK_AGENT_DB_HOST: "postgres.wrktalk.svc.cluster.local"
  WRKTALK_AGENT_DB_PORT: "5432"
  WRKTALK_AGENT_DB_NAME: "wrktalk"
  WRKTALK_AGENT_DB_USER: "wrktalk_user"
  WRKTALK_AGENT_DB_PASSWORD: "wrktalk_password"
  WRKTALK_AGENT_DB_SSL_MODE: "disable"  # Within cluster, SSL not needed
```

### Step 2: Deploy Agent

```bash
# Apply the deployment
kubectl apply -f k8s/agent-deployment.yaml

# Verify deployment
kubectl get deployments -n wrktalk

# Check pod status
kubectl get pods -n wrktalk
```

### Step 3: View Agent Logs

```bash
# Watch agent logs in real-time
kubectl logs -f deployment/wrktalk-agent -n wrktalk

# Expected output:
# {"event": "agent.initialized", "deployment_type": "kubernetes"}
# {"event": "agent.starting"}
# {"event": "database.pool.connected"}
# {"event": "agent.email_client_initialized"}
```

---

## Part 5: Upload Test Helm Chart and Create Task

### Step 1: Upload Chart to Database

```bash
# If using PostgreSQL in Minikube, port-forward to access it
kubectl port-forward -n wrktalk service/postgres 5432:5432 &

# Run upload script (same as local setup)
python upload_chart.py
# Note the artifact ID

# If port-forwarding, kill the background process
kill %1
```

### Step 2: Create Deployment Task

```bash
# Create task in database
python create_task.py <artifact-id-from-upload>
```

### Step 3: Monitor Agent Execution

```bash
# Watch agent logs
kubectl logs -f deployment/wrktalk-agent -n wrktalk

# You should see:
# {"event": "agent.task_received", "task_id": "..."}
# {"event": "agent.artifact_loaded", "version": "wrktalk-test-v1.0.0"}
# {"event": "helm.upgrade.starting", "release": "wrktalk"}
# {"event": "helm.upgrade.success", "revision": 1}
# {"event": "agent.task_completed"}
```

---

## Part 6: Verify Deployment

### Step 1: Check Helm Releases

```bash
# Get shell access to agent pod
kubectl exec -it deployment/wrktalk-agent -n wrktalk -- /bin/bash

# Inside the pod, check Helm releases
helm list -n wrktalk

# Expected output:
# NAME    NAMESPACE  REVISION  UPDATED                                 STATUS   CHART
# wrktalk wrktalk    1         2024-12-15 12:00:00.000000 +0000 UTC    deployed wrktalk-test-1.0.0

# Exit pod
exit
```

### Step 2: Check Deployed Resources

```bash
# View all resources in wrktalk namespace
kubectl get all -n wrktalk

# Check deployment created by Helm
kubectl get deployment wrktalk-test -n wrktalk

# Check pods
kubectl get pods -n wrktalk -l app=wrktalk-test

# View pod logs
kubectl logs -l app=wrktalk-test -n wrktalk
```

### Step 3: Check Task Status in Database

```bash
# Port-forward to PostgreSQL (if in Minikube)
kubectl port-forward -n wrktalk service/postgres 5432:5432 &

# Query database
psql -U wrktalk_user -h localhost -d wrktalk << 'SQL'
SELECT id, type, status, completed_at, result 
FROM agent_task 
ORDER BY created_at DESC 
LIMIT 5;
SQL

# Kill port-forward
kill %1
```

---

## Part 7: Test Rollback

### Step 1: Deploy Second Version

```bash
# Upload another chart version (v2.0.0)
python upload_chart.py  # For wrktalk-test-2.0.0.tgz
python create_task.py <new-artifact-id>

# Wait for deployment to complete
kubectl logs -f deployment/wrktalk-agent -n wrktalk

# Verify new version is deployed
kubectl exec -it deployment/wrktalk-agent -n wrktalk -- helm list -n wrktalk
# Should show revision 2
```

### Step 2: Trigger Rollback

```bash
# Create rollback task
python << 'PYTHON'
import asyncio
import asyncpg

async def create_rollback():
    # Port-forward should be running: kubectl port-forward -n wrktalk service/postgres 5432:5432 &
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

asyncio.run(create_rollback())
PYTHON

# Monitor rollback
kubectl logs -f deployment/wrktalk-agent -n wrktalk

# Verify rollback completed
kubectl exec -it deployment/wrktalk-agent -n wrktalk -- helm list -n wrktalk
# Should show revision 3 (rollback to revision 1)
```

---

## Part 8: Access Agent Pod for Debugging

### SSH into Agent Pod

```bash
# Get pod name
kubectl get pods -n wrktalk -l app=wrktalk-agent

# Exec into pod
kubectl exec -it deployment/wrktalk-agent -n wrktalk -- /bin/bash

# Inside pod, you can:

# 1. Check Helm installations
helm list -n wrktalk

# 2. Check Kubernetes resources
kubectl get all -n wrktalk

# 3. View agent logs
tail -f /tmp/agent.log  # if logging to file

# 4. Test database connection
python << 'PYTHON'
import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect(
        host='postgres.wrktalk.svc.cluster.local',  # or host.minikube.internal
        port=5432,
        database='wrktalk',
        user='wrktalk_user',
        password='wrktalk_password'
    )
    count = await conn.fetchval('SELECT COUNT(*) FROM agent_task')
    print(f"Total tasks: {count}")
    await conn.close()

asyncio.run(test())
PYTHON

# Exit pod
exit
```

---

## Part 9: Scaling and High Availability

### Run Multiple Agent Replicas

```bash
# Scale agent deployment
kubectl scale deployment/wrktalk-agent -n wrktalk --replicas=3

# Verify multiple pods
kubectl get pods -n wrktalk -l app=wrktalk-agent

# Watch logs from all pods
kubectl logs -f deployment/wrktalk-agent -n wrktalk --all-containers=true

# Each agent will pick different tasks due to FOR UPDATE SKIP LOCKED
```

---

## Part 10: Monitoring and Maintenance

### View Agent Metrics

```bash
# Get pod resource usage
kubectl top pods -n wrktalk

# View pod events
kubectl get events -n wrktalk --sort-by='.lastTimestamp'

# Check pod restart count
kubectl get pods -n wrktalk -o wide
```

### Check Database Metrics

```bash
# Port-forward to PostgreSQL
kubectl port-forward -n wrktalk service/postgres 5432:5432 &

# Query metrics
psql -U wrktalk_user -h localhost -d wrktalk << 'SQL'
-- Active tasks
SELECT COUNT(*) FROM agent_task WHERE status = 'inProgress';

-- Recent heartbeats
SELECT id, last_heartbeat, NOW() - last_heartbeat as age
FROM agent_task 
WHERE status = 'inProgress'
ORDER BY last_heartbeat DESC;

-- Last agent poll
SELECT last_agent_poll, NOW() - last_agent_poll as time_since_poll
FROM deployment_config;
SQL

kill %1
```

### Update Agent Deployment

```bash
# After making code changes, rebuild image
docker build -f Dockerfile.kubernetes -t wrktalk-agent:v4.2 .

# Load new image to Minikube
minikube image load wrktalk-agent:v4.2

# Restart deployment
kubectl rollout restart deployment/wrktalk-agent -n wrktalk

# Watch rollout status
kubectl rollout status deployment/wrktalk-agent -n wrktalk
```

---

## Part 11: Cleanup

### Remove All Resources

```bash
# Delete agent deployment
kubectl delete -f k8s/agent-deployment.yaml

# Delete PostgreSQL (if deployed in Minikube)
kubectl delete -f postgres-deployment.yaml

# Delete namespace
kubectl delete namespace wrktalk

# Stop Minikube
minikube stop

# Delete Minikube cluster (optional)
minikube delete
```

---

## Troubleshooting

### Issue: Agent pod in CrashLoopBackOff

```bash
# Check pod logs
kubectl logs deployment/wrktalk-agent -n wrktalk

# Check pod events
kubectl describe pod -l app=wrktalk-agent -n wrktalk

# Common causes:
# - Database connection failed
# - Missing environment variables
# - Image not loaded to Minikube
```

### Issue: Can't connect to PostgreSQL on host

```bash
# Verify host.minikube.internal resolves
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup host.minikube.internal

# Test connection from pod
kubectl run -it --rm psql --image=postgres:14 --restart=Never -- \
  psql -h host.minikube.internal -U wrktalk_user -d wrktalk

# If fails, check PostgreSQL is listening on all interfaces
# In postgresql.conf: listen_addresses = '*'
# In pg_hba.conf: host all all 0.0.0.0/0 md5
```

### Issue: Helm deployment fails

```bash
# Check agent has proper RBAC permissions
kubectl auth can-i create deployments --namespace=wrktalk --as=system:serviceaccount:wrktalk:wrktalk-agent

# Check if chart was extracted correctly
kubectl exec -it deployment/wrktalk-agent -n wrktalk -- ls -la /tmp/wrktalk-deploy-*

# View full Helm output
kubectl logs deployment/wrktalk-agent -n wrktalk | grep helm
```

---

## Next Steps

✅ Agent successfully deployed in Minikube
✅ Test deployments working
✅ Rollback tested

Now you can:
1. Test with real application Helm charts
2. Set up production PostgreSQL with backups
3. Configure email notifications
4. Deploy to production Kubernetes cluster

---

## Production Deployment Checklist

Before deploying to production:

- [ ] Use PostgreSQL with persistent storage and backups
- [ ] Store database credentials in Kubernetes Secrets
- [ ] Configure SMTP with valid credentials
- [ ] Set up monitoring and alerting
- [ ] Test rollback procedures
- [ ] Configure resource limits for agent pod
- [ ] Set up log aggregation (ELK, Loki, etc.)
- [ ] Enable TLS for database connections
- [ ] Configure pod anti-affinity for HA
- [ ] Set up health checks and readiness probes

