'''
Сервисный модуль для анализа логов из Elasticsearch и генерации плейбуков.
'''

import logging
from elasticsearch import Elasticsearch
from datetime import datetime, timedelta

from config.settings import settings
from app.services.qwen_service import QwenService
from app.services.playbook_service import PlaybookService
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)

class LogAnalysisService:
    def __init__(self):
        self.es_client = Elasticsearch(settings.ELASTICSEARCH_URL)
        self.ai_service = QwenService()
        self.playbook_service = PlaybookService()
        self.telegram_service = TelegramService()

    def get_logs(self, index: str, minutes_ago: int, query: dict) -> list:
        '''Получает логи из Elasticsearch за указанный период.'''
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=minutes_ago)

            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            query,
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": start_time.isoformat(),
                                        "lt": end_time.isoformat()
                                    }
                                }
                            }
                        ]
                    }
                },
                "size": 100, # Ограничиваем количество логов для анализа
                "sort": [{"@timestamp": "desc"}]
            }

            response = self.es_client.search(index=index, body=search_body)
            return [hit['_source'] for hit in response['hits']['hits']]
        except Exception as e:
            logger.error(f"Ошибка получения логов из Elasticsearch: {e}")
            return []

    async def analyze_and_propose_remediation(self, service_name: str, device_type: str):
        '''
        Анализирует логи, генерирует плейбук и отправляет запрос на утверждение.
        '''
        logger.info(f"Запуск анализа логов для сервиса: {service_name}")
        
        # 1. Получаем логи с ошибками
        logs = self.get_logs(
            index=f"{service_name}-logs-*",
            minutes_ago=60, # Анализируем за последний час
            query={"match": {"log.level": "error"}} # Пример запроса
        )

        if not logs:
            logger.info(f"Критических ошибок для '{service_name}' не найдено.")
            return

        # 2. Формируем контекст для AI
        log_summary = "\n".join([log.get('message', '') for log in logs[:10]]) # Берем последние 10 ошибок
        log_snippet = "\n".join([log.get('message', '') for log in logs[:5]]) # Фрагмент для Telegram

        context = f"Проанализируй следующие ошибки из логов сервиса '{service_name}' и определи основную проблему:\n\n{log_summary}"

        # 3. Получаем анализ от AI
        problem_description = self.ai_service.interpret_command(context)

        if not problem_description or "нет явных проблем" in problem_description.lower():
            logger.info("AI не обнаружил конкретной проблемы для исправления.")
            return

        # 4. Генерируем плейбук
        playbook_path = self.playbook_service.generate_playbook(problem_description, device_type)

        if not playbook_path:
            logger.warning("Не удалось сгенерировать плейбук для обнаруженной проблемы.")
            return

        # 5. Отправляем запрос на утверждение в Telegram
        logger.info(f"Отправка запроса на утверждение для плейбука: {playbook_path}")
        await self.telegram_service.send_approval_request(
            chat_id=settings.admin_chat_id,
            problem_description=problem_description,
            log_snippet=log_snippet,
            playbook_path=playbook_path
        )

# Пример использования (для запуска из cron или другого планировщика)
async def main():
    log_analyzer = LogAnalysisService()
    
    # Анализ логов для разных систем
    await log_analyzer.analyze_and_propose_remediation(service_name="mikrotik", device_type="mikrotik")
    await log_analyzer.analyze_and_propose_remediation(service_name="unifi", device_type="unifi")
    # Для Proxmox можно добавить аналогичный вызов, если настроен сбор логов в ES
    # await log_analyzer.analyze_and_propose_remediation(service_name="proxmox", device_type="proxmox")

if __name__ == '__main__':
    import asyncio
    # Убедитесь, что у вас есть запущенный event loop
    asyncio.run(main())
