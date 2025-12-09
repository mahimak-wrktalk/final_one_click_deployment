#!/bin/bash
# Script to create test deployment tasks for the mock backend

BACKEND_URL="${BACKEND_URL:-http://localhost:3000}"

echo "Creating test deployment task..."

# Kubernetes deployment task
curl -X POST "${BACKEND_URL}/test/add-task" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "task-k8s-001",
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
        {"key": "FEATURE_X", "value": "true"},
        {"key": "LOG_LEVEL", "value": "debug"}
      ]
    },
    "executeAfter": "2024-01-01T00:00:00Z"
  }'

echo -e "\n\nTask created! Check agent logs to see it being processed."
echo "View all tasks: curl ${BACKEND_URL}/test/tasks"
