'''
Сервисный модуль для анализа логов из Elasticsearch.

Этот модуль отвечает за:
- Подключение к Elasticsearch.
- Запрос и получение логов по заданным критериям.
- Предварительную обработку и агрегацию логов.
- Передачу обработанных логов в AI-сервис для анализа.
'''

import logging
from elasticsearch import Elasticsearch
from datetime import datetime, timedelta

from config.settings import settings
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

class LogAnalysisService:
    def __init__(self):
        try:
            self.es = Elasticsearch(
                hosts=[settings.ELASTICSEARCH_URL],
                # http_auth=('user', 'secret'), # Если требуется аутентификация
            )
            if not self.es.ping():
                raise ConnectionError("Не удалось подключиться к Elasticsearch")
            logger.info("Успешное подключение к Elasticsearch")
        except Exception as e:
            logger.error(f"Ошибка подключения к Elasticsearch: {e}")
            self.es = None

        self.ai_service = AIService()

    def get_logs(self, index: str, minutes_ago: int = 60, query: dict = None) -> list:
        '''
        Получает логи из Elasticsearch за указанный промежуток времени.

        :param index: Индекс Elasticsearch для поиска.
        :param minutes_ago: Временной интервал в минутах для поиска логов.
        :param query: Дополнительные параметры запроса (например, для фильтрации).
        :return: Список записей логов.
        '''
        if not self.es:
            logger.error("Нет подключения к Elasticsearch.")
            return []

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=minutes_ago)

        default_query = {
            "bool": {
                "must": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": start_time.isoformat(),
                                "lte": end_time.isoformat()
                            }
                        }
                    }
                ]
            }
        }

        if query:
            default_query["bool"]["must"].append(query)

        try:
            response = self.es.search(
                index=index,
                body={"query": default_query, "size": 1000} # Ограничиваем количество логов
            )
            return [hit['_source'] for hit in response['hits']['hits']]
        except Exception as e:
            logger.error(f"Ошибка при поиске логов в Elasticsearch: {e}")
            return []

    def analyze_and_generate_playbook(self, service_name: str):
        '''
        Основной метод для анализа логов и генерации плейбука.

        1. Получает логи для указанного сервиса.
        2. Агрегирует и подготавливает их для AI.
        3. Отправляет в AI-сервис для анализа и получения плейбука.
        4. Возвращает сгенерированный плейбук.
        '''
        # Пример: ищем логи с уровнем "error" для конкретного сервиса
        logs = self.get_logs(
            index=f"{service_name}-logs-*", # Пример индекса
            minutes_ago=30,
            query={"match": {"log.level": "error"}}
        )

        if not logs:
            logger.info(f"Не найдено ошибок в логах для сервиса '{service_name}' за последние 30 минут.")
            return None

        # Подготовка контекста для AI
        log_summary = "\n".join([log.get('message', '') for log in logs])
        context = f"Обнаружены следующие ошибки в логах сервиса '{service_name}':\n\n{log_summary}"

        logger.info(f"Отправка {len(logs)} записей логов в AI для анализа...")

        # Генерация плейбука
        playbook = self.ai_service.generate_playbook_from_logs(context, service_name)

        if playbook:
            logger.info(f"AI сгенерировал плейбук для исправления проблемы в '{service_name}'.")
            return playbook
        else:
            logger.warning(f"AI не смог сгенерировать плейбук для '{service_name}'.")
            return None

# Пример использования
if __name__ == '__main__':
    # Этот код выполнится только при прямом запуске файла
    # Требует, чтобы переменные окружения были установлены
    log_analyzer = LogAnalysisService()
    
    # Пример анализа логов для сервиса 'auth-service'
    # В реальном приложении это будет вызываться из API эндпоинта
    playbook_result = log_analyzer.analyze_and_generate_playbook("auth-service")

    if playbook_result:
        print("--- Сгенерированный Плейбук ---")
        print(playbook_result)
    else:
        print("--- Плейбук не был сгенерирован ---")
