# Интеграция с n8n

## Обзор

n8n - это платформа автоматизации workflow с открытым исходным кодом. Интеграция AIOps с n8n позволяет:

- **Автоматизировать реакцию на алерты** - создавать сложные workflow для обработки инцидентов
- **Интегрировать внешние системы** - подключать Slack, PagerDuty, Jira и сотни других сервисов
- **Создавать кастомные автоматизации** - без написания кода
- **Визуализировать процессы** - наглядное представление workflow

## Быстрый старт

### 1. Запуск с n8n

```bash
# Запуск AIOps с n8n
make up-n8n

# Или полная версия (с Ollama, Milvus, n8n)
make up-full
```

### 2. Доступ к n8n

- **URL**: http://localhost:5678
- **Логин**: admin
- **Пароль**: aiops123 (по умолчанию)

### 3. Настройка переменных окружения

```env
# .env файл
N8N_PORT=5678
N8N_BASIC_AUTH=true
N8N_USER=admin
N8N_PASSWORD=your_secure_password
N8N_WEBHOOK_SECRET=your_webhook_secret
```

## Архитектура интеграции

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   AIOps API     │────▶│   n8n Webhooks  │────▶│  External       │
│   (Events)      │     │   (Workflows)   │     │  Services       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │                       ▼                       │
        │               ┌─────────────────┐            │
        └──────────────▶│   AIOps API     │◀───────────┘
                        │   (Commands)    │
                        └─────────────────┘
```

## API Endpoints

### Отправка событий в n8n

```bash
# Отправка события
POST /api/v1/n8n/events/send
{
    "event_type": "alert.fired",
    "data": {
        "alert_name": "High CPU",
        "severity": "critical",
        "description": "CPU usage > 90%"
    }
}
```

### Получение команд от n8n

```bash
# Webhook для команд
POST /api/v1/n8n/webhook/command
{
    "command": "restart_service",
    "target": "nginx",
    "parameters": {},
    "callback_url": "http://n8n:5678/webhook/callback"
}
```

### Регистрация webhook

```bash
# Регистрация workflow для получения событий
POST /api/v1/n8n/webhooks/register
{
    "workflow_id": "alert-handler-1",
    "name": "Alert Handler",
    "webhook_url": "http://n8n:5678/webhook/aiops-alert",
    "triggers": ["alert.fired", "alert.resolved"],
    "description": "Обработка алертов"
}
```

## Типы событий

| Событие | Описание |
|---------|----------|
| `alert.fired` | Сработал алерт |
| `alert.resolved` | Алерт разрешен |
| `incident.created` | Создан инцидент |
| `incident.updated` | Инцидент обновлен |
| `incident.resolved` | Инцидент разрешен |
| `anomaly.detected` | Обнаружена аномалия |
| `action.requested` | Запрошено действие |
| `action.completed` | Действие выполнено |
| `backup.completed` | Бэкап завершен |
| `deployment.started` | Деплой начат |
| `deployment.completed` | Деплой завершен |

## Поддерживаемые команды

| Команда | Описание | Параметры |
|---------|----------|-----------|
| `restart_service` | Перезапуск сервиса | `target`: имя сервиса |
| `run_playbook` | Запуск Ansible плейбука | `playbook`: имя плейбука |
| `analyze_logs` | Анализ логов | `timeframe`: период |
| `create_backup` | Создание бэкапа | `target`: что бэкапить |
| `scale_service` | Масштабирование | `replicas`: количество |
| `block_ip` | Блокировка IP | `ip`: адрес, `duration`: время |
| `send_notification` | Отправка уведомления | `channel`, `message` |
| `health_check` | Проверка здоровья | `service`: сервис |

## Примеры Workflow

### 1. Автоматическая эскалация алертов

```
Webhook (alert.fired)
    ↓
Check Severity
    ↓
┌─────────────────────────────────────┐
│ Critical?                           │
│   Yes → Send PagerDuty Alert        │
│         Send Telegram Message       │
│         Create Jira Ticket          │
│   No  → Send Slack Message          │
│         Log to Elasticsearch        │
└─────────────────────────────────────┘
```

### 2. Автоматическое восстановление

```
Webhook (alert.fired)
    ↓
Analyze Alert Type
    ↓
┌─────────────────────────────────────┐
│ High Memory?                        │
│   → Restart Service                 │
│   → Wait 60s                        │
│   → Check Health                    │
│   → Notify Result                   │
└─────────────────────────────────────┘
```

### 3. Ежедневный отчет

```
Schedule (Cron: 0 9 * * *)
    ↓
Get Metrics from AIOps
    ↓
Generate Report
    ↓
Send Email to Team
```

## Безопасность

### Подпись запросов

Все запросы от AIOps к n8n подписываются HMAC-SHA256:

```python
signature = hmac.new(
    webhook_secret.encode(),
    payload.encode(),
    hashlib.sha256
).hexdigest()

headers = {
    "X-AIOps-Signature": signature,
    "X-AIOps-Event": event_type
}
```

### Проверка подписи в n8n

```javascript
// В n8n Function Node
const crypto = require('crypto');
const secret = $env.AIOPS_WEBHOOK_SECRET;
const signature = $input.first().headers['x-aiops-signature'];
const payload = JSON.stringify($input.first().json);

const expected = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

if (signature !== expected) {
    throw new Error('Invalid signature');
}
```

## Makefile команды

```bash
# Запуск с n8n
make up-n8n

# Остановка
make down-n8n

# Логи n8n
make logs-n8n

# Открыть n8n в браузере
make open-n8n

# Импорт workflows
make n8n-import

# Экспорт workflows
make n8n-export

# Тест webhook
make n8n-test-webhook
```

## Troubleshooting

### n8n не запускается

```bash
# Проверить логи
make logs-n8n

# Проверить порт
netstat -tlnp | grep 5678
```

### Webhook не получает события

1. Проверьте регистрацию webhook:
```bash
curl http://localhost:8000/api/v1/n8n/webhooks
```

2. Проверьте доступность n8n из контейнера API:
```bash
docker exec aiops-api curl http://n8n:5678/healthz
```

### События не доходят

1. Проверьте типы событий в регистрации
2. Проверьте логи API на ошибки отправки
3. Убедитесь, что workflow активен в n8n

## Полезные ссылки

- [n8n Documentation](https://docs.n8n.io/)
- [n8n Nodes Library](https://n8n.io/integrations)
- [n8n Community](https://community.n8n.io/)
