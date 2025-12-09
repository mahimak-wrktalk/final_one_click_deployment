# WrkTalk Unified Deployment System
## Technical Specification Document v1
**Version:** 1.0  
**Date:** December 2024  
**Status:** Final Architecture Draft

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Storage Architecture](#3-storage-architecture)
4. [Environment Variable Architecture](#4-environment-variable-architecture)
5. [Complete Release Flow](#5-complete-release-flow)
6. [Agent Architecture](#6-agent-architecture)
7. [Communication Model](#7-communication-model)
8. [Error Cases & Recovery Procedures](#8-error-cases--recovery-procedures)
9. [Rollback Procedures](#9-rollback-procedures)
10. [Scheduling & Deadlines](#10-scheduling--deadlines)
11. [Health Monitoring](#11-health-monitoring)
12. [GCC Schema Extensions](#12-gcc-schema-extensions)
13. [Customer Backend Schema Extensions](#13-customer-backend-schema-extensions)
14. [API Specifications](#14-api-specifications)
15. [Python Agent Implementation](#15-python-agent-implementation)
16. [Implementation Roadmap](#16-implementation-roadmap)

---

## 1. Executive Summary

### 1.1 Purpose

This document specifies the Unified Deployment System for WrkTalk, enabling automated software releases across 100k+ customers deployed on Kubernetes and Docker Compose environments.

### 1.2 Stack Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TECHNOLOGY STACK                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  GCC (Global Control Center)                                                │
│  ├─ Framework: NestJS                                                       │
│  ├─ ORM: Prisma                                                             │
│  ├─ Database: PostgreSQL                                                    │
│  ├─ Bucket: AWS S3 (for chart storage)                                      │
│  ├─ SMTP: For internal GCC team notifications only                          │
│  └─ Purpose: Release management, chart hosting, webhook dispatcher          │
│                                                                              │
│  Customer Backend (= WrkTalk Backend, SAME APPLICATION)                     │
│  ├─ Framework: NestJS (existing)                                            │
│  ├─ ORM: Prisma (existing)                                                  │
│  ├─ Database: PostgreSQL (existing)                                         │
│  ├─ Bucket: Customer's own (S3/Azure/GCS/MinIO)                             │
│  ├─ SMTP: For customer admin notifications                                  │
│  └─ Purpose: Main messaging app + deployment features (extended)            │
│                                                                              │
│  Control Tower                                                              │
│  ├─ Framework: React (separate app)                                         │
│  ├─ Type: Client admin dashboard                                            │
│  └─ Purpose: Env var editing, deployment scheduling, status viewing         │
│                                                                              │
│  Agent (NEW - ONLY PYTHON COMPONENT)                                        │
│  ├─ Language: Python 3.11+                                                  │
│  ├─ Type: Pure daemon (no HTTP server)                                      │
│  ├─ State: Stateless (queries Backend for everything)                       │
│  ├─ K8s: Uses Helm CLI + in-cluster ServiceAccount                          │
│  ├─ Compose: Uses docker-compose CLI + socket mount                         │
│  └─ Purpose: Helm/Compose execution, env insertion                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Agent Language** | Python 3.11+ | Only Python component. Pure daemon. |
| **Agent Pattern** | Poll-based worker | No HTTP server. Polls Backend for tasks. |
| **Agent State** | Stateless | All state in Backend DB. Agent queries as needed. |
| **Multi-Agent** | Not Supported | Single Agent per customer environment. |
| **Helm Execution** | CLI (`helm upgrade --atomic`) | Full Helm features, atomic rollback, hooks. |
| **Docker Compose** | CLI + Socket Mount | Required for container orchestration. |
| **K8s Auth** | In-cluster ServiceAccount | No kubeconfig management at GCC. |
| **Chart Hosting** | GCC bucket (S3) | CI uploads to GCC, customers download from GCC. |
| **Chart Retention** | 20 at GCC, 10 at customer | GCC keeps more for fallback downloads. |
| **Essential Envs** | ConfigMaps (K8s) / .env file (Compose) | Managed manually by WrkTalk team. |     ## Doubt- vishal sir was saying we are going to use. 
| **Non-Essential Envs** | Backend Database | Editable via Control Tower, read at runtime. |             ## Doubt- 
| **Forced Update Deadline** | Escalate only | No auto-deploy after 24h, wait for manual action. |
| **License Check** | Block at Backend/Agent | If license expires, block deployment. |
| **Task Timeout** | Heartbeat-based + 30min initial | Long migrations can exceed 1 hour. |
| **Missed Schedule** | Require re-schedule | No auto-execute if window passed. |

### 1.4 Notification Responsibility

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NOTIFICATION RESPONSIBILITIES                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CUSTOMER BACKEND sends to ADMINS (from `admin` table):                     │
│  ├─ New release available                                                   │
│  ├─ Forced update warnings (T+0, T+12h, T+20h, T+24h)                       │
│  ├─ Migration downtime notices                                              │
│  ├─ Deployment scheduled/started/success/failed                             │
│  ├─ Agent offline alerts                                                    │
│  └─ All operational notifications                                           │
│                                                                              │
│  GCC sends INTERNALLY to:                                                   │
│  ├─ Account Manager (escalations, deployment failures)                      │
│  └─ GCC Admin team (critical alerts, license issues)                        │
│                                                                              │
│  GCC stores for MANUAL outreach:                                            │
│  ├─ SPOC contact info                                                       │
│  └─ Account Manager assignment                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Overview

### 2.1 System Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GLOBAL CONTROL CENTER (GCC)                          │
│                                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │   Release    │ │    Chart     │ │   Webhook    │ │   Health     │       │
│  │   Manager    │ │   Storage    │ │  Dispatcher  │ │   Monitor    │       │
│  │              │ │              │ │              │ │              │       │
│  │ • Versions   │ │ • S3 Bucket  │ │ • Push       │ │ • Heartbeat  │       │
│  │ • Rulesets   │ │ • 20 charts  │ │ • Retry 2x   │ │ • Version    │       │
│  │ • Targets    │ │ • SHA256     │ │ • @60sec     │ │ • Uptime     │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                                              │
│  GCC Bucket (S3):                                                           │
│  └── charts/                                                                │
│      ├── wrktalk-2.3.0.tgz                                                 │
│      ├── wrktalk-2.3.0-compose.tar.gz                                      │
│      └── ... (max 20 versions)             ## doubt: why need this                                     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
         │                                              ▲
         │ Webhook (Push)                               │ Heartbeat + Poll
         ▼                                              │
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CUSTOMER ENVIRONMENT (Kubernetes)                         │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │              WRKTALK BACKEND (Existing NestJS App)                      ││
│  │                                                                          ││
│  │  EXISTING:                     NEW MODULES:                             ││
│  │  • User management             • Webhook Receiver                       ││
│  │  • Messaging                   • GCC Poller + Heartbeat                 ││
│  │  • Groups                      • Chart Downloader                       ││
│  │  • Admin panel                 • Deployment Scheduler                   ││
│  │  • SMTP integration            • Agent Task Queue                       ││
│  │  • Non-essential env table     • License Validator                      ││
│  │                                                                          ││
│  │  Customer Bucket:                                                       ││
│  │  ├── artifacts/helm/wrktalk-*.tgz (max 10)    --- ## doubt: why need this                          ││
│  │  └── config/values.yaml                                                 ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                          │                                                  │
│                GET /internal/agent/tasks                                   │
│                          ▼                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │                    PYTHON AGENT (Stateless Daemon)                      ││
│  │                                                                          ││
│  │  • Polls Backend every 30 seconds                                       ││
│  │  • Downloads chart from customer bucket                                 ││
│  │  • Inserts non-essential envs via API                                   ││
│  │  • Runs: helm upgrade --atomic --wait                                   ││
│  │  • Sends heartbeat during long tasks                                    ││
│  │  • Reports status back to Backend                                       ││
│  │  • Uses ServiceAccount (in-cluster auth)                                ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                          │                                                  │
│                          ▼                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │                    KUBERNETES CLUSTER                                   ││
│  │  • Helm manages deployments                                             ││
│  │  • ConfigMaps for essential envs                                        ││
│  │  • Secrets for GHCR pull (global imagePullSecrets)                     ││
│  │  • Release history in cluster secrets         ## Doubt- why release history here?                           ││
│  └────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    CUSTOMER ENVIRONMENT (Docker Compose)                     │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │              WRKTALK BACKEND (Same as K8s)                              ││
│  │                                                                          ││
│  │  Customer Bucket:                                                       ││
│  │  ├── artifacts/compose/wrktalk-*-compose.tar.gz (max 10)               ││
│  │  └── config/                                                            ││
│  │      ├── .env (current - symlink)                                       ││
│  │      ├── .env.v2.3.0 (versioned for rollback)                          ││
│  │      ├── .env.v2.2.0                                                    ││
│  │      └── ...                                                            ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                          │                                                  │
│                GET /internal/agent/tasks                                   │
│                          ▼                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │                    PYTHON AGENT (Docker Compose)                        ││
│  │                                                                          ││
│  │  • Same poll-based pattern                                              ││
│  │  • Downloads compose bundle from bucket                                 ││
│  │  • Downloads .env from bucket                                           ││
│  │  • Runs: docker-compose up -d                                           ││
│  │  • NO atomic rollback (Compose limitation)                              ││
│  │  • Docker socket mount required                                         ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                          │                                                  │
│                          ▼                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │                    DOCKER HOST                                          ││
│  │  • docker-compose manages containers                                    ││
│  │  • .env file for essential envs                                         ││
│  │  • docker login for GHCR auth                                           ││
│  │  • No built-in release history                                          ││
│  └────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Kubernetes vs Docker Compose Comparison

| Aspect | Kubernetes | Docker Compose |
|--------|------------|----------------|
| **Artifact** | `wrktalk-2.3.0.tgz` (Helm chart) | `wrktalk-2.3.0-compose.tar.gz` |
| **Essential Envs** | ConfigMaps (via Helm values) | `.env` file in bucket |
| **Env Versioning** | Helm release history | `.env.v{version}` files |
| **Deployment Command** | `helm upgrade --atomic` | `docker-compose up -d` |
| **Auto-Rollback** | YES (--atomic flag) | NO |
| **Auth** | ServiceAccount (in-cluster) | Docker socket mount |
| **Image Pull Auth** | imagePullSecrets in Helm | `docker login` |
| **Release History** | Stored in K8s secrets | Manual (bucket versioning) |
| **Rollback Command** | `helm rollback` | Re-deploy old version |

---

## 3. Storage Architecture

### 3.1 GCC Bucket (AWS S3)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GCC BUCKET STRUCTURE                                 │
│                                                                              │
│  s3://gcc-wrktalk-artifacts/                                                │
│  └── charts/                                                                │
│      ├── helm/                                                              │
│      │   ├── wrktalk-2.3.0.tgz                                             │
│      │   ├── wrktalk-2.2.0.tgz                                             │
│      │   ├── wrktalk-2.1.0.tgz                                             │
│      │   └── ... (max 20 versions)                                         │
│      │                                                                      │
│      └── compose/                                                           │
│          ├── wrktalk-2.3.0-compose.tar.gz                                  │
│          ├── wrktalk-2.2.0-compose.tar.gz                                  │
│          └── ... (max 20 versions)                                         │
│                                                                              │
│  Retention Policy:                                                          │
│  • Keep last 20 versions per type (helm/compose)                           │
│  • Cleanup on new upload: delete oldest if > 20                            │
│  • Each chart: ~50-100KB                                                   │
│  • Total storage: ~4MB (negligible)                                        │
│                                                                              │
│  Access:                                                                    │
│  • Jenkins: Write (upload new charts)                                      │
│  • Customers: Read (download via authenticated API)                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Customer Bucket Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CUSTOMER BUCKET STRUCTURE (Kubernetes)                    │
│                                                                              │
│  s3://customer-wrktalk/                (or Azure/GCS/MinIO)                │
│  ├── artifacts/                                                             │
│  │   └── helm/                                                              │
│  │       ├── wrktalk-2.3.0.tgz   ← Current                                 │
│  │       ├── wrktalk-2.2.0.tgz   ← Previous (rollback target)              │
│  │       ├── wrktalk-2.1.0.tgz                                             │
│  │       └── ... (max 10 versions)                                         │
│  │                                                                          │
│  └── config/                                                                │
│      └── values.yaml   ← Domain-level config (client domain, etc.)    ## doubt- what is this     │
│                                                                              │
│  Note: Essential envs (DATABASE_URL, etc.) are NOT in bucket.              │
│        They are in Helm chart's configMap.yaml, managed manually.    ## new doubt- why not this?       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    CUSTOMER BUCKET STRUCTURE (Docker Compose)                │
│                                                                              │
│  s3://customer-wrktalk/                (or Azure/GCS/MinIO)                │
│  ├── artifacts/                                                             │
│  │   └── compose/                                                           │
│  │       ├── wrktalk-2.3.0-compose.tar.gz                                  │
│  │       ├── wrktalk-2.2.0-compose.tar.gz                                  │
│  │       └── ... (max 10 versions)                                         │
│  │                                                                          │
│  └── config/                                                                │
│      ├── .env           ← Symlink to current version                       │
│      ├── .env.v2.3.0    ← Current essential envs                           │
│      ├── .env.v2.2.0    ← Previous (for rollback)                          │
│      ├── .env.v2.1.0                                                       │
│      └── ... (versioned for rollback support)                    ## doubt- what is this            │
│                                                                              │
│  Compose Bundle Contents:                                                   │
│  wrktalk-2.3.0-compose.tar.gz                                               │
│  └── wrktalk/                                                               │
│      ├── docker-compose.yaml                                                │
│      ├── docker-compose.override.yaml (optional)                           │
│      └── config/                                                            │
│          └── nginx.conf (or other static configs)                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Environment Variable Architecture

### 4.1 Classification

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ENVIRONMENT VARIABLE CLASSIFICATION                       │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════   │
│  ESSENTIAL ENVS (Sensitive)                                                 │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Examples:                                                                  │
│  • DATABASE_URL                                                             │
│  • REDIS_URL                                                                │
│  • JWT_SECRET                                                               │
│  • SMTP_PASSWORD                                                            │
│  • Other connection strings and secrets                                     │
│                                                                              │
│  Kubernetes:                                                                │
│  • Storage: ConfigMaps (created via Helm chart templates)   ## Doubts: are we going to use different configmap for all the cleints?- we can do one thing will store the secret  in bucket too.             │
│  • Location: charts/wrktalk/templates/configmap.yaml                        │
│  • Changed by: WrkTalk team manually (edit + helm upgrade)                 │
│  • Control Tower: CANNOT edit                                               │
│  • Rollback: YES (Helm restores previous ConfigMap)                        │
│                                                                              │
│  Docker Compose:                                                            │
│  • Storage: .env file in customer bucket                                   │
│  • Location: config/.env.v{version}                                        │
│  • Changed by: WrkTalk team manually                                       │
│  • Control Tower: CANNOT edit                                               │
│  • Rollback: YES (use previous .env.v{version} file)       ## Doubt- didn't get, for rollback in docker- are we going to storage the image tag in .env?      │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════   │
│  NON-ESSENTIAL ENVS (Non-sensitive)                               ## Doubt- didn't get  non-essential and essential env how you planed it to deploy and rollback.        │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Examples:                                                                  │
│  • Feature flags (FEATURE_X_ENABLED)                                       │
│  • Log levels (LOG_LEVEL)                                                  │
│  • UI configuration (THEME, LOCALE)                                        │
│  • Rate limits (API_RATE_LIMIT)                                            │
│                                                                              │
│  Both K8s and Compose:                                                      │
│  • Storage: Backend Database (config table)                                │
│  • How app reads: Queries its own DB at runtime                            │
│  • Control Tower: CAN edit                                                  │
│  • New envs from release: Agent calls POST /internal/config               │
│  • Rollback: NO (cannot be rolled back)                                    │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════   │
│  VALUES.YAML (Domain Config)                    ## doubt- where r u going to store it?                            │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Contains:                                                                  │
│  • Client domain name                                                       │
│  • Ingress configuration                                                    │
│  • Resource limits (optional overrides)                                    │
│  • Other domain-specific settings                                          │
│                                                                              │
│  Does NOT contain: Essential envs (those are in configMap.yaml)            │
│  Storage: Customer bucket (config/values.yaml)                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 How Non-Essential Envs Reach the Application

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NON-ESSENTIAL ENV FLOW                                    │
│                                                                              │
│  1. Admin edits in Control Tower                                            │
│     POST /api/admin/config                                                  │
│     { "key": "FEATURE_X", "value": "true" }                                │
│                                                                              │
│  2. Backend stores in database                                              │
│     Table: nonEssentialEnv                                                  │
│     { key: "FEATURE_X", value: "true", updatedAt: now }                    │
│                                                                              │
│  3. Application reads at runtime                                            │
│     Backend service: ConfigService.get("FEATURE_X")                        │
│     → Queries database                                                      │
│     → Returns "true"                                                        │
│                                                                              │
│  4. New release adds new non-essential env                                  │
│     Release includes: newNonEssentialEnvs: [{ key: "NEW_FLAG", value: "false" }]
│     Agent: POST /internal/config                                           │
│     Backend: Inserts with default value                                    │
│     No restart needed (read at runtime)                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Complete Release Flow

### 5.1 CI Pipeline to GCC

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 1: CI PIPELINE (Jenkins)                             │
│                                                                              │
│  Jenkinsfile:                                                               │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│  stage('Build Images') {                                                    │
│    sh '''                                                                   │
│      docker build -t ghcr.io/wrktalk/backend:${TAG} ./backend              │
│      docker build -t ghcr.io/wrktalk/media:${TAG} ./media                  │
│      docker build -t ghcr.io/wrktalk/control-tower:${TAG} ./control-tower  │
│      docker build -t ghcr.io/wrktalk/agent:${TAG} ./agent                  │
│                                                                              │
│      docker push ghcr.io/wrktalk/backend:${TAG}                            │
│      docker push ghcr.io/wrktalk/media:${TAG}                              │
│      docker push ghcr.io/wrktalk/control-tower:${TAG}                      │
│      docker push ghcr.io/wrktalk/agent:${TAG}                              │
│    '''                                                                      │
│  }                                                                           │
│                                                                              │
│  stage('Package Helm Chart') {                                              │
│    sh '''                                                                   │
│      helm package ./charts/wrktalk --version ${VERSION}                    │
│      # Produces: wrktalk-${VERSION}.tgz                                    │
│    '''                                                                      │
│  }                                                                           │
│                                                                              │
│  stage('Package Compose Bundle') {                                          │
│    sh '''                                                                   │
│      tar -czvf wrktalk-${VERSION}-compose.tar.gz ./compose/wrktalk         │
│    '''                                                                      │
│  }                                                                           │
│                                                                              │
│  stage('Upload to GCC') {                                                   │
│    sh '''                                                                   │
│      # Upload Helm chart                                                   │
│      curl -X POST https://gcc.wrktalk.com/api/internal/artifacts \         │
│        -H "Authorization: Bearer ${GCC_CI_TOKEN}" \                         │
│        -F "file=@wrktalk-${VERSION}.tgz" \                                 │
│        -F "type=helm" \                                                     │
│        -F "version=${VERSION}"                                              │
│                                                                              │
│      # Upload Compose bundle                                                │
│      curl -X POST https://gcc.wrktalk.com/api/internal/artifacts \         │
│        -H "Authorization: Bearer ${GCC_CI_TOKEN}" \                         │
│        -F "file=@wrktalk-${VERSION}-compose.tar.gz" \                      │
│        -F "type=compose" \                                                  │
│        -F "version=${VERSION}"                                              │
│    '''                                                                      │
│  }                                                                           │
│                                                                              │
│  stage('Create Release in GCC') {                                           │
│    sh '''                                                                   │
│      curl -X POST https://gcc.wrktalk.com/api/internal/releases \          │
│        -H "Authorization: Bearer ${GCC_CI_TOKEN}" \                         │
│        -H "Content-Type: application/json" \                                │
│        -d '{                                                                │
│          "version": "${VERSION}",                                          │
│          "imageTags": {                                                     │
│            "backend": "${BACKEND_TAG}",                                    │
│            "media": "${MEDIA_TAG}",                                        │
│            "controlTower": "${CT_TAG}",                                    │
│            "agent": "${AGENT_TAG}"                                         │
│          },                                                                 │
│          "isForced": false,                                                │
│          "isMigrationRequired": false,                                     │
│          "releaseNotes": "...",                                            │
│          "newNonEssentialEnvs": [                                          │
│            { "key": "NEW_FEATURE", "value": "false" }                     │
│          ]                                                                  │
│        }'                                                                   │
│    '''                                                                      │
│  }                                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 GCC Stores and Distributes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 2: GCC STORES CHART                                  │
│                                                                              │
│  GCC receives upload:                                                       │
│  1. Validate CI token                                                       │
│  2. Compute SHA256 checksum                                                 │
│  3. Upload to S3:                           ## doubt- Why?                                │
│     • charts/helm/wrktalk-2.3.0.tgz                                        │
│     • charts/compose/wrktalk-2.3.0-compose.tar.gz                          │
│  4. Store reference in database                                             │
│  5. Cleanup old versions (keep 20)                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 3: GCC SENDS WEBHOOK                                 │
│                                                                              │
│  For each customer (based on deployment targets):                           │
│                                                                              │
│  1. Check license validity                                                  │
│     • If expired: Skip, create LICENSE_EXPIRED escalation                  │
│                                                                              │
│  2. Check min version requirement                                           │
│     • If customer.version < release.minVersion: Skip, escalate             │
│                                                                              │
│  3. Send webhook:                                                           │
│     POST https://customer.example.com/api/deployment/webhook               │
│     Headers:                                                                │
│       X-Webhook-Signature: HMAC-SHA256(payload, webhookSecret)             │
│       Content-Type: application/json                                        │
│                                                                              │
│     Body:                                                                   │
│     {                                                                        │
│       "eventType": "release.published",                                    │
│       "release": {                                                          │
│         "id": "rel-uuid",                                                  │
│         "version": "2.3.0",                                                │
│         "chartVersion": "2.3.0",                                           │
│         "chartSha256": "abc123...",                                        │
│         "imageTags": {                                                      │
│           "backend": "sha-abc123",                                         │
│           "media": "sha-def456",                                           │
│           "controlTower": "sha-ghi789",                                    │
│           "agent": "sha-jkl012"                                            │
│         },                                                                  │
│         "newNonEssentialEnvs": [                                           │
│           { "key": "NEW_FEATURE", "value": "false" }                      │
│         ]                                                                   │
│       },                                                                    │
│       "ruleset": {                                                          │
│         "isForced": false,                                                 │
│         "isMigrationRequired": false,                                      │
│         "estimatedDowntime": null,                                         │
│         "releaseNotes": "Bug fixes and improvements"                       │
│       }                                                                     │
│     }                                                                        │
│                                                                              │
│  4. Handle response:                                                        │
│     • 200 OK: Mark webhookAcked = true                                     │
│     • 4xx/5xx: Retry 2x @ 60 seconds                                       │
│     • After 3 failures: Mark webhookFailed, wait for poll                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Customer Backend Receives

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 4: CUSTOMER BACKEND RECEIVES                         │
│                                                                              │
│  1. Validate webhook signature                                              │
│     computed = HMAC-SHA256(body, webhookSecret)                            │
│     if (computed !== header['X-Webhook-Signature']) reject 401             │
│                                                                              │
│  2. Check license locally                                                   │
│     if (license.expiresAt < now) reject 403 "License expired"             │
│                                                                              │
│  3. ACK immediately (async processing)                                      │
│     return 200 { "received": true }                                        │
│                                                                              │
│  4. Queue for async processing:                                             │
│     a. Determine artifact type (helm or compose based on deploymentType)  │
│     b. Download chart from GCC:                                             │
│        GET https://gcc.wrktalk.com/api/artifacts/charts/{version}         │
│        Params: type=helm (or compose)                                      │
│        Auth: Bearer {customerGccApiKey}                                    │
│                                                                              │
│     c. Verify SHA256 checksum                                               │
│        if mismatch: Retry 3x, then fail with alert                        │
│                                                                              │
│     d. Store in customer bucket:                                            │
│        K8s: artifacts/helm/wrktalk-2.3.0.tgz                              │
│        Compose: artifacts/compose/wrktalk-2.3.0-compose.tar.gz            │
│                                                                              │
│     e. Cleanup old versions (keep max 10)                                  │
│                                                                              │
│     f. Create scheduledDeployment record:                                  │
│        {                                                                    │
│          gccReleaseId: release.id,                                         │
│          releaseName: "v2.3.0",                                            │
│          releaseData: <full payload>,                                      │
│          isForced: false,                                                  │
│          forceDeadline: null,                                              │
│          status: "pending"                                                 │
│        }                                                                    │
│                                                                              │
│     g. Notify admins:                                                       │
│        "New release v2.3.0 available. Please schedule deployment."        │
│                                                                              │
│  5. If isForced:                                                            │
│     a. Set forceDeadline = now + 24 hours                                  │
│     b. Notify admins with urgency:                                         │
│        "FORCED UPDATE: v2.3.0 must be deployed within 24 hours"           │
│     c. Schedule reminders: 12h, 20h, 24h                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.4 Admin Schedules Deployment

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 5: ADMIN SCHEDULES                                   │
│                                                                              │
│  Control Tower UI:                                                          │
│  1. Admin views pending releases                                            │
│     GET /api/admin/deployment/releases?status=pending                      │
│                                                                              │
│  2. Admin optionally edits non-essential envs                              │
│     POST /api/admin/config                                                  │
│     { "key": "LOG_LEVEL", "value": "debug" }                               │
│                                                                              │
│  3. Admin schedules deployment                                              │
│     POST /api/admin/deployment/schedule                                    │
│     {                                                                        │
│       "deploymentId": "sd-uuid",                                           │
│       "scheduledFor": "2024-12-15T02:00:00Z"                               │
│     }                                                                        │
│                                                                              │
│  Backend:                                                                   │
│  1. Validate no other deployment in progress                               │
│     if (activeDeployment exists) return 409 "Deployment in progress"      │
│                                                                              │
│  2. Update scheduledDeployment:                                             │
│     status = "scheduled"                                                   │
│     scheduledFor = provided time                                           │
│     scheduledBy = admin.email                                              │
│                                                                              │
│  3. Create agentTask:                                                       │
│     {                                                                        │
│       type: "deploy",                                                       │
│       status: "pending",                                                   │
│       deploymentId: "sd-uuid",                                             │
│       executeAfter: scheduledFor,                                          │
│       payload: {                                                            │
│         chart: {                                                            │
│           bucketPath: "artifacts/helm/wrktalk-2.3.0.tgz",                 │
│           version: "2.3.0"                                                 │
│         },                                                                  │
│         imageTags: { backend: "sha-...", media: "sha-..." },              │
│         valuesBucketPath: "config/values.yaml",                           │
│         newNonEssentialEnvs: [{ key: "NEW_FEATURE", value: "false" }]     │
│       }                                                                     │
│     }                                                                        │
│                                                                              │
│  4. Report schedule to GCC:                                                 │
│     POST https://gcc.wrktalk.com/api/v1/deployments/scheduled             │
│     { organizationName, releaseId, scheduledFor }                          │
│                                                                              │
│  5. Notify admins:                                                          │
│     "Deployment v2.3.0 scheduled for 2024-12-15 02:00 UTC"                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.5 Agent Executes Deployment

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 6: AGENT EXECUTES (Kubernetes)                       │
│                                                                              │
│  Agent poll loop:                                                           │
│  1. GET /internal/agent/tasks                                              │
│     Response: { task: { ... } } or { task: null }                          │
│                                                                              │
│  2. If task exists and executeAfter <= now:                                │
│                                                                              │
│     a. Mark task as inProgress:                                             │
│        POST /internal/agent/tasks/{taskId}/status                          │
│        { "status": "inProgress", "pickedUpAt": now }                       │
│                                                                              │
│                            │
│                                                                              │
│     c. Insert new non-essential envs (if any):                             │
│        for each env in newNonEssentialEnvs:                                │
│          POST /internal/config                                              │
│          { "key": env.key, "value": env.value }                            │
│        (Continue even if this fails - log warning)                         │
│                                                                              │
│     d. Download chart from bucket:                                          │
│        s3://customer-bucket/artifacts/helm/wrktalk-2.3.0.tgz              │
│        → /tmp/wrktalk-2.3.0.tgz                                            │
│                                                                              │
│     e. Download values from bucket:                                         │
│        s3://customer-bucket/config/values.yaml                             │
│        → /tmp/values.yaml                                                   │
│                                                                              │
│     f. Start heartbeat thread:                                              │
│        Every 60 seconds: POST /internal/agent/tasks/{taskId}/heartbeat    │
│                                                                              │
│     g. Execute helm upgrade:                                                │
│        helm upgrade wrktalk /tmp/wrktalk-2.3.0.tgz \                       │
│          --namespace wrktalk \                                              │
│          --values /tmp/values.yaml \                                        │
│          --set backend.image.tag=sha-abc123 \                              │
│          --set media.image.tag=sha-def456 \                                │
│          --set controlTower.image.tag=sha-ghi789 \                         │
│          --set agent.image.tag=sha-jkl012 \      ## Doubt- why this?                             │
│          --atomic \                                                         │
│          --wait \                                                           │
│          --timeout 10m                                                      │
│                                                                              │
│     h. Stop heartbeat thread                                                │
│                                                                              │
│     i. Report success:                                                      │
│        POST /internal/agent/tasks/{taskId}/status                          │
│        {                                                                    │
│          "status": "completed",                                            │
│          "completedAt": now,                                               │
│          "result": {                                                        │
│            "helmRevision": 5,                                              │
│            "status": "success"                                             │
│          }                                                                  │
│        }                                                                    │
│                                                                              │
│     j. Cleanup temp files:                                                  │
│        Secure delete /tmp/wrktalk-2.3.0.tgz                                │
│        Secure delete /tmp/values.yaml          
│                                                                              │
│  3. On failure:                                                             │
│     • --atomic flag triggers auto-rollback                                 │
│     • Report failure:                                                       │
│       POST /internal/agent/tasks/{taskId}/status                           │
│       { "status": "failed", "errorMessage": stderr }                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 6: AGENT EXECUTES (Docker Compose)                   │
│                                                                              │
│  Same as Kubernetes until step (d), then:                                   │
│                                                                              │
│     d. Download compose bundle from bucket:                                 │
│        s3://.../artifacts/compose/wrktalk-2.3.0-compose.tar.gz            │
│        → Extract to /tmp/wrktalk/                                          │
│                                                                              │
│     e. Download .env from bucket:                                           │
│        s3://.../config/.env                                                │
│        → /tmp/wrktalk/.env                                                 │
│                                                                              │
│     f. Start heartbeat thread (same)                                       │
│                                                                              │
│     g. Execute docker-compose:                                              │
│        cd /tmp/wrktalk                                                      │
│        docker-compose pull                                                  │
│        docker-compose up -d --remove-orphans                               │
│                                                                              │
│        ⚠️ NO --atomic equivalent                                            │
│        ⚠️ Partial failure possible                                          │
│                                                                              │
│     h. Stop heartbeat thread                                                │
│                                                                              │
│     i. Report success/failure (same)                                        │
│                                                                              │
│     j. Cleanup (same)                                                       │
│                                                                              │
│  On failure:                                                                │
│     • NO auto-rollback (Compose doesn't support)                           │
│     • Report failure with detailed error                                   │
│     • Admin must manually rollback if needed                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.6 Backend Reports to GCC

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 7: BACKEND REPORTS TO GCC                            │
│                                                                              │
│  When Agent reports task completion:                                        │
│                                                                              │
│  1. Update scheduledDeployment:                                             │
│     status = "success" or "failed"                                         │
│     completedAt = now                                                       │
│     helmRevision = result.helmRevision (K8s only)                          │
│     errorMessage = result.errorMessage (if failed)                         │
│                                                                              │
│  2. Create deploymentHistory record                                        │
│                                                                              │
│  3. Notify admins:                                                          │
│     Success: "Deployment v2.3.0 completed successfully"                   │
│     Failure: "⚠️ Deployment v2.3.0 FAILED: {error}"                       │
│                                                                              │
│  4. Report to GCC:                                                          │
│     POST https://gcc.wrktalk.com/api/v1/deployments/status                 │
│     {                                                                        │
│       "organizationName": "customer-x",                                    │
│       "releaseId": "rel-uuid",                                             │
│       "status": "success",                                                 │
│       "deployedAt": now,                                                   │
│       "helmRevision": 5,                                                   │
│       "currentVersion": "2.3.0"                                            │
│     }                                                                        │
│                                                                              │
│  5. GCC updates:                                                            │
│     • organizationalServices.currentVersion = "2.3.0"                      │
│     • organizationalServices.appVer = "2.3.0"                              │
│     • DeploymentTarget.status = "success"                                  │
│     • Create VersionHistory record                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Agent Architecture

### 6.1 Project Structure

```
wrktalk-agent/
├── pyproject.toml
├── requirements.txt
├── Dockerfile.kubernetes
├── Dockerfile.compose
├── README.md
│
├── src/
│   └── wrktalk_agent/
│       ├── __init__.py
│       ├── __main__.py           # Entry point
│       ├── config.py             # Configuration loading
│       ├── agent.py              # Main agent loop
│       │
│       ├── client/
│       │   ├── __init__.py
│       │   ├── backend.py        # Backend API client
│       │   └── bucket.py         # Multi-provider bucket client
│       │
│       ├── executor/
│       │   ├── __init__.py
│       │   ├── base.py           # Base executor interface
│       │   ├── helm.py           # Helm executor
│       │   └── compose.py        # Docker Compose executor
│       │
│       └── utils/
│           ├── __init__.py
│           ├── logging.py
│           └── heartbeat.py      # Task heartbeat thread
│
└── tests/
    └── ...
```

### 6.2 Configuration

```python
# src/wrktalk_agent/config.py
from pydantic import Field
from pydantic_settings import BaseSettings
from enum import Enum


class DeploymentType(str, Enum):
    KUBERNETES = "kubernetes"
    DOCKER = "docker"


class BucketProvider(str, Enum):
    S3 = "s3"
    AZURE = "azure"
    GCS = "gcs"
    MINIO = "minio"


class AgentConfig(BaseSettings):
    """Agent configuration from environment variables."""
    
    # Backend connection
    backend_url: str = Field(default="http://localhost:3000")
    backend_timeout: int = Field(default=30)
    poll_interval: int = Field(default=30)  # seconds
    
    # Deployment type
    deployment_type: DeploymentType = Field(default=DeploymentType.KUBERNETES)
    
    # Kubernetes settings
    kube_namespace: str = Field(default="wrktalk")
    helm_release_name: str = Field(default="wrktalk")
    helm_timeout: str = Field(default="10m")
    
    # Docker Compose settings
    compose_project_name: str = Field(default="wrktalk")
    compose_working_dir: str = Field(default="/tmp/wrktalk")
    
    # Bucket settings
    bucket_provider: BucketProvider = Field(default=BucketProvider.S3)
    bucket_name: str = Field(...)
    bucket_region: str | None = Field(default=None)
    bucket_endpoint: str | None = Field(default=None)  # For MinIO
    
    # AWS credentials (if S3/MinIO)
    aws_access_key_id: str | None = Field(default=None)
    aws_secret_access_key: str | None = Field(default=None)
    
    # Azure credentials
    azure_connection_string: str | None = Field(default=None)
    
    # GCS credentials
    gcs_credentials_file: str | None = Field(default=None)
    
    # Task heartbeat
    heartbeat_interval: int = Field(default=60)  # seconds
    
    # Logging
    log_level: str = Field(default="INFO")
    
    class Config:
        env_prefix = "WRKTALK_AGENT_"
```

### 6.3 Main Agent Loop

```python
# src/wrktalk_agent/agent.py
import asyncio
import signal
from datetime import datetime
from typing import Optional
import structlog

from .config import AgentConfig, DeploymentType
from .client.backend import BackendClient
from .client.bucket import create_bucket_client
from .executor.helm import HelmExecutor
from .executor.compose import ComposeExecutor
from .utils.heartbeat import HeartbeatThread


logger = structlog.get_logger()


class Agent:
    """Stateless WrkTalk deployment agent."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.backend = BackendClient(
            base_url=config.backend_url,
            timeout=config.backend_timeout,
        )
        self.bucket = create_bucket_client(config)
        
        if config.deployment_type == DeploymentType.KUBERNETES:
            self.executor = HelmExecutor(
                namespace=config.kube_namespace,
                release_name=config.helm_release_name,
                timeout=config.helm_timeout,
            )
        else:
            self.executor = ComposeExecutor(
                project_name=config.compose_project_name,
                working_dir=config.compose_working_dir,
            )
        
        self._running = False
        self._current_task: Optional[str] = None
        self._heartbeat: Optional[HeartbeatThread] = None
    
    async def start(self):
        """Start the agent main loop."""
        logger.info(
            "agent.starting",
            deployment_type=self.config.deployment_type.value,
            backend_url=self.config.backend_url,
        )
        
        self._running = True
        
        # Signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)
        
        while self._running:
            try:
                await self._poll_and_execute()
            except Exception as e:
                logger.error("agent.poll_error", error=str(e))
            
            await asyncio.sleep(self.config.poll_interval)
        
        logger.info("agent.stopped")
    
    def _handle_shutdown(self):
        """Graceful shutdown."""
        logger.info("agent.shutdown_requested")
        if self._current_task:
            logger.warning("agent.shutdown_during_task", task_id=self._current_task)
        self._running = False
    
    async def _poll_and_execute(self):
        """Poll for tasks and execute if available."""
        task = await self.backend.get_pending_task()
        
        if not task:
            logger.debug("agent.no_tasks")
            return
        
        logger.info("agent.task_received", task_id=task["id"], task_type=task["type"])
        self._current_task = task["id"]
        
        try:
            # Mark as in progress
            await self.backend.update_task_status(
                task_id=task["id"],
                status="inProgress",
                picked_up_at=datetime.utcnow().isoformat(),
            )
            
            # Check license
            license_valid = await self.backend.check_license()
            if not license_valid:
                raise LicenseError("License expired or invalid")
            
            # Execute based on type
            if task["type"] == "deploy":
                result = await self._execute_deployment(task)
            elif task["type"] == "rollback":
                result = await self._execute_rollback(task)
            else:
                raise ValueError(f"Unknown task type: {task['type']}")
            
            # Report success
            await self.backend.update_task_status(
                task_id=task["id"],
                status="completed",
                completed_at=datetime.utcnow().isoformat(),
                result=result,
            )
            
            logger.info("agent.task_completed", task_id=task["id"])
            
        except Exception as e:
            logger.error("agent.task_failed", task_id=task["id"], error=str(e))
            await self.backend.update_task_status(
                task_id=task["id"],
                status="failed",
                completed_at=datetime.utcnow().isoformat(),
                error_message=str(e),
            )
        finally:
            self._current_task = None
            if self._heartbeat:
                self._heartbeat.stop()
                self._heartbeat = None
    
    async def _execute_deployment(self, task: dict) -> dict:
        """Execute deployment task."""
        payload = task["payload"]
        
        # 1. Insert non-essential envs (continue on failure)
        for env in payload.get("newNonEssentialEnvs", []):
            try:
                await self.backend.insert_config(env["key"], env["value"])
            except Exception as e:
                logger.warning("agent.env_insert_failed", key=env["key"], error=str(e))
        
        # 2. Download artifacts
        chart_path = await self.bucket.download(
            payload["chart"]["bucketPath"],
            local_path="/tmp/chart",
        )
        
        values_path = await self.bucket.download(
            payload["valuesBucketPath"],
            local_path="/tmp/values.yaml",
        )
        
        # 3. For Compose: download .env
        env_path = None
        if self.config.deployment_type == DeploymentType.DOCKER:
            env_path = await self.bucket.download(
                payload.get("envBucketPath", "config/.env"),
                local_path="/tmp/.env",
            )
        
        try:
            # 4. Start heartbeat
            self._heartbeat = HeartbeatThread(
                backend=self.backend,
                task_id=task["id"],
                interval=self.config.heartbeat_interval,
            )
            self._heartbeat.start()
            
            # 5. Execute deployment
            result = await self.executor.deploy(
                artifact_path=chart_path,
                values_path=values_path,
                env_path=env_path,
                image_tags=payload["imageTags"],
            )
            
            return result
            
        finally:
            # 6. Stop heartbeat
            if self._heartbeat:
                self._heartbeat.stop()
            
            # 7. Cleanup
            self._secure_delete(chart_path)
            self._secure_delete(values_path)
            if env_path:
                self._secure_delete(env_path)
    
    async def _execute_rollback(self, task: dict) -> dict:
        """Execute rollback task."""
        payload = task["payload"]
        
        self._heartbeat = HeartbeatThread(
            backend=self.backend,
            task_id=task["id"],
            interval=self.config.heartbeat_interval,
        )
        self._heartbeat.start()
        
        try:
            result = await self.executor.rollback(
                target_revision=payload.get("targetRevision"),
                target_version=payload.get("targetVersion"),
            )
            return result
        finally:
            self._heartbeat.stop()
    
    def _secure_delete(self, path: str):
        """Securely delete file."""
        import os
        import secrets
        
        try:
            if os.path.exists(path):
                size = os.path.getsize(path)
                with open(path, "wb") as f:
                    f.write(secrets.token_bytes(size))
                os.remove(path)
        except Exception as e:
            logger.warning("agent.secure_delete_failed", path=path, error=str(e))


class LicenseError(Exception):
    pass
```

### 6.4 Heartbeat Thread

```python
# src/wrktalk_agent/utils/heartbeat.py
import threading
import time
from typing import Optional
import structlog

logger = structlog.get_logger()


class HeartbeatThread:
    """Background thread to send task heartbeats during long-running operations."""
    
    def __init__(self, backend, task_id: str, interval: int = 60):
        self.backend = backend
        self.task_id = task_id
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start the heartbeat thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.debug("heartbeat.started", task_id=self.task_id)
    
    def stop(self):
        """Stop the heartbeat thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.debug("heartbeat.stopped", task_id=self.task_id)
    
    def _run(self):
        """Heartbeat loop."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self.interval)
            if not self._stop_event.is_set():
                try:
                    # Synchronous call in thread
                    import asyncio
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(
                        self.backend.send_heartbeat(self.task_id)
                    )
                    loop.close()
                    logger.debug("heartbeat.sent", task_id=self.task_id)
                except Exception as e:
                    logger.warning("heartbeat.failed", task_id=self.task_id, error=str(e))
```

### 6.5 Helm Executor

```python
# src/wrktalk_agent/executor/helm.py
import asyncio
import json
import subprocess
from dataclasses import dataclass
from typing import Optional
import structlog

from .base import BaseExecutor, DeploymentResult

logger = structlog.get_logger()


@dataclass
class HelmConfig:
    namespace: str
    release_name: str
    timeout: str = "10m"


class HelmExecutor(BaseExecutor):
    """Kubernetes Helm executor."""
    
    def __init__(self, namespace: str, release_name: str, timeout: str = "10m"):
        self.config = HelmConfig(
            namespace=namespace,
            release_name=release_name,
            timeout=timeout,
        )
    
    async def deploy(
        self,
        artifact_path: str,
        values_path: str,
        env_path: Optional[str],  # Not used for K8s
        image_tags: dict[str, str],
    ) -> DeploymentResult:
        """Execute Helm upgrade with atomic rollback."""
        
        logger.info("helm.upgrade.starting", release=self.config.release_name)
        
        cmd = [
            "helm", "upgrade", self.config.release_name, artifact_path,
            "--namespace", self.config.namespace,
            "--values", values_path,
            "--timeout", self.config.timeout,
            "--atomic",  # Auto-rollback on failure
            "--wait",    # Wait for pods ready
            "--output", "json",
        ]
        
        # Add image tag overrides
        for service, tag in image_tags.items():
            cmd.extend(["--set", f"{service}.image.tag={tag}"])
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=660,  # 11 minutes
            )
            
            if result.returncode != 0:
                logger.error("helm.upgrade.failed", stderr=result.stderr)
                raise HelmError(f"Helm upgrade failed: {result.stderr}")
            
            output = json.loads(result.stdout) if result.stdout else {}
            revision = output.get("revision", self._get_current_revision())
            
            logger.info("helm.upgrade.success", revision=revision)
            
            return DeploymentResult(
                status="success",
                revision=revision,
                message="Helm upgrade completed successfully",
            )
            
        except subprocess.TimeoutExpired:
            logger.error("helm.upgrade.timeout")
            raise HelmError("Helm upgrade timed out")
    
    async def rollback(
        self,
        target_revision: Optional[int] = None,
        target_version: Optional[str] = None,
    ) -> DeploymentResult:
        """Execute Helm rollback."""
        
        logger.info("helm.rollback.starting", target_revision=target_revision)
        
        cmd = [
            "helm", "rollback", self.config.release_name,
            "--namespace", self.config.namespace,
            "--timeout", self.config.timeout,
            "--wait",
        ]
        
        if target_revision:
            cmd.append(str(target_revision))
        
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            raise HelmError(f"Helm rollback failed: {result.stderr}")
        
        current_revision = self._get_current_revision()
        
        logger.info("helm.rollback.success", revision=current_revision)
        
        return DeploymentResult(
            status="success",
            revision=current_revision,
            message="Helm rollback completed",
        )
    
    def _get_current_revision(self) -> int:
        """Get current Helm revision."""
        result = subprocess.run(
            ["helm", "list", "-n", self.config.namespace,
             "-f", self.config.release_name, "-o", "json"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout:
            releases = json.loads(result.stdout)
            if releases:
                return int(releases[0].get("revision", 0))
        return 0


class HelmError(Exception):
    pass
```

### 6.6 Docker Compose Executor

```python
# src/wrktalk_agent/executor/compose.py
import asyncio
import os
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from typing import Optional
import structlog

from .base import BaseExecutor, DeploymentResult

logger = structlog.get_logger()


@dataclass
class ComposeConfig:
    project_name: str
    working_dir: str


class ComposeExecutor(BaseExecutor):
    """Docker Compose executor."""
    
    def __init__(self, project_name: str, working_dir: str):
        self.config = ComposeConfig(
            project_name=project_name,
            working_dir=working_dir,
        )
    
    async def deploy(
        self,
        artifact_path: str,
        values_path: str,  # Not used for Compose
        env_path: Optional[str],
        image_tags: dict[str, str],
    ) -> DeploymentResult:
        """Execute Docker Compose deployment."""
        
        logger.info("compose.deploy.starting", project=self.config.project_name)
        
        # 1. Extract bundle
        os.makedirs(self.config.working_dir, exist_ok=True)
        
        await asyncio.to_thread(
            self._extract_bundle, artifact_path, self.config.working_dir
        )
        
        # 2. Copy .env file
        if env_path:
            dest_env = os.path.join(self.config.working_dir, ".env")
            shutil.copy(env_path, dest_env)
        
        # 3. Set image tag environment variables
        for service, tag in image_tags.items():
            env_key = f"{service.upper()}_IMAGE_TAG"
            os.environ[env_key] = tag
        
        compose_file = os.path.join(self.config.working_dir, "docker-compose.yaml")
        
        try:
            # 4. Pull images
            logger.info("compose.pulling")
            await asyncio.to_thread(
                subprocess.run,
                ["docker-compose", "-f", compose_file, "pull"],
                check=True,
                capture_output=True,
            )
            
            # 5. Deploy
            logger.info("compose.up")
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker-compose", "-f", compose_file, "up", "-d", "--remove-orphans"],
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                raise ComposeError(f"Docker Compose failed: {result.stderr}")
            
            logger.info("compose.deploy.success")
            
            return DeploymentResult(
                status="success",
                message="Docker Compose deployment completed",
            )
            
        except subprocess.CalledProcessError as e:
            raise ComposeError(f"Docker Compose failed: {e.stderr}")
    
    async def rollback(
        self,
        target_revision: Optional[int] = None,  # Not used for Compose
        target_version: Optional[str] = None,
    ) -> DeploymentResult:
        """
        Rollback Docker Compose.
        
        For Compose, rollback = re-deploy previous version.
        This requires the previous bundle and .env to be available in bucket.
        Backend must provide the correct artifact/env paths.
        """
        logger.info("compose.rollback.starting", target_version=target_version)
        
        # Rollback for Compose is essentially a deploy of an older version
        # The Backend should provide the old artifact paths in the task payload
        raise NotImplementedError(
            "Compose rollback requires Backend to provide previous version paths"
        )
    
    def _extract_bundle(self, artifact_path: str, dest_dir: str):
        """Extract compose bundle tarball."""
        with tarfile.open(artifact_path, "r:gz") as tar:
            tar.extractall(dest_dir)


class ComposeError(Exception):
    pass
```

### 6.7 Dockerfiles

```dockerfile
# Dockerfile.kubernetes
FROM python:3.11-slim

# Install Helm
RUN apt-get update && apt-get install -y curl && \
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN useradd -m -u 1000 agent && chown -R agent:agent /app
USER agent

ENV WRKTALK_AGENT_DEPLOYMENT_TYPE=kubernetes

CMD ["python", "-m", "wrktalk_agent"]
```

```dockerfile
# Dockerfile.compose
FROM python:3.11-slim

# Install Docker CLI and docker-compose
RUN apt-get update && apt-get install -y \
    curl docker.io docker-compose \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV WRKTALK_AGENT_DEPLOYMENT_TYPE=docker

# Note: Runs as root for docker socket access
# Use docker socket proxy in production for security

CMD ["python", "-m", "wrktalk_agent"]
```

---

## 7. Communication Model

### 7.1 Push + Poll + Heartbeat

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMMUNICATION MODEL                                  │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════   │
│  1. WEBHOOK (Push - Primary)                                                │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  GCC ──── POST /api/deployment/webhook ────► Customer Backend               │
│                                                                              │
│  Success: ◄── 200 OK + ACK                                                  │
│  Failure: Retry 2x @ 60 second intervals                                   │
│  After 3 failures: Mark webhookFailed, wait for poll                       │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════   │
│  2. POLLING (Fallback - every 5 min)                                        │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Customer Backend ── GET /api/v1/organizations/{name}/updates ──► GCC       │
│                                                                              │
│  Purpose:                                                                   │
│  • Catch missed webhooks                                                    │
│  • Air-gapped fallback                                                      │
│  • Check for new releases                                                   │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════   │
│  3. HEARTBEAT (every 5 min with poll)                                       │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Customer Backend ── POST /api/v1/organizations/{name}/heartbeat ──► GCC   │
│                                                                              │
│  Payload:                                                                   │
│  {                                                                           │
│    "version": "2.3.0",                                                      │
│    "status": "healthy",                                                     │
│    "agentLastPoll": "2024-12-15T10:00:00Z",                                │
│    "timestamp": "2024-12-15T10:05:00Z"                                     │
│  }                                                                           │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════   │
│  4. AGENT TASK HEARTBEAT (during deployment)                                │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Agent ── POST /internal/agent/tasks/{id}/heartbeat ──► Backend            │
│                                                                              │
│  Purpose:                                                                   │
│  • Keep task alive during long migrations                                  │
│  • Prevent timeout for operations > 30 min                                 │
│  • Interval: every 60 seconds                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Error Cases & Recovery Procedures

### 8.1 Phase 1: CI → GCC

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 1: CI → GCC ERRORS                                  │
│                                                                              │
│  ERROR 1.1: Jenkins cannot reach GCC                                        │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Network issue, GCC down                                             │
│  Detection: HTTP timeout or connection refused                              │
│  Impact: Release not created                                                │
│  Recovery:                                                                   │
│    • Jenkins job fails → alerts DevOps                                     │
│    • Manual retry after GCC restored                                       │
│    • Idempotent: same version = safe to retry                              │
│                                                                              │
│  ERROR 1.2: Chart upload succeeds, release creation fails                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: GCC DB error, validation failure                                    │
│  Detection: Upload 200, release 500                                        │
│  Impact: Orphan chart in bucket                                             │
│  Recovery:                                                                   │
│    • GCC cleanup job deletes orphan charts                                 │
│    • Manual retry                                                           │
│                                                                              │
│  ERROR 1.3: Duplicate version upload                                        │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Detection: Version already exists                                          │
│  Handling:                                                                   │
│    • If release is draft: Allow overwrite                                  │
│    • If release is published: Reject 409 Conflict                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Phase 2: GCC → Customer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 2: GCC → CUSTOMER ERRORS                            │
│                                                                              │
│  ERROR 2.1: Customer Backend unreachable                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Customer infra down, network blocked                               │
│  Detection: Connection timeout/refused                                      │
│  Recovery:                                                                   │
│    • Retry 2x @ 60 seconds                                                  │
│    • After 3 failures: Mark webhookFailed                                  │
│    • Customer poll picks up release                                        │
│    • Alert GCC admin if offline > 24 hours                                 │
│                                                                              │
│  ERROR 2.2: Customer returns 401 Unauthorized                               │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Webhook secret mismatch                                             │
│  Recovery:                                                                   │
│    • DO NOT retry (won't help)                                             │
│    • Alert GCC admin: "Auth issue with customer X"                         │
│    • Manual investigation required                                          │
│                                                                              │
│  ERROR 2.3: Customer returns 5xx                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Backend error                                                       │
│  Recovery:                                                                   │
│    • Retry 2x @ 60 seconds                                                  │
│    • Log response body for debugging                                       │
│    • Fall back to poll                                                      │
│                                                                              │
│  ERROR 2.4: Webhook timeout                                                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Slow processing                                                     │
│  Recovery:                                                                   │
│    • Customer Backend should ACK quickly, process async                    │
│    • Retry (idempotent)                                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Phase 3: Customer Backend Processing

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 3: CUSTOMER BACKEND PROCESSING ERRORS               │
│                                                                              │
│  ERROR 3.1: Cannot download chart from GCC                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: GCC down, network issue                                             │
│  Recovery:                                                                   │
│    • Retry 3x with exponential backoff                                     │
│    • Mark release as: downloadFailed                                        │
│    • Background job retries periodically                                   │
│    • Alert admin: "Cannot download chart"                                  │
│    • DO NOT allow scheduling until downloaded                              │
│                                                                              │
│  ERROR 3.2: SHA256 checksum mismatch                                        │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Corrupted download                                                  │
│  Recovery:                                                                   │
│    • REJECT chart                                                           │
│    • Retry download 3x                                                      │
│    • After failures: Alert admin + GCC                                     │
│    • NEVER deploy unverified chart                                         │
│                                                                              │
│  ERROR 3.3: Customer bucket upload fails                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Credentials expired, bucket full                                   │
│  Recovery:                                                                   │
│    • Retry 3x                                                               │
│    • Alert admin: "Check bucket credentials"                               │
│    • Keep chart in temp until bucket works                                 │
│                                                                              │
│  ERROR 3.4: Cleanup fails                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Impact: Bucket grows beyond 10 versions                                    │
│  Recovery:                                                                   │
│    • Log warning, continue (non-blocking)                                  │
│    • Retry in background job                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.4 Phase 4: Agent Execution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 4: AGENT EXECUTION ERRORS                           │
│                                                                              │
│  ERROR 4.1: Agent cannot poll Backend                                       │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Backend down, network partition                                    │
│  Recovery:                                                                   │
│    • Retry with exponential backoff                                        │
│    • Agent continues running                                                │
│    • Backend tracks: lastAgentPoll                                         │
│    • If no poll in 10 min: Alert admin "Agent may be down"                │
│                                                                              │
│  ERROR 4.2: Agent cannot download from bucket                               │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Credentials wrong, chart deleted                                   │
│  Recovery:                                                                   │
│    • Fail task with error                                                   │
│    • Retry up to maxAttempts (3)                                           │
│    • After max: Mark failed, notify admin                                  │
│                                                                              │
│  ERROR 4.3: License expired                                                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Detection: Agent checks license before executing                          │
│  Recovery:                                                                   │
│    • BLOCK deployment                                                       │
│    • Fail task: "License expired"                                          │
│    • Notify admin                                                           │
│                                                                              │
│  ERROR 4.4: Non-essential env insert fails                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Backend API error                                                   │
│  Recovery:                                                                   │
│    • Log warning                                                            │
│    • CONTINUE deployment (non-blocking)                                    │
│    • Envs can be added manually later                                      │
│                                                                              │
│  ERROR 4.5: Helm upgrade fails (Kubernetes)                                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Invalid chart, resource issues, image pull fails                   │
│  Recovery:                                                                   │
│    • --atomic: Helm auto-rollbacks                                         │
│    • Report failure with stderr                                             │
│    • Notify admins                                                          │
│    • Admin can: retry, investigate, rollback                               │
│                                                                              │
│  ERROR 4.6: Docker Compose fails                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: Invalid compose, image pull fails, port conflict                   │
│  Impact: PARTIAL STATE possible (no atomic)                                │
│  Recovery:                                                                   │
│    • Report failure                                                         │
│    • Notify: "CRITICAL: Compose failed - manual intervention"             │
│    • Admin must check state and rollback manually                          │
│                                                                              │
│  ERROR 4.7: Agent crashes mid-deployment                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Detection: Task stuck inProgress, no heartbeat                            │
│                                                                              │
│  Kubernetes:                                                                │
│    • Helm --atomic: incomplete = rolled back                               │
│    • Backend timeout (30 min base, extended by heartbeats)                │
│    • After timeout: Mark failed                                             │
│                                                                              │
│  Docker Compose:                                                            │
│    • Partial deployment may exist                                           │
│    • Backend timeout: Mark failed, alert admin                             │
│    • Manual intervention required                                           │
│                                                                              │
│  ERROR 4.8: Image pull fails                                                │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Cause: GHCR auth fails, image doesn't exist                               │
│  Recovery:                                                                   │
│    • Check imagePullSecrets (K8s) or docker login (Compose)               │
│    • Check image exists in GHCR                                            │
│    • Usually configuration issue, not retry-able                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.5 Task Timeout Logic

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TASK TIMEOUT LOGIC                                        │
│                                                                              │
│  Base timeout: 30 minutes                                                   │
│  Extended by heartbeats: Each heartbeat resets timeout window              │
│                                                                              │
│  Backend timeout check (runs every minute):                                │
│                                                                              │
│  for each task where status = "inProgress":                                │
│    lastActivity = MAX(pickedUpAt, lastHeartbeat)                          │
│    if (now - lastActivity > 30 minutes):                                   │
│      task.status = "failed"                                                │
│      task.errorMessage = "Task timeout - no heartbeat received"           │
│      notify admin: "Deployment timed out - check Agent status"            │
│                                                                              │
│  Long-running migrations:                                                   │
│  • Agent sends heartbeat every 60 seconds                                  │
│  • Each heartbeat extends the timeout window                               │
│  • Migrations taking 1+ hours are supported                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Rollback Procedures

### 9.1 Kubernetes Rollback

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KUBERNETES ROLLBACK                                       │
│                                                                              │
│  AUTOMATIC (Helm --atomic)                                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Trigger: helm upgrade fails                                                │
│  Action: Helm automatically rolls back to previous revision                │
│  Restores:                                                                  │
│    ✅ Previous image tags                                                   │
│    ✅ Previous ConfigMaps (essential envs)                                 │
│    ✅ Previous chart templates                                              │
│  Does NOT restore:                                                          │
│    ❌ Non-essential envs (in DB)                                           │
│                                                                              │
│  MANUAL (Admin-initiated)                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│  Option A: Use Helm history                                                 │
│  Admin: POST /api/admin/deployment/rollback                                │
│  { "targetRevision": 5 }                                                    │
│                                                                              │
│  Agent executes:                                                            │
│    helm rollback wrktalk 5 --namespace wrktalk --wait                      │
│                                                                              │
│  Fast, no download needed.                                                  │
│                                                                              │
│  Option B: Re-deploy from bucket                                            │
│  Admin: POST /api/admin/deployment/rollback                                │
│  { "targetVersion": "2.2.0" }                                               │
│                                                                              │
│  Agent:                                                                     │
│    1. Download wrktalk-2.2.0.tgz from bucket                              │
│    2. helm upgrade with old chart + current values                        │
│                                                                              │
│  More flexible, can use different values.                                  │
│                                                                              │
│  FALLBACK: Chart not in customer bucket                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  If chart deleted from customer bucket (only 10 kept):                     │
│    1. Try download from GCC (keeps 20)                                     │
│    2. If not in GCC: "Version not available"                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Docker Compose Rollback

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DOCKER COMPOSE ROLLBACK                                   │
│                                                                              │
│  NO automatic rollback (Compose limitation)                                │
│                                                                              │
│  MANUAL ROLLBACK                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│  Admin: POST /api/admin/deployment/rollback                                │
│  { "targetVersion": "2.2.0" }                                               │
│                                                                              │
│  Backend creates rollback task:                                             │
│  {                                                                           │
│    type: "deploy",  // Rollback = deploy old version                       │
│    payload: {                                                               │
│      chart: {                                                               │
│        bucketPath: "artifacts/compose/wrktalk-2.2.0-compose.tar.gz"       │
│      },                                                                     │
│      envBucketPath: "config/.env.v2.2.0",  // Versioned env file          │
│      imageTags: { /* old image tags from DB */ }                          │
│    }                                                                        │
│  }                                                                           │
│                                                                              │
│  Agent:                                                                     │
│    1. Download old compose bundle                                          │
│    2. Download old .env file (.env.v2.2.0)                                │
│    3. docker-compose up -d                                                 │
│                                                                              │
│  REQUIREMENT: .env files must be versioned in bucket                       │
│  ─────────────────────────────────────────────────────────────────────────  │
│  config/                                                                    │
│  ├── .env           ← Current (symlink or copy)                            │
│  ├── .env.v2.3.0    ← Saved when 2.3.0 deployed                           │
│  ├── .env.v2.2.0    ← Rollback target                                     │
│  └── .env.v2.1.0                                                           │
│                                                                              │
│  On each deployment:                                                        │
│    1. Before deploying 2.3.0, save current .env as .env.v{current}        │
│    2. Deploy with new .env                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Scheduling & Deadlines

### 10.1 Normal Updates

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NORMAL UPDATE FLOW                                        │
│                                                                              │
│  1. Release received → status: pending                                      │
│  2. Admin notified                                                          │
│  3. Admin schedules for specific time                                       │
│  4. At scheduled time → Agent executes                                      │
│  5. No deadline, no pressure                                                │
│                                                                              │
│  MISSED SCHEDULE (system was down)                                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Detection: scheduledFor < now AND status = "scheduled"                    │
│  Action: REQUIRE RE-SCHEDULE                                                │
│    • Do NOT auto-execute                                                    │
│    • Notify admin: "Scheduled deployment missed, please reschedule"       │
│    • Update status: "missedSchedule"                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Forced Updates

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FORCED UPDATE FLOW                                        │
│                                                                              │
│  Timeline:                                                                  │
│                                                                              │
│  T+0h: Release received (isForced: true)                                   │
│    • forceDeadline = now + 24 hours                                        │
│    • Notify admins: "FORCED UPDATE - 24h deadline"                         │
│    • status: pending                                                        │
│                                                                              │
│  T+12h: First reminder                                                      │
│    • If not scheduled: Send reminder                                       │
│    • "12 hours remaining to deploy v2.3.0"                                 │
│                                                                              │
│  T+20h: Second reminder                                                     │
│    • If not scheduled: Send urgent reminder                                │
│    • "⚠️ 4 hours remaining to deploy v2.3.0"                              │
│                                                                              │
│  T+24h: Deadline exceeded                                                   │
│    • If not deployed:                                                       │
│      - status: "deadlineExceeded"                                          │
│      - DO NOT auto-deploy                                                   │
│      - Create escalation: FORCED_24H_EXCEEDED                              │
│      - Alert admin: "CRITICAL: Forced update deadline exceeded"           │
│      - Report to GCC (escalation created)                                  │
│                                                                              │
│  After deadline:                                                            │
│    • Admin can still schedule manually                                     │
│    • Escalation remains until deployed                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.3 Concurrent Deployment Prevention

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONCURRENT DEPLOYMENT PREVENTION                          │
│                                                                              │
│  Rule: Only ONE deployment can be active at a time                          │
│                                                                              │
│  When admin tries to schedule:                                              │
│    if (exists task where status IN ("scheduled", "inProgress")):           │
│      return 409 Conflict "Deployment already in progress"                  │
│                                                                              │
│  When admin tries to rollback:                                              │
│    if (exists task where status IN ("scheduled", "inProgress")):           │
│      return 409 Conflict "Cannot rollback - deployment in progress"       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Health Monitoring

### 11.1 Customer Status Tracking

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CUSTOMER STATUS TRACKING                                  │
│                                                                              │
│  GCC tracks per customer:                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • lastHeartbeat: When customer last sent heartbeat                        │
│  • lastWebhookAck: When customer last acknowledged webhook                 │
│  • lastSeen: MAX(lastHeartbeat, lastWebhookAck)                            │
│  • currentVersion: Version reported in heartbeat                           │
│  • isOnline: Computed from lastSeen                                        │
│  • agentLastPoll: Reported in heartbeat (Backend tracks this)             │
│                                                                              │
│  Status Thresholds:                                                         │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • ONLINE:    lastSeen < 10 minutes                                        │
│  • DEGRADED:  lastSeen < 1 hour                                            │
│  • OFFLINE:   lastSeen < 24 hours                                          │
│  • CRITICAL:  lastSeen > 24 hours → Escalate if pending forced            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.2 Agent Status Tracking

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AGENT STATUS TRACKING                                     │
│                                                                              │
│  Backend tracks:                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • lastAgentPoll: When Agent last called GET /internal/agent/tasks        │
│  • agentOnline: lastAgentPoll < 10 minutes                                 │
│                                                                              │
│  Alert if:                                                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • No poll in 10 minutes → Alert admin "Agent may be down"                │
│  • Check: Is Agent pod running? (K8s)                                      │
│  • Check: Is Agent container running? (Compose)                            │
│                                                                              │
│  Task heartbeat during deployment:                                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • Agent sends POST /internal/agent/tasks/{id}/heartbeat every 60s        │
│  • Backend updates task.lastHeartbeat                                      │
│  • If no heartbeat for 30 min: Task times out                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. GCC Schema Extensions

```prisma
// ============================================================================
// GCC SCHEMA EXTENSIONS
// ============================================================================

// Existing model - add new fields
model organizationalServices {
  id                String   @id() @default(uuid())
  name              String   @unique()
  servicePath       String
  appVer            String   @map("app_version")
  createdAt         DateTime @default(now())
  updatedAt         DateTime @updatedAt
  
  // Existing fields...
  
  // ═══════════════════════════════════════════════════════════════════════
  // NEW FIELDS
  // ═══════════════════════════════════════════════════════════════════════
  
  deploymentType    DeploymentType @default(kubernetes)
  
  // Webhook
  webhookEndpoint   String?
  webhookSecret     String?
  
  // Health monitoring
  isOnline          Boolean  @default(false)
  lastSeen          DateTime?
  lastHeartbeat     DateTime?
  lastWebhookAck    DateTime?
  currentVersion    String?
  agentLastPoll     DateTime?
  
  // Contacts
  spocName          String?
  spocEmail         String?
  spocPhone         String?
  accountManagerId  String?
  
  // Relations
  deploymentTargets DeploymentTarget[]
  versionHistory    VersionHistory[]
  escalations       Escalation[]
  
  @@map("organizational_service")
}

enum DeploymentType {
  kubernetes
  docker
}

enum ReleaseStatus {
  draft
  published
  deprecated
}

enum DeploymentStatus {
  pending
  notified
  webhookFailed
  downloadFailed
  scheduled
  inProgress
  success
  failed
  rolledBack
  deadlineExceeded
  cancelled
}

enum EscalationType {
  FORCED_24H_EXCEEDED
  MIN_VERSION_BLOCKED
  LICENSE_EXPIRED
  DEPLOYMENT_FAILED
  CLIENT_OFFLINE
}

model Release {
  id                    String        @id @default(uuid())
  version               String        @unique
  releaseNotes          String?       @db.Text
  status                ReleaseStatus @default(draft)
  
  // Image tags
  backendImageTag       String
  mediaImageTag         String
  controlTowerImageTag  String
  agentImageTag         String
  
  // Artifacts
  helmChartSha256       String
  composeArtifactSha256 String?
  
  // Ruleset
  isForced              Boolean       @default(false)
  isMigrationRequired   Boolean       @default(false)
  estimatedDowntime     String?
  minCurrentVersion     String?
  
  // Non-essential envs to add
  newNonEssentialEnvs   Json?
  
  createdAt             DateTime      @default(now())
  createdBy             String
  publishedAt           DateTime?
  
  deploymentTargets     DeploymentTarget[]
  
  @@map("gcc_release")
}

model DeploymentTarget {
  id                String           @id @default(uuid())
  
  releaseId         String
  release           Release          @relation(fields: [releaseId], references: [id])
  
  organizationName  String
  organization      organizationalServices @relation(fields: [organizationName], references: [name])
  
  // Webhook tracking
  webhookSent       Boolean          @default(false)
  webhookAcked      Boolean          @default(false)
  webhookRetries    Int              @default(0)
  webhookError      String?
  
  // Scheduling (from customer)
  scheduledFor      DateTime?
  
  // Execution
  status            DeploymentStatus @default(pending)
  startedAt         DateTime?
  completedAt       DateTime?
  helmRevision      Int?
  errorMessage      String?          @db.Text
  
  createdAt         DateTime         @default(now())
  updatedAt         DateTime         @updatedAt
  
  @@unique([releaseId, organizationName])
  @@map("gcc_deployment_target")
}

model VersionHistory {
  id                String   @id @default(uuid())
  organizationName  String
  organization      organizationalServices @relation(fields: [organizationName], references: [name])
  releaseVersion    String
  deployedAt        DateTime
  status            String
  helmRevision      Int?
  
  @@map("gcc_version_history")
}

model Escalation {
  id                String         @id @default(uuid())
  organizationName  String
  organization      organizationalServices @relation(fields: [organizationName], references: [name])
  type              EscalationType
  reason            String         @db.Text
  metadata          Json?
  escalatedAt       DateTime       @default(now())
  resolvedAt        DateTime?
  resolution        String?
  
  @@map("gcc_escalation")
}

model GccArtifact {
  id                String   @id @default(uuid())
  version           String
  type              String   // "helm" or "compose"
  bucketPath        String
  sha256            String
  sizeBytes         Int
  createdAt         DateTime @default(now())
  
  @@unique([version, type])
  @@map("gcc_artifact")
}
```

---

## 13. Customer Backend Schema Extensions

```prisma
// ============================================================================
// CUSTOMER BACKEND SCHEMA EXTENSIONS
// Add to existing schema.prisma
// ============================================================================

enum LocalDeploymentStatus {
  pending
  downloadFailed
  scheduled
  missedSchedule
  inProgress
  success
  failed
  rolledBack
  deadlineExceeded
  cancelled
}

enum AgentTaskType {
  deploy
  rollback
}

enum AgentTaskStatus {
  pending
  inProgress
  completed
  failed
}

// Deployment configuration (singleton)
model deploymentConfig {
  id                Int      @id @default(1)
  
  // GCC connection
  gccEndpoint       String
  gccApiKey         String
  webhookSecret     String
  
  // Bucket
  bucketProvider    String   // s3 | azure | gcs | minio
  bucketName        String
  bucketRegion      String?
  bucketEndpoint    String?
  
  // Polling
  pollIntervalSec   Int      @default(300)
  heartbeatEnabled  Boolean  @default(true)
  
  // Current state
  currentVersion    String?
  lastGccPoll       DateTime?
  lastHeartbeat     DateTime?
  lastAgentPoll     DateTime?
  
  createdAt         DateTime @default(now())
  updatedAt         DateTime @updatedAt
  
  @@map("deployment_config")
}

// Scheduled deployments
model scheduledDeployment {
  id                String                @id @default(uuid())
  
  // Release info
  gccReleaseId      String
  releaseName       String
  releaseData       Json                  // Full release payload
  
  // Ruleset
  isForced          Boolean               @default(false)
  forceDeadline     DateTime?
  remindersSent     Int                   @default(0)
  
  // Scheduling
  scheduledFor      DateTime?
  scheduledBy       String?
  
  // Artifact tracking
  chartBucketPath   String?
  chartDownloaded   Boolean               @default(false)
  
  // Execution
  status            LocalDeploymentStatus @default(pending)
  startedAt         DateTime?
  completedAt       DateTime?
  helmRevision      Int?
  errorMessage      String?               @db.Text
  
  // GCC sync
  reportedToGcc     Boolean               @default(false)
  
  // Relations
  agentTasks        agentTask[]
  
  createdAt         DateTime              @default(now())
  updatedAt         DateTime              @updatedAt
  
  @@index([status, scheduledFor])
  @@map("scheduled_deployment")
}

// Agent task queue
model agentTask {
  id                String          @id @default(uuid())
  
  type              AgentTaskType
  status            AgentTaskStatus @default(pending)
  
  // Reference
  deploymentId      String?
  deployment        scheduledDeployment? @relation(fields: [deploymentId], references: [id])
  
  // Task payload
  payload           Json
  
  // Scheduling
  executeAfter      DateTime        @default(now())
  
  // Execution tracking
  pickedUpAt        DateTime?
  lastHeartbeat     DateTime?
  completedAt       DateTime?
  
  // Results
  result            Json?
  errorMessage      String?         @db.Text
  
  // Retry
  attempts          Int             @default(0)
  maxAttempts       Int             @default(3)
  
  createdAt         DateTime        @default(now())
  updatedAt         DateTime        @updatedAt
  
  @@index([status, executeAfter])
  @@map("agent_task")
}

// Non-essential environment variables
model nonEssentialEnv {
  id                String   @id @default(uuid())
  key               String   @unique
  value             String
  description       String?
  category          String?  // feature | logging | ui
  
  createdAt         DateTime @default(now())
  updatedAt         DateTime @updatedAt
  updatedBy         String?
  
  @@map("non_essential_env")
}

// Deployment history
model deploymentHistory {
  id                String   @id @default(uuid())
  gccReleaseId      String
  releaseName       String
  version           String
  deployedAt        DateTime
  status            String
  helmRevision      Int?
  isRollback        Boolean  @default(false)
  isCurrent         Boolean  @default(false)
  
  @@map("deployment_history")
}

// Compose env versions (for rollback)
model composeEnvVersion {
  id                String   @id @default(uuid())
  version           String   @unique
  bucketPath        String
  isCurrent         Boolean  @default(false)
  createdAt         DateTime @default(now())
  
  @@map("compose_env_version")
}
```

---

## 14. API Specifications

### 14.1 GCC Internal APIs (CI → GCC)

```
POST /api/internal/artifacts
Authorization: Bearer {CI_TOKEN}
Content-Type: multipart/form-data

Form fields:
  - file: Binary (chart.tgz or compose.tar.gz)
  - type: "helm" | "compose"
  - version: "2.3.0"

Response 200:
{
  "id": "artifact-uuid",
  "bucketPath": "charts/helm/wrktalk-2.3.0.tgz",
  "sha256": "abc123...",
  "sizeBytes": 102400
}
```

```
POST /api/internal/releases
Authorization: Bearer {CI_TOKEN}
Content-Type: application/json

{
  "version": "2.3.0",
  "imageTags": {
    "backend": "sha-abc123",
    "media": "sha-def456",
    "controlTower": "sha-ghi789",
    "agent": "sha-jkl012"
  },
  "isForced": false,
  "isMigrationRequired": false,
  "estimatedDowntime": null,
  "releaseNotes": "Bug fixes",
  "newNonEssentialEnvs": [
    { "key": "NEW_FEATURE", "value": "false" }
  ]
}

Response 200:
{
  "id": "release-uuid",
  "version": "2.3.0",
  "status": "draft"
}
```

### 14.2 GCC External APIs (Customer → GCC)

```
GET /api/artifacts/charts/{version}
Authorization: Bearer {CUSTOMER_API_KEY}
Query: type=helm (or compose)

Response: Binary stream (chart.tgz)
Headers:
  X-Sha256: abc123...
```

```
POST /api/v1/organizations/{orgName}/heartbeat
Authorization: Bearer {CUSTOMER_API_KEY}
Content-Type: application/json

{
  "version": "2.3.0",
  "status": "healthy",
  "agentLastPoll": "2024-12-15T10:00:00Z",
  "timestamp": "2024-12-15T10:05:00Z"
}

Response 200:
{ "received": true }
```

### 14.3 Customer Backend Internal APIs (Agent → Backend)

```
GET /internal/agent/tasks
X-Agent-Secret: {AGENT_SECRET}

Response (no task):
{ "task": null }

Response (task available):
{
  "task": {
    "id": "task-uuid",
    "type": "deploy",
    "payload": {
      "chart": {
        "bucketPath": "artifacts/helm/wrktalk-2.3.0.tgz",
        "version": "2.3.0"
      },
      "imageTags": {
        "backend": "sha-abc123",
        "media": "sha-def456"
      },
      "valuesBucketPath": "config/values.yaml",
      "envBucketPath": "config/.env",  // Compose only
      "newNonEssentialEnvs": [
        { "key": "NEW_FEATURE", "value": "false" }
      ]
    },
    "executeAfter": "2024-12-15T02:00:00Z"
  }
}
```

```
POST /internal/agent/tasks/{taskId}/status
X-Agent-Secret: {AGENT_SECRET}
Content-Type: application/json

{
  "status": "inProgress" | "completed" | "failed",
  "pickedUpAt": "...",
  "completedAt": "...",
  "result": { "helmRevision": 5, "status": "success" },
  "errorMessage": "..."
}
```

```
POST /internal/agent/tasks/{taskId}/heartbeat
X-Agent-Secret: {AGENT_SECRET}

Response 200:
{ "received": true }
```

```
POST /internal/config
X-Agent-Secret: {AGENT_SECRET}
Content-Type: application/json

{
  "key": "NEW_FEATURE",
  "value": "false"
}

Response 200:
{ "created": true }
```

```
GET /internal/license/status
X-Agent-Secret: {AGENT_SECRET}

Response 200:
{
  "valid": true,
  "expiresAt": "2025-12-31T23:59:59Z"
}
```

### 14.4 Control Tower APIs

```
GET /api/admin/deployment/releases
Authorization: Bearer {ADMIN_TOKEN}

Response:
{
  "pending": [...],
  "scheduled": [...],
  "history": [...]
}
```

```
POST /api/admin/deployment/schedule
Authorization: Bearer {ADMIN_TOKEN}
Content-Type: application/json

{
  "deploymentId": "sd-uuid",
  "scheduledFor": "2024-12-15T02:00:00Z"
}

Response 200:
{ "scheduled": true, "taskId": "task-uuid" }

Response 409:
{ "error": "Deployment already in progress" }
```

```
POST /api/admin/deployment/rollback
Authorization: Bearer {ADMIN_TOKEN}
Content-Type: application/json

// Option A: By Helm revision
{ "targetRevision": 5 }

// Option B: By version
{ "targetVersion": "2.2.0" }

Response 200:
{ "rollbackInitiated": true, "taskId": "task-uuid" }
```

---

## 15. Python Agent Implementation

See Section 6 for complete Agent implementation including:
- Project structure
- Configuration
- Main agent loop
- Heartbeat thread
- Helm executor
- Compose executor
- Dockerfiles

---

## 16. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-3)

| Task | Component | Priority |
|------|-----------|----------|
| GCC schema extensions | GCC | HIGH |
| S3 bucket setup for GCC | GCC | HIGH |
| CI artifact upload endpoints | GCC | HIGH |
| Release management CRUD | GCC | HIGH |
| Customer Backend schema extensions | Backend | HIGH |

### Phase 2: Communication (Weeks 4-5)

| Task | Component | Priority |
|------|-----------|----------|
| Webhook dispatcher with retry | GCC | HIGH |
| Webhook receiver + signature validation | Backend | HIGH |
| Chart download from GCC | Backend | HIGH |
| Customer bucket upload | Backend | HIGH |
| Polling endpoint | GCC | MEDIUM |
| Heartbeat endpoint | GCC | MEDIUM |

### Phase 3: Agent Core (Weeks 6-8)

| Task | Component | Priority |
|------|-----------|----------|
| Agent project setup | Agent | HIGH |
| Backend API client | Agent | HIGH |
| Bucket client (multi-provider) | Agent | HIGH |
| Task polling loop | Agent | HIGH |
| Heartbeat thread | Agent | HIGH |
| Helm executor | Agent | HIGH |
| Compose executor | Agent | HIGH |

### Phase 4: Scheduling & Execution (Weeks 9-10)

| Task | Component | Priority |
|------|-----------|----------|
| Control Tower scheduling APIs | Backend | HIGH |
| Agent task queue management | Backend | HIGH |
| License validation | Backend | HIGH |
| Non-essential env insertion | Agent | MEDIUM |
| Task timeout handling | Backend | HIGH |

### Phase 5: Rollback & Error Handling (Weeks 11-12)

| Task | Component | Priority |
|------|-----------|----------|
| Helm rollback | Agent | HIGH |
| Compose rollback (.env versioning) | Agent | HIGH |
| Error recovery procedures | All | HIGH |
| Escalation system | GCC | MEDIUM |
| Admin notifications | Backend | MEDIUM |

### Phase 6: Monitoring & Polish (Weeks 13-14)

| Task | Component | Priority |
|------|-----------|----------|
| Health monitoring service | GCC | MEDIUM |
| GCC admin dashboard | GCC | MEDIUM |
| Control Tower UI | Frontend | MEDIUM |
| Load testing (100+ customers) | All | HIGH |
| Documentation | All | MEDIUM |

---

## Appendix A: Environment Variables

### GCC

```bash
DATABASE_URL=postgresql://user:pass@host:5432/gcc
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
GCC_BUCKET_NAME=gcc-wrktalk-artifacts
SMTP_HOST=smtp.example.com
CI_TOKEN=...  # For Jenkins authentication
```

### Customer Backend

```bash
# Existing
WRKTALK_DATABASE_URL=postgresql://...

# New: Deployment
WRKTALK_GCC_ENDPOINT=https://gcc.wrktalk.com
WRKTALK_GCC_API_KEY=customer-api-key
WRKTALK_WEBHOOK_SECRET=webhook-secret

# New: Bucket
WRKTALK_BUCKET_PROVIDER=s3
WRKTALK_BUCKET_NAME=customer-wrktalk
WRKTALK_BUCKET_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

### Python Agent

```bash
WRKTALK_AGENT_BACKEND_URL=http://localhost:3000
WRKTALK_AGENT_DEPLOYMENT_TYPE=kubernetes  # or docker
WRKTALK_AGENT_KUBE_NAMESPACE=wrktalk
WRKTALK_AGENT_HELM_RELEASE_NAME=wrktalk
WRKTALK_AGENT_BUCKET_PROVIDER=s3
WRKTALK_AGENT_BUCKET_NAME=customer-wrktalk
WRKTALK_AGENT_BUCKET_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

---

## Appendix B: GHCR Image Pull Configuration

### Kubernetes (imagePullSecrets)

```yaml
# Secret created once per cluster
apiVersion: v1
kind: Secret
metadata:
  name: ghcr-pull-secret
  namespace: wrktalk
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <base64 encoded>

# Used in Helm values
imagePullSecrets:
  - name: ghcr-pull-secret
```

### Docker Compose

```bash
# Run once on host
docker login ghcr.io -u USERNAME -p TOKEN
# Credentials stored in ~/.docker/config.json
```

---

**Document Version:** 3.0  
**Last Updated:** December 2024  
**Author:** WrkTalk Engineering Team
