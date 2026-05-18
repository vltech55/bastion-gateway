.PHONY: help up down logs build migrate test lint format psql load clean

help:
	@echo "Targets:"
	@echo "  up        gateway + postgres + redis + prometheus + grafana"
	@echo "  migrate   alembic upgrade head"
	@echo "  load      run scripts/load_test.py to populate metrics"
	@echo "  test      pytest"
	@echo "  lint      ruff + mypy"
	@echo "  format    ruff format + autofix"
	@echo "  psql      open psql"
	@echo "  logs      tail logs"
	@echo "  down      stop containers"
	@echo "  clean     drop volumes"

up:
	docker compose up -d
	@echo "Gateway:    http://localhost:8080/docs"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana:    http://localhost:3003 (admin / admin)"

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

migrate:
	docker compose exec gateway alembic upgrade head

load:
	docker compose exec gateway python -m scripts.load_test

test:
	docker compose exec gateway pytest -v

lint:
	docker compose exec gateway ruff check src tests scripts
	docker compose exec gateway mypy src

format:
	docker compose exec gateway ruff format src tests scripts
	docker compose exec gateway ruff check --fix src tests scripts

psql:
	docker compose exec postgres psql -U gateway

clean:
	docker compose down -v
