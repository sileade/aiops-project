# 🚀 AIOps Platform - Быстрый старт

## Требования

- Docker 20.10+
- Docker Compose V2
- 4GB RAM минимум (8GB рекомендуется)
- 10GB свободного места на диске

## Установка за 3 шага

### 1. Клонирование репозитория

```bash
git clone https://github.com/sileade/aiops-project.git
cd aiops-project
```

### 2. Настройка

```bash
# Автоматическая настройка
make setup

# Или вручную
cp .env.example .env
```

Отредактируйте `.env` и добавьте минимум:
```env
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
OPENAI_API_KEY=your_api_key
```

### 3. Запуск

```bash
# Базовый запуск
make up

# Или напрямую через Docker Compose
docker compose up -d
```

## Варианты запуска

### Базовый (без локальной LLM)

```bash
docker compose up -d
```

Включает: API, Bot, Redis, Elasticsearch, Prometheus, Grafana, Alertmanager

### С локальной LLM (Ollama)

```bash
docker compose --profile ollama up -d

# Загрузка модели
docker exec -it aiops-ollama ollama pull llama3.2
```

### Полная установка

```bash
docker compose --profile full up -d
```

Включает всё + Ollama + Milvus (векторная БД)

## Проверка работы

### Статус сервисов

```bash
make status
# или
docker compose ps
```

### Health check

```bash
curl http://localhost:8000/health
```

### Логи

```bash
# Все сервисы
make logs

# Только API
make logs-api

# Только бот
make logs-bot
```

## Доступные сервисы

| Сервис | URL | Описание |
|--------|-----|----------|
| API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Prometheus | http://localhost:9090 | Метрики |
| Grafana | http://localhost:3000 | Дашборды (admin/admin) |
| Alertmanager | http://localhost:9093 | Алерты |
| Elasticsearch | http://localhost:9200 | Логи |

## Команды Makefile

```bash
make help          # Показать все команды
make up            # Запустить сервисы
make down          # Остановить сервисы
make restart       # Перезапустить
make logs          # Показать логи
make status        # Статус сервисов
make test          # Запустить тесты
make lint          # Проверить код
make clean         # Очистить временные файлы
```

## Telegram бот

После запуска найдите бота в Telegram и отправьте:

```
/start    - Начать работу
/status   - Статус системы
/analyze  - Запустить анализ
/help     - Справка по командам
```

## Решение проблем

### Сервисы не запускаются

```bash
# Проверить логи
docker compose logs

# Пересобрать образы
make up-build
```

### Elasticsearch не стартует

```bash
# Увеличить лимит памяти
sudo sysctl -w vm.max_map_count=262144

# Сделать постоянным
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Очистка и перезапуск

```bash
# Остановить и удалить данные
make down-clean

# Запустить заново
make up-build
```

## Следующие шаги

1. 📖 Прочитайте [полную документацию](../README.md)
2. ⚙️ Настройте [интеграции](../README.md#configuration)
3. 📊 Создайте дашборды в Grafana
4. 🔔 Настройте уведомления (Slack, Email, PagerDuty)
