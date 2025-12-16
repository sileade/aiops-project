# =============================================================================
# AIOps Platform - Makefile
# =============================================================================
# Быстрый старт: make setup && make up
# =============================================================================

.PHONY: help setup up down restart logs status test lint format clean build push

# Цвета для вывода
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
NC     := \033[0m # No Color

# Переменные
DOCKER_COMPOSE := docker compose
PROJECT_NAME := aiops

# =============================================================================
# HELP
# =============================================================================

help: ## Показать справку
	@echo ""
	@echo "$(GREEN)AIOps Platform - Команды управления$(NC)"
	@echo ""
	@echo "$(YELLOW)Быстрый старт:$(NC)"
	@echo "  make setup    - Первоначальная настройка (создание .env)"
	@echo "  make up       - Запустить все сервисы"
	@echo "  make down     - Остановить все сервисы"
	@echo ""
	@echo "$(YELLOW)Доступные команды:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# SETUP & CONFIGURATION
# =============================================================================

setup: ## Первоначальная настройка проекта
	@echo "$(GREEN)🚀 Настройка AIOps Platform...$(NC)"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(YELLOW)📝 Создан файл .env из .env.example$(NC)"; \
		echo "$(RED)⚠️  Отредактируйте .env и добавьте свои ключи API$(NC)"; \
	else \
		echo "$(GREEN)✓ Файл .env уже существует$(NC)"; \
	fi
	@echo "$(GREEN)✓ Настройка завершена$(NC)"
	@echo ""
	@echo "$(YELLOW)Следующие шаги:$(NC)"
	@echo "  1. Отредактируйте .env файл"
	@echo "  2. Запустите: make up"

setup-dev: ## Настройка для разработки (с зависимостями Python)
	@echo "$(GREEN)🔧 Настройка окружения разработки...$(NC)"
	@make setup
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-cov ruff black pre-commit
	pre-commit install
	@echo "$(GREEN)✓ Окружение разработки готово$(NC)"

# =============================================================================
# DOCKER COMPOSE COMMANDS
# =============================================================================

up: ## Запустить все сервисы
	@echo "$(GREEN)🚀 Запуск AIOps Platform...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo ""
	@make status

up-build: ## Пересобрать и запустить все сервисы
	@echo "$(GREEN)🔨 Сборка и запуск AIOps Platform...$(NC)"
	$(DOCKER_COMPOSE) up -d --build
	@echo ""
	@make status

down: ## Остановить все сервисы
	@echo "$(YELLOW)⏹️  Остановка сервисов...$(NC)"
	$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ Сервисы остановлены$(NC)"

down-clean: ## Остановить и удалить volumes
	@echo "$(RED)🗑️  Остановка и очистка данных...$(NC)"
	$(DOCKER_COMPOSE) down -v
	@echo "$(GREEN)✓ Сервисы остановлены, данные удалены$(NC)"

restart: ## Перезапустить все сервисы
	@echo "$(YELLOW)🔄 Перезапуск сервисов...$(NC)"
	$(DOCKER_COMPOSE) restart
	@make status

restart-api: ## Перезапустить только API
	$(DOCKER_COMPOSE) restart api

restart-bot: ## Перезапустить только Telegram бота
	$(DOCKER_COMPOSE) restart bot

# =============================================================================
# MONITORING & LOGS
# =============================================================================

status: ## Показать статус сервисов
	@echo ""
	@echo "$(GREEN)📊 Статус сервисов:$(NC)"
	@$(DOCKER_COMPOSE) ps
	@echo ""

logs: ## Показать логи всех сервисов
	$(DOCKER_COMPOSE) logs -f

logs-api: ## Показать логи API
	$(DOCKER_COMPOSE) logs -f api

logs-bot: ## Показать логи Telegram бота
	$(DOCKER_COMPOSE) logs -f bot

logs-tail: ## Показать последние 100 строк логов
	$(DOCKER_COMPOSE) logs --tail=100

health: ## Проверить здоровье сервисов
	@echo "$(GREEN)🏥 Проверка здоровья сервисов...$(NC)"
	@curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "$(RED)API недоступен$(NC)"

# =============================================================================
# DEVELOPMENT
# =============================================================================

test: ## Запустить тесты
	@echo "$(GREEN)🧪 Запуск тестов...$(NC)"
	python3 -m pytest tests/ -v -m "unit" --tb=short

test-cov: ## Запустить тесты с покрытием
	@echo "$(GREEN)🧪 Запуск тестов с покрытием...$(NC)"
	python3 -m pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

lint: ## Проверить код линтером
	@echo "$(GREEN)🔍 Проверка кода...$(NC)"
	ruff check app/ tests/

lint-fix: ## Исправить ошибки линтера
	@echo "$(GREEN)🔧 Исправление ошибок линтера...$(NC)"
	ruff check app/ tests/ --fix

format: ## Форматировать код
	@echo "$(GREEN)🎨 Форматирование кода...$(NC)"
	black app/ tests/ --line-length 120

format-check: ## Проверить форматирование
	black app/ tests/ --check --diff --line-length 120

# =============================================================================
# BUILD & DEPLOY
# =============================================================================

build: ## Собрать Docker образы
	@echo "$(GREEN)🔨 Сборка Docker образов...$(NC)"
	$(DOCKER_COMPOSE) build

build-no-cache: ## Собрать Docker образы без кэша
	@echo "$(GREEN)🔨 Сборка Docker образов (без кэша)...$(NC)"
	$(DOCKER_COMPOSE) build --no-cache

push: ## Запушить образы в registry
	@echo "$(GREEN)📤 Публикация образов...$(NC)"
	$(DOCKER_COMPOSE) push

# =============================================================================
# DATABASE & SERVICES
# =============================================================================

shell-api: ## Открыть shell в контейнере API
	$(DOCKER_COMPOSE) exec api /bin/bash

shell-redis: ## Открыть Redis CLI
	$(DOCKER_COMPOSE) exec redis redis-cli

shell-es: ## Открыть shell в Elasticsearch
	$(DOCKER_COMPOSE) exec elasticsearch /bin/bash

# =============================================================================
# CLEANUP
# =============================================================================

clean: ## Очистить временные файлы
	@echo "$(YELLOW)🧹 Очистка временных файлов...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf htmlcov/ 2>/dev/null || true
	@echo "$(GREEN)✓ Очистка завершена$(NC)"

clean-docker: ## Очистить неиспользуемые Docker ресурсы
	@echo "$(YELLOW)🐳 Очистка Docker ресурсов...$(NC)"
	docker system prune -f
	@echo "$(GREEN)✓ Docker очищен$(NC)"

clean-all: clean clean-docker ## Полная очистка

# =============================================================================
# QUICK COMMANDS
# =============================================================================

dev: up logs ## Запустить и показать логи (для разработки)

prod: up-build ## Собрать и запустить для production

quick-test: lint test ## Быстрая проверка (линт + тесты)

# =============================================================================
# PROFILE COMMANDS (Ollama, Full)
# =============================================================================

up-ollama: ## Запустить с локальной LLM (Ollama)
	@echo "$(GREEN)🤖 Запуск AIOps Platform с Ollama...$(NC)"
	$(DOCKER_COMPOSE) --profile ollama up -d
	@echo ""
	@make status
	@echo "$(YELLOW)📝 Для загрузки модели выполните:$(NC)"
	@echo "   docker exec -it aiops-ollama ollama pull llama3.2"

up-full: ## Запустить полную версию (Ollama + Milvus)
	@echo "$(GREEN)🚀 Запуск AIOps Platform (Full)...$(NC)"
	$(DOCKER_COMPOSE) --profile full up -d --build
	@echo ""
	@make status

up-full-open: ## Запустить полную версию и открыть API Docs в браузере
	@echo "$(GREEN)🚀 Запуск AIOps Platform (Full) с открытием документации...$(NC)"
	$(DOCKER_COMPOSE) --profile full up -d --build
	@echo ""
	@make wait-api
	@echo "$(GREEN)🌐 Открытие документации API...$(NC)"
	@if command -v xdg-open > /dev/null; then \
		xdg-open http://localhost:8000/docs; \
	elif command -v open > /dev/null; then \
		open http://localhost:8000/docs; \
	elif command -v start > /dev/null; then \
		start http://localhost:8000/docs; \
	else \
		echo "$(YELLOW)Откройте в браузере: http://localhost:8000/docs$(NC)"; \
	fi
	@echo ""
	@make status

down-ollama: ## Остановить сервисы с профилем Ollama
	$(DOCKER_COMPOSE) --profile ollama down

down-full: ## Остановить сервисы с профилем Full
	$(DOCKER_COMPOSE) --profile full down

# =============================================================================
# BROWSER COMMANDS
# =============================================================================

open-docs: ## Открыть API документацию в браузере
	@echo "$(GREEN)🌐 Открытие API Docs...$(NC)"
	@if command -v xdg-open > /dev/null; then \
		xdg-open http://localhost:8000/docs; \
	elif command -v open > /dev/null; then \
		open http://localhost:8000/docs; \
	elif command -v start > /dev/null; then \
		start http://localhost:8000/docs; \
	else \
		echo "$(YELLOW)Откройте в браузере: http://localhost:8000/docs$(NC)"; \
	fi

open-grafana: ## Открыть Grafana в браузере
	@echo "$(GREEN)📊 Открытие Grafana...$(NC)"
	@if command -v xdg-open > /dev/null; then \
		xdg-open http://localhost:3000; \
	elif command -v open > /dev/null; then \
		open http://localhost:3000; \
	elif command -v start > /dev/null; then \
		start http://localhost:3000; \
	else \
		echo "$(YELLOW)Откройте в браузере: http://localhost:3000$(NC)"; \
	fi

open-prometheus: ## Открыть Prometheus в браузере
	@echo "$(GREEN)📈 Открытие Prometheus...$(NC)"
	@if command -v xdg-open > /dev/null; then \
		xdg-open http://localhost:9090; \
	elif command -v open > /dev/null; then \
		open http://localhost:9090; \
	elif command -v start > /dev/null; then \
		start http://localhost:9090; \
	else \
		echo "$(YELLOW)Откройте в браузере: http://localhost:9090$(NC)"; \
	fi

open-all: ## Открыть все веб-интерфейсы
	@make open-docs
	@sleep 1
	@make open-grafana
	@sleep 1
	@make open-prometheus

# =============================================================================
# OLLAMA COMMANDS
# =============================================================================

ollama-pull: ## Загрузить модель Ollama (llama3.2)
	@echo "$(GREEN)📥 Загрузка модели llama3.2...$(NC)"
	docker exec -it aiops-ollama ollama pull llama3.2

ollama-list: ## Показать установленные модели Ollama
	docker exec -it aiops-ollama ollama list

ollama-run: ## Запустить интерактивный чат с Ollama
	docker exec -it aiops-ollama ollama run llama3.2

# =============================================================================
# UTILITY COMMANDS
# =============================================================================

wait-api: ## Ожидать готовности API (макс 30 сек)
	@echo "$(YELLOW)⏳ Ожидание готовности API...$(NC)"
	@for i in $$(seq 1 30); do \
		if curl -s http://localhost:8000/health > /dev/null 2>&1; then \
			echo "$(GREEN)✓ API готов за $$i сек$(NC)"; \
			exit 0; \
		fi; \
		printf "."; \
		sleep 1; \
	done; \
	echo ""; \
	echo "$(RED)⚠️ Таймаут ожидания API (30 сек). Проверьте логи: make logs-api$(NC)"

wait-services: ## Ожидать готовности всех сервисов
	@echo "$(YELLOW)⏳ Ожидание готовности сервисов...$(NC)"
	@echo "Проверка Redis..."
	@for i in $$(seq 1 15); do \
		if $(DOCKER_COMPOSE) exec -T redis redis-cli ping > /dev/null 2>&1; then \
			echo "$(GREEN)✓ Redis готов$(NC)"; \
			break; \
		fi; \
		sleep 1; \
	done
	@echo "Проверка Elasticsearch..."
	@for i in $$(seq 1 30); do \
		if curl -s http://localhost:9200/_cluster/health > /dev/null 2>&1; then \
			echo "$(GREEN)✓ Elasticsearch готов$(NC)"; \
			break; \
		fi; \
		sleep 1; \
	done
	@make wait-api
