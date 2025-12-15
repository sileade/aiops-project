# Подробная Инструкция по Настройке AIOps Проекта

## 1. Создание Telegram Бота

### Шаг 1: Создание бота через BotFather

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather).
2. Отправьте команду `/newbot`.
3. Следуйте инструкциям:
   - Введите имя для бота (например, `MyAIOpsBot`).
   - Введите username для бота (должен заканчиваться на `_bot`, например, `my_aiops_bot`).
4. BotFather вернет вам **токен доступа**. Скопируйте его.

### Шаг 2: Получение вашего Chat ID

1. Найдите бота [@userinfobot](https://t.me/userinfobot) в Telegram.
2. Отправьте ему любое сообщение.
3. Бот вернет вашу информацию, включая **ID**.

## 2. Конфигурация Проекта

### Шаг 1: Клонирование репозитория

```bash
cd /path/to/projects
git clone <repository_url> aiops_project
cd aiops_project
```

### Шаг 2: Создание файла `.env`

```bash
cp .env.example .env
```

### Шаг 3: Редактирование `.env` файла

Откройте `.env` и заполните следующие поля:

```env
# Telegram
TELEGRAM_TOKEN=<ваш_токен_от_BotFather>
ADMIN_CHAT_ID=<ваш_chat_id>

# API Server
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=true

# Остальные настройки (оставьте по умолчанию для локального развертывания)
```

## 3. Запуск Проекта

### Вариант 1: Запуск с Docker Compose (Рекомендуется)

#### Предварительные требования:
- Docker
- Docker Compose

#### Запуск:

```bash
cd /path/to/aiops_project

# Сборка и запуск всех сервисов
docker-compose up --build

# Для запуска в фоновом режиме
docker-compose up -d --build
```

#### Проверка статуса:

```bash
# Посмотреть логи всех сервисов
docker-compose logs -f

# Посмотреть логи конкретного сервиса
docker-compose logs -f api
docker-compose logs -f bot
```

#### Остановка:

```bash
docker-compose down
```

### Вариант 2: Локальный запуск (для разработки)

#### Предварительные требования:
- Python 3.11+
- Redis (локально или в Docker)
- Elasticsearch (локально или в Docker)

#### Установка зависимостей:

```bash
pip install -r requirements.txt
```

#### Запуск API сервера:

```bash
# В одном терминале
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Запуск Telegram бота:

```bash
# В другом терминале
python bot/main.py
```

## 4. Проверка Работоспособности

### Проверка API

```bash
# Проверка здоровья API
curl http://localhost:8000/

# Получение статуса системы
curl http://localhost:8000/status
```

### Проверка Telegram Бота

1. Откройте Telegram и найдите вашего бота (по username).
2. Отправьте команду `/start`.
3. Отправьте команду `/status` для проверки статуса системы.

## 5. Первый Анализ

### Через Telegram Бот:

1. Отправьте команду: `/analyze my-service`
2. Система запустит анализ в фоновом режиме.
3. Вы получите уведомления о результатах анализа.
4. Если найдены проблемы, вы получите запрос на утверждение плана исправления.
5. Нажмите кнопку "✅ Утвердить" для выполнения плана.

### Через API:

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"service_name": "my-service", "time_window": "15m"}'
```

## 6. Интеграция с AI-Моделями

### Опция 1: Облачные API (Рекомендуется для быстрого старта)

Используйте Hugging Face Inference Endpoints:

1. Зарегистрируйтесь на [huggingface.co](https://huggingface.co).
2. Создайте Inference Endpoint для модели `deepseek-ai/DeepSeek-Coder-V2`.
3. Скопируйте URL эндпоинта.
4. Обновите в `.env`:
   ```env
   LLM_ENDPOINT=https://your-endpoint.huggingface.co
   ```

### Опция 2: Локальное развертывание (требует GPU)

Если у вас есть NVIDIA GPU:

1. Установите `nvidia-docker`.
2. В `docker-compose.yml` раскомментируйте сервис `llm`.
3. Запустите: `docker-compose up llm`

## 7. Решение Проблем

### Бот не получает сообщения

- Проверьте, что `TELEGRAM_TOKEN` и `ADMIN_CHAT_ID` верны в `.env`.
- Проверьте логи: `docker-compose logs bot`.

### API не запускается

- Проверьте, что порт 8000 не занят.
- Проверьте логи: `docker-compose logs api`.

### Elasticsearch не запускается

- Убедитесь, что у вас достаточно памяти (минимум 2GB).
- Проверьте логи: `docker-compose logs elasticsearch`.

### Ошибки при подключении к AI-модели

- Проверьте, что `LLM_ENDPOINT` верен.
- Убедитесь, что модель доступна и работает.

## 8. Дальнейшие Шаги

После успешной настройки:

1. **Интегрируйте с вашей инфраструктурой:**
   - Настройте Prometheus для сбора метрик.
   - Настройте Fluentd для сбора логов.

2. **Создавайте Ansible плейбуки:**
   - Система будет генерировать плейбуки автоматически, но вы можете создавать кастомные.

3. **Настройте мониторинг:**
   - Добавьте алерты для критических проблем.
   - Настройте автоматический анализ по расписанию.

4. **Развертывание в Production:**
   - Используйте Kubernetes для оркестрации.
   - Настройте CI/CD для автоматического развертывания.
