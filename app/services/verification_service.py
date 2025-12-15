"""
Сервисный модуль для проверки (верификации), было ли исправление успешным.
"""

import logging
import time
from app.services.log_analysis_service import LogAnalysisService # Используем его для повторной проверки логов

logger = logging.getLogger(__name__)

class VerificationService:
    def __init__(self):
        # Мы можем переиспользовать LogAnalysisService для повторной проверки логов
        self.log_analyzer = LogAnalysisService()

    def verify_fix(self, original_log_query: dict, service_name: str) -> bool:
        """
        Проверяет, решена ли проблема, путем повторного запроса логов.

        :param original_log_query: Исходный запрос к Elasticsearch, который обнаружил проблему.
        :param service_name: Имя сервиса (индекс в ES).
        :return: True, если проблема решена, иначе False.
        """
        try:
            logger.info(f"Запуск верификации исправления для сервиса '{service_name}'. Ожидание 60 секунд...")
            # Даем системе время (например, 60 секунд), чтобы новые логи могли появиться, если проблема не решена
            time.sleep(60)

            logger.info("Повторный запрос логов для проверки...")
            # Выполняем тот же самый запрос, который изначально нашел ошибку
            logs_after_fix = self.log_analyzer.get_logs(
                index=f"{service_name}-logs-*",
                minutes_ago=1, # Проверяем только за последнюю минуту
                query=original_log_query
            )

            if not logs_after_fix:
                # Если после исправления нет логов, соответствующих исходной проблеме, считаем, что проблема решена
                logger.info(f"Верификация успешна! Проблема для '{service_name}' решена.")
                return True
            else:
                # Если ошибки все еще появляются, проблема не решена
                logger.warning(f"Верификация не удалась. Проблема для '{service_name}' все еще существует.")
                return False

        except Exception as e:
            logger.error(f"Ошибка во время верификации исправления: {e}")
            return False

# Пример использования
if __name__ == '__main__':
    verifier = VerificationService()

    # Предположим, исходная проблема была обнаружена этим запросом
    test_query = {"match": {"log.level": "error"}}
    test_service = "mikrotik"

    print(f"--- Тестирование верификации для сервиса '{test_service}' ---")
    # В тестовом сценарии мы не можем реально проверить ES, поэтому просто демонстрируем вызов
    # В реальной системе этот вызов будет иметь смысл после применения плейбука
    is_fixed = verifier.verify_fix(test_query, test_service)

    print(f"Проблема решена: {is_fixed}")
    # Ожидаемый результат в тестовом запуске будет зависеть от наличия логов в ES.
    # Скорее всего, будет True, если за последнюю минуту не было ошибок.
