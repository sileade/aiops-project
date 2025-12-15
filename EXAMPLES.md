# Примеры Использования AIOps Системы

## 1. Анализ Проблемы с БД

### Сценарий

Ваша база данных PostgreSQL внезапно стала медленной. Вы хотите, чтобы система:
1. Обнаружила проблему.
2. Проанализировала логи и метрики.
3. Предложила план исправления.
4. Выполнила исправление после вашего утверждения.

### Шаги

#### Через Telegram Бот:

```
Вы: /analyze postgres-db
Бот: ▶️ Начинаю анализ для сервиса: postgres-db
...
Бот: ⚠️ Обнаружена аномалия в метриках postgres-db: Аномально высокая загрузка CPU (значение: 95.5)
Бот: 🚨 **Обнаружена Проблема: Исправление проблемы: Database connection refused**
     **Уровень серьезности:** `critical`
     **Описание:** ...
     **Предлагаемый план:**
     ```yaml
     - name: Fix PostgreSQL High CPU
       hosts: postgres-db
       tasks:
         - name: Check PostgreSQL status
           command: systemctl status postgresql
         - name: Restart PostgreSQL
           systemd:
             name: postgresql
             state: restarted
         - name: Verify PostgreSQL is running
           command: pg_isready
     ```
     Требуется ваше утверждение для выполнения плана.

Вы: [Нажимаете кнопку "✅ Утвердить"]
Бот: 🚀 План **Исправление проблемы: Database connection refused** утвержден. Начинаю выполнение...
...
Бот: ✅ План **Исправление проблемы: Database connection refused** успешно выполнен!
```

#### Через API:

```bash
# Запуск анализа
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "postgres-db",
    "time_window": "15m",
    "include_logs": true,
    "include_metrics": true
  }'

# Получение статуса системы
curl http://localhost:8000/status

# Получение информации о плане
curl http://localhost:8000/plans/plan-uuid-here

# Утверждение плана
curl -X POST http://localhost:8000/approve \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "plan-uuid-here",
    "approved": true,
    "reason": "Проблема критична, одобряю исправление"
  }'
```

## 2. Мониторинг Нескольких Сервисов

### Сценарий

У вас есть микросервисная архитектура с 10+ сервисами. Вы хотите мониторить все и получать уведомления об аномалиях.

### Решение

Создайте cron-задачу для периодического анализа:

```bash
# Добавьте в crontab
0 */6 * * * curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"service_name": "api-gateway"}' > /dev/null 2>&1

0 */6 * * * curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"service_name": "auth-service"}' > /dev/null 2>&1

0 */6 * * * curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"service_name": "payment-service"}' > /dev/null 2>&1
```

Система будет автоматически анализировать каждый сервис каждые 6 часов и отправлять вам уведомления в Telegram при обнаружении проблем.

## 3. Кастомные Плейбуки

### Сценарий

Вы хотите, чтобы система использовала ваши собственные Ansible плейбуки вместо автоматически сгенерированных.

### Решение

1. Создайте плейбук в `data/playbooks/`:

```yaml
# data/playbooks/restart-nginx.yml
---
- name: Restart Nginx Service
  hosts: web-servers
  become: yes
  tasks:
    - name: Stop Nginx
      systemd:
        name: nginx
        state: stopped
    
    - name: Check Nginx configuration
      command: nginx -t
      register: nginx_check
    
    - name: Start Nginx
      systemd:
        name: nginx
        state: started
      when: nginx_check.rc == 0
    
    - name: Verify Nginx is running
      command: systemctl is-active nginx
      register: nginx_status
    
    - name: Send notification
      debug:
        msg: "Nginx restart completed. Status: {{ nginx_status.stdout }}"
```

2. Модифицируйте `ai_service.py` для использования кастомных плейбуков:

```python
async def generate_remediation_plan(context: str) -> str:
    """Генерирует план исправления, используя кастомные плейбуки."""
    
    # Определяем тип проблемы
    if "nginx" in context.lower():
        with open("/app/data/playbooks/restart-nginx.yml", "r") as f:
            return f.read()
    
    # Для других проблем используем AI-генерацию
    return await ai_service.generate_remediation_plan_with_llm(context)
```

## 4. Интеграция с Slack (Дополнительно)

### Сценарий

Вы хотите получать уведомления не только в Telegram, но и в Slack.

### Решение

Создайте новый файл `app/services/slack_service.py`:

```python
import aiohttp
from config.settings import settings

async def send_slack_message(text: str, channel: str = "#alerts"):
    """Отправляет сообщение в Slack."""
    webhook_url = settings.slack_webhook_url
    payload = {
        "channel": channel,
        "text": text
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(webhook_url, json=payload) as response:
            return response.status == 200
```

Затем обновите `telegram_service.py` для отправки в оба канала:

```python
async def send_message(text: str, parse_mode: str = "Markdown"):
    """Отправляет сообщение в Telegram и Slack."""
    await send_telegram_message(text, parse_mode)
    await slack_service.send_slack_message(text)
```

## 5. Расширенная Аналитика

### Сценарий

Вы хотите видеть исторические данные об аномалиях и их исправлениях.

### Решение

Создайте эндпоинт для получения истории:

```python
@app.get("/analytics/anomalies", tags=["Analytics"])
async def get_anomalies_history(days: int = 7):
    """Получить историю аномалий за последние N дней."""
    # Запрос к Elasticsearch для получения истории аномалий
    query = {
        "query": {
            "range": {
                "timestamp": {
                    "gte": f"now-{days}d"
                }
            }
        },
        "aggs": {
            "anomalies_by_service": {
                "terms": {
                    "field": "service_name.keyword"
                }
            }
        }
    }
    result = await es_client.search(index="anomalies", body=query)
    return result
```

## 6. Автоматическое Масштабирование

### Сценарий

Когда система обнаруживает высокую нагрузку, она должна автоматически масштабировать приложение.

### Решение

Создайте плейбук для масштабирования:

```yaml
# data/playbooks/scale-up.yml
---
- name: Scale Up Application
  hosts: kubernetes-master
  tasks:
    - name: Get current replica count
      command: kubectl get deployment my-app -o jsonpath='{.spec.replicas}'
      register: current_replicas
    
    - name: Scale up deployment
      command: kubectl scale deployment my-app --replicas={{ current_replicas.stdout | int + 2 }}
    
    - name: Wait for new pods to be ready
      command: kubectl rollout status deployment/my-app
    
    - name: Verify scaling
      command: kubectl get deployment my-app
      register: scaling_result
    
    - name: Log scaling action
      debug:
        msg: "Scaled up to {{ scaling_result.stdout }}"
```

Затем обновите `ai_service.py` для выбора этого плейбука при обнаружении высокой нагрузки.

## 7. Тестирование Системы

### Локальное Тестирование

```bash
# Тест API
python -m pytest tests/ -v

# Тест Telegram бота
python -m pytest tests/test_bot.py -v

# Тест сервисов анализа
python -m pytest tests/test_analysis_service.py -v
```

### Интеграционное Тестирование

```bash
# Запустить все сервисы
docker-compose up -d

# Дождаться инициализации
sleep 10

# Отправить тестовый запрос
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"service_name": "test-service"}'

# Проверить логи
docker-compose logs -f api
```

## 8. Резервное Копирование и Восстановление

### Резервное копирование

```bash
# Резервная копия Redis
docker-compose exec redis redis-cli BGSAVE

# Резервная копия Elasticsearch
curl -X PUT "localhost:9200/_snapshot/backup" \
  -H 'Content-Type: application/json' \
  -d'{
    "type": "fs",
    "settings": {
      "location": "/data/snapshots"
    }
  }'
```

### Восстановление

```bash
# Восстановление из Redis
docker-compose exec redis redis-cli RESTORE

# Восстановление из Elasticsearch
curl -X POST "localhost:9200/_snapshot/backup/snapshot_name/_restore"
```

---

Эти примеры показывают различные способы использования AIOps системы. Вы можете адаптировать их под свои нужды!
