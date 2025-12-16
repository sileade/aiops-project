#!/bin/bash
# =============================================================================
# AIOps Platform - Quick Setup Script
# =============================================================================
# Использование: ./scripts/setup.sh [--with-ollama] [--full]
# =============================================================================

set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции вывода
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; exit 1; }

# Баннер
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           🚀 AIOps Platform - Quick Setup                 ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Парсинг аргументов
WITH_OLLAMA=false
FULL_INSTALL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --with-ollama)
            WITH_OLLAMA=true
            shift
            ;;
        --full)
            FULL_INSTALL=true
            WITH_OLLAMA=true
            shift
            ;;
        --help|-h)
            echo "Использование: ./scripts/setup.sh [OPTIONS]"
            echo ""
            echo "Опции:"
            echo "  --with-ollama  Установить с локальной LLM (Ollama)"
            echo "  --full         Полная установка (Ollama + Milvus)"
            echo "  --help, -h     Показать эту справку"
            exit 0
            ;;
        *)
            error "Неизвестная опция: $1"
            ;;
    esac
done

# Проверка Docker
info "Проверка Docker..."
if ! command -v docker &> /dev/null; then
    error "Docker не установлен. Установите Docker: https://docs.docker.com/get-docker/"
fi

if ! docker info &> /dev/null; then
    error "Docker daemon не запущен. Запустите Docker."
fi
success "Docker готов"

# Проверка Docker Compose
info "Проверка Docker Compose..."
if ! docker compose version &> /dev/null; then
    error "Docker Compose не установлен. Установите Docker Compose V2."
fi
success "Docker Compose готов"

# Создание .env файла
info "Настройка конфигурации..."
if [ ! -f .env ]; then
    cp .env.example .env
    success "Создан файл .env из .env.example"
    warning "Отредактируйте .env и добавьте свои ключи API!"
else
    success "Файл .env уже существует"
fi

# Создание необходимых директорий
info "Создание директорий..."
mkdir -p playbooks logs data
success "Директории созданы"

# Проверка обязательных переменных
info "Проверка конфигурации..."
source .env 2>/dev/null || true

MISSING_VARS=()
if [ -z "$TELEGRAM_TOKEN" ] || [ "$TELEGRAM_TOKEN" = "your_telegram_bot_token" ]; then
    MISSING_VARS+=("TELEGRAM_TOKEN")
fi
if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key" ]; then
    MISSING_VARS+=("OPENAI_API_KEY")
fi

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    warning "Следующие переменные не настроены: ${MISSING_VARS[*]}"
    warning "Система будет работать в ограниченном режиме"
fi

# Определение профиля Docker Compose
PROFILE=""
if [ "$FULL_INSTALL" = true ]; then
    PROFILE="--profile full"
    info "Режим: Полная установка (с Ollama и Milvus)"
elif [ "$WITH_OLLAMA" = true ]; then
    PROFILE="--profile ollama"
    info "Режим: С локальной LLM (Ollama)"
else
    info "Режим: Базовая установка"
fi

# Сборка образов
info "Сборка Docker образов..."
docker compose $PROFILE build

success "Образы собраны"

# Запуск сервисов
info "Запуск сервисов..."
docker compose $PROFILE up -d

# Ожидание запуска
info "Ожидание запуска сервисов..."
sleep 10

# Проверка статуса
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              🎉 Установка завершена!                      ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Статус сервисов
docker compose $PROFILE ps

echo ""
echo -e "${BLUE}📍 Доступные сервисы:${NC}"
echo -e "   • API:          http://localhost:8000"
echo -e "   • API Docs:     http://localhost:8000/docs"
echo -e "   • Prometheus:   http://localhost:9090"
echo -e "   • Grafana:      http://localhost:3000 (admin/admin)"
echo -e "   • Alertmanager: http://localhost:9093"

if [ "$WITH_OLLAMA" = true ]; then
    echo -e "   • Ollama:       http://localhost:11434"
fi

echo ""
echo -e "${YELLOW}📝 Следующие шаги:${NC}"
echo "   1. Отредактируйте .env файл (если еще не сделали)"
echo "   2. Перезапустите: docker compose restart"
echo "   3. Проверьте логи: docker compose logs -f"
echo ""

if [ "$WITH_OLLAMA" = true ]; then
    echo -e "${YELLOW}🤖 Для загрузки модели Ollama:${NC}"
    echo "   docker exec -it aiops-ollama ollama pull llama3.2"
    echo ""
fi

echo -e "${GREEN}Готово! Используйте 'make help' для списка команд.${NC}"
