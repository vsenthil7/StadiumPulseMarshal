.PHONY: install dev build test e2e docker
install:
	cd backend && pip install -e .[dev]
	cd frontend && npm install
dev:
	bash scripts/dev.sh
build:
	cd frontend && npm run build
test:
	cd backend && python -m pytest --cov=app --cov-report=term-missing
e2e:
	cd e2e && npx playwright test
docker:
	docker build -t stadiumpulse-marshal .
	docker run -p 8080:8080 stadiumpulse-marshal

# --- Multi-instance demo (requires a Docker host) ---
.PHONY: multi-up multi-verify multi-down
multi-up: ## Build + start redis + 2 app replicas + nginx LB
	docker compose up --build -d
	@echo "Waiting for the load balancer on http://localhost:8088 ..."
	@for i in $$(seq 1 30); do curl -sf http://localhost:8088/api/v1/health >/dev/null && break || sleep 1; done

multi-verify: ## Assert the shared rate limit holds across both replicas
	./scripts/verify_multi_instance.sh

multi-down: ## Tear down the multi-instance stack
	docker compose down -v

# --- Definition-of-DONE verification ---
.PHONY: verify-live
verify-live: ## Run environment-dependent DoD checks (skips cleanly when prereqs absent)
	./scripts/verify_live.sh
