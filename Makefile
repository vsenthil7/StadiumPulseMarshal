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
