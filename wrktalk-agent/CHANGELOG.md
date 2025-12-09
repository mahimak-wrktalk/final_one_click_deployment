# Changelog

## [1.1.0] - 2024-12-05

### Removed
- **License validation functionality** - Removed from all components
  - Removed `LicenseError` exception class from [agent.py](src/wrktalk_agent/agent.py)
  - Removed `check_license()` method from [backend.py](src/wrktalk_agent/client/backend.py)
  - Removed `GET /internal/license/status` endpoint from [mock_backend.py](tests/mock_backend.py)
  - Updated deployment flow documentation to remove license check step
  - Updated all README files to remove license validation references

### Changed Files
1. **src/wrktalk_agent/agent.py**
   - Removed `LicenseError` class
   - Removed license check from `_poll_and_execute()` method
   - Deployment flow now proceeds directly from marking task as in-progress to execution

2. **src/wrktalk_agent/client/backend.py**
   - Removed `check_license()` method

3. **tests/mock_backend.py**
   - Removed `/internal/license/status` endpoint
   - Updated root endpoint documentation

4. **Documentation Updates**
   - README.md - Removed license validation from features list
   - PROJECT_SUMMARY.md - Removed license validation references from:
     - Error Handling section
     - Architecture Alignment table
     - Deployment flow diagrams (both K8s and Docker)
     - Backend API endpoints list
   - TESTING_GUIDE.md - Removed license check from execution steps
   - QUICKSTART.md - Removed license check from sample logs

### Deployment Flow Changes

**Before:**
```
1. Agent polls Backend
2. Receives task
3. Mark task in progress
4. Check license ❌ (REMOVED)
5. Insert new envs
6. Download artifacts
...
```

**After:**
```
1. Agent polls Backend
2. Receives task
3. Mark task in progress
4. Insert new envs
5. Download artifacts
...
```

### API Endpoints

**Removed Endpoint:**
- `GET /internal/license/status` - No longer needed

**Remaining Agent Endpoints:**
- `GET /internal/agent/tasks` - Poll for pending tasks
- `POST /internal/agent/tasks/{id}/status` - Update task status
- `POST /internal/agent/tasks/{id}/heartbeat` - Send heartbeat
- `POST /internal/config` - Insert non-essential environment variables

### Testing

No changes required to test infrastructure. The mock backend and agent will work without license validation.

### Migration Notes

If you were planning to implement license validation in your Backend:
- You can skip the `license_status` endpoint implementation
- Remove any license-related database tables or fields
- The agent will work without any license checks

---

## [1.0.0] - 2024-12-05

### Added
- Initial release with full deployment agent implementation
- Support for Kubernetes (Helm) and Docker Compose deployments
- MinIO/S3 integration for artifact downloads
- Heartbeat system for long-running tasks
- Mock backend for testing
- Comprehensive documentation
