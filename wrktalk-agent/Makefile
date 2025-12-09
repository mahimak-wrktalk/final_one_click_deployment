.PHONY: help install dev test clean docker-k8s docker-compose run-backend run-agent setup

help: ## Show this help message
	@echo "WrkTalk Agent - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Initial setup - create venv and install dependencies
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	./venv/bin/pip install fastapi uvicorn
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env file"; fi
	@echo ""
	@echo "✅ Setup complete!"
	@echo "Run 'source venv/bin/activate' to activate the virtual environment"

install: ## Install agent as package
	pip install -e .

dev: ## Install with development dependencies
	pip install -e .
	pip install fastapi uvicorn pytest pytest-asyncio

clean: ## Clean up temporary files and caches
	rm -rf venv/
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	@echo "✅ Cleaned up!"

test: ## Run tests (when implemented)
	pytest tests/

run-backend: ## Run mock backend server
	@echo "Starting mock backend on http://localhost:3000"
	python tests/mock_backend.py

run-agent: ## Run agent (requires .env)
	@if [ ! -f .env ]; then echo "❌ .env file not found. Run 'make setup' first"; exit 1; fi
	@echo "Starting WrkTalk Agent..."
	@export $$(cat .env | grep -v '^#' | xargs) && python -m wrktalk_agent

run-agent-debug: ## Run agent with debug logging
	@if [ ! -f .env ]; then echo "❌ .env file not found. Run 'make setup' first"; exit 1; fi
	@echo "Starting WrkTalk Agent (DEBUG mode)..."
	@export $$(cat .env | grep -v '^#' | xargs) && \
		export WRKTALK_AGENT_LOG_LEVEL=DEBUG && \
		python -m wrktalk_agent

docker-k8s: ## Build Kubernetes agent Docker image
	docker build -f Dockerfile.kubernetes -t wrktalk-agent:latest .
	@echo "✅ Built: wrktalk-agent:latest (Kubernetes)"

docker-compose-image: ## Build Docker Compose agent image
	docker build -f Dockerfile.docker -t wrktalk-agent:docker .
	@echo "✅ Built: wrktalk-agent:docker (Docker Compose)"

minikube-load: docker-k8s ## Build and load image to minikube
	minikube image load wrktalk-agent:latest
	@echo "✅ Image loaded to minikube"

minikube-deploy: minikube-load ## Deploy agent to minikube
	kubectl apply -f k8s/agent-deployment.yaml
	@echo "✅ Deployed to minikube"
	@echo "View logs: kubectl logs -f -n wrktalk deployment/wrktalk-agent"

minikube-logs: ## Show agent logs in minikube
	kubectl logs -f -n wrktalk deployment/wrktalk-agent

minikube-restart: ## Restart agent in minikube
	kubectl rollout restart deployment/wrktalk-agent -n wrktalk
	@echo "✅ Agent restarted"

minikube-delete: ## Delete agent from minikube
	kubectl delete -f k8s/agent-deployment.yaml
	@echo "✅ Agent deleted"

lint: ## Run linters (requires dev dependencies)
	@echo "Running linters..."
	python -m pylint src/wrktalk_agent/ || true
	python -m mypy src/wrktalk_agent/ || true

format: ## Format code with black (requires dev dependencies)
	@echo "Formatting code..."
	python -m black src/wrktalk_agent/
	python -m isort src/wrktalk_agent/

check-minio: ## Check MinIO connectivity
	@echo "Checking MinIO connectivity..."
	@curl -s http://localhost:9000/minio/health/live && echo "✅ MinIO is accessible" || echo "❌ MinIO is not accessible"

check-backend: ## Check Backend connectivity
	@echo "Checking Backend connectivity..."
	@curl -s http://localhost:3000/ && echo "\n✅ Backend is accessible" || echo "❌ Backend is not accessible"

create-task: ## Create a test deployment task
	./tests/create_test_task.sh

view-tasks: ## View all tasks in mock backend
	@curl -s http://localhost:3000/test/tasks | python -m json.tool

clear-tasks: ## Clear all tasks from mock backend
	@curl -s -X DELETE http://localhost:3000/test/clear
	@echo "✅ All tasks cleared"

status: ## Show current status
	@echo "=== WrkTalk Agent Status ==="
	@echo ""
	@echo "Python version:"
	@python3 --version || echo "❌ Python not found"
	@echo ""
	@echo "Virtual environment:"
	@if [ -d venv ]; then echo "✅ venv exists"; else echo "❌ venv not found (run 'make setup')"; fi
	@echo ""
	@echo "Configuration:"
	@if [ -f .env ]; then echo "✅ .env exists"; else echo "❌ .env not found"; fi
	@echo ""
	@echo "Docker images:"
	@docker images | grep wrktalk-agent || echo "No agent images found"
	@echo ""
	@echo "MinIO:"
	@make check-minio 2>&1 | tail -1
	@echo ""
	@echo "Backend:"
	@make check-backend 2>&1 | tail -1

all: setup docker-k8s ## Run full setup and build
	@echo ""
	@echo "✅ All tasks complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Start backend: make run-backend"
	@echo "  2. Start agent:   make run-agent"
	@echo "  3. Create task:   make create-task"
