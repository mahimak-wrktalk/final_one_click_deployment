#!/bin/bash
# Advanced test script with parameters

BACKEND_URL="${BACKEND_URL:-http://localhost:3000}"
VERSION="${1:-2.3.0}"
VALUES_FILE="${2:-values.yaml}"
BACKEND_TAG="${3:-latest}"
MEDIA_TAG="${4:-latest}"

echo "Creating deployment task for version $VERSION with $VALUES_FILE"

curl -X POST "${BACKEND_URL}/test/add-task" \
  -H "Content-Type: application/json" \
  -d "{
    \"id\": \"task-${VERSION}-$(date +%s)\",
    \"type\": \"deploy\",
    \"payload\": {
      \"chart\": {
        \"bucketPath\": \"artifacts/helm/wrktalk-${VERSION}.tgz\",
        \"version\": \"${VERSION}\"
      },
      \"valuesBucketPath\": \"config/${VALUES_FILE}\",
      \"imageTags\": {
        \"backend\": \"${BACKEND_TAG}\",
        \"media\": \"${MEDIA_TAG}\"
      },
      \"newNonEssentialEnvs\": [
        {\"key\": \"FEATURE_X\", \"value\": \"true\"},
        {\"key\": \"LOG_LEVEL\", \"value\": \"debug\"}
      ]
    },
    \"executeAfter\": \"2024-01-01T00:00:00Z\"
  }"

echo -e "\n\n✅ Task created!"
echo "View tasks: curl ${BACKEND_URL}/test/tasks | jq"