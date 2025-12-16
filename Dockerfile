# =============================================================================
# AIOps Platform - Multi-stage Dockerfile
# =============================================================================
# Сборка:
#   docker build --target api -t aiops-api .
#   docker build --target bot -t aiops-bot .
# =============================================================================

# =============================================================================
# BASE STAGE - Общие зависимости
# =============================================================================
FROM python:3.11-slim as base

# Метаданные
LABEL maintainer="AIOps Team"
LABEL version="1.0.0"
LABEL description="AIOps Platform - AI-powered IT Operations"

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libffi-dev \
    sshpass \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Создание рабочей директории
WORKDIR /app

# Копирование и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# API STAGE - FastAPI Backend
# =============================================================================
FROM base as api

# Копирование исходного кода
COPY app/ ./app/
COPY config/ ./config/
COPY playbooks/ ./playbooks/

# Создание директории для логов
RUN mkdir -p /app/logs && chmod 755 /app/logs

# Создание непривилегированного пользователя
RUN useradd -m -u 1000 aiops && chown -R aiops:aiops /app
USER aiops

# Порт API
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запуск API
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# BOT STAGE - Telegram Bot
# =============================================================================
FROM base as bot

# Копирование исходного кода
COPY app/ ./app/
COPY bot/ ./bot/
COPY config/ ./config/

# Создание директории для логов
RUN mkdir -p /app/logs && chmod 755 /app/logs

# Создание непривилегированного пользователя
RUN useradd -m -u 1000 aiops && chown -R aiops:aiops /app
USER aiops

# Запуск бота
CMD ["python", "bot/main.py"]

# =============================================================================
# DEV STAGE - Для разработки
# =============================================================================
FROM base as dev

# Установка dev зависимостей
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    ruff \
    black \
    pre-commit \
    ipython

# Копирование всего проекта
COPY . .

# Создание директории для логов
RUN mkdir -p /app/logs && chmod 755 /app/logs

# Запуск в dev режиме с hot-reload
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =============================================================================
# TEST STAGE - Для тестирования
# =============================================================================
FROM dev as test

# Запуск тестов
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
