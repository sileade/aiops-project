"""
Сервисный модуль для анализа результатов выполнения Ansible плейбуков.
"""

import logging
from app.services.qwen_service import QwenService

logger = logging.getLogger(__name__)

class PostAnalysisService:
    def __init__(self):
        self.ai_service = QwenService()

    def analyze_execution_results(self, playbook_output: str, original_problem: str) -> dict:
        """
        Анализирует вывод Ansible и определяет, была ли решена проблема.

        :param playbook_output: Текстовый вывод выполнения ansible-playbook.
        :param original_problem: Исходное описание проблемы.
        :return: Словарь с результатами анализа.
        """
        prompt = self._create_analysis_prompt(playbook_output, original_problem)

        try:
            logger.info("Запрос на анализ результатов выполнения плейбука...")
            analysis_result = self.ai_service.interpret_command(prompt)

            # Простая обработка ответа от AI
            # В реальном приложении здесь может быть парсинг JSON
            if "SUCCESS" in analysis_result:
                status = "SUCCESS"
            elif "FAILURE" in analysis_result:
                status = "FAILURE"
            else:
                status = "UNCERTAIN"

            return {
                "status": status,
                "reason": analysis_result
            }

        except Exception as e:
            logger.error(f"Ошибка при анализе результатов выполнения: {e}")
            return {
                "status": "ERROR",
                "reason": str(e)
            }

    def _create_analysis_prompt(self, playbook_output: str, original_problem: str) -> str:
        """
        Создает промпт для AI для анализа результатов.
        """
        prompt = f"""
        **Задача:** Проанализируй результат выполнения Ansible плейбука и определи, была ли решена исходная проблема.

        **Исходная Проблема:**
        {original_problem}

        **Вывод Ansible:**
        ```
        {playbook_output}
        ```

        **Проанализируй вывод и ответь ОДНИМ СЛОВОМ, за которым следует краткое объяснение:**
        - **SUCCESS:** если вывод Ansible не содержит ошибок (failed=0, unreachable=0) и выполненные задачи соответствуют решению исходной проблемы.
        - **FAILURE:** если в выводе Ansible есть ошибки (failed > 0 или unreachable > 0).
        - **UNCERTAIN:** если плейбук выполнен без ошибок, но невозможно точно сказать, решена ли проблема (например, если задача была просто перезапустить сервис).

        **Пример ответа:**
        SUCCESS: Плейбук успешно выполнен, правило firewall было удалено.
        """
        return prompt.strip()

# Пример использования
if __name__ == '__main__':
    post_analyzer = PostAnalysisService()

    problem = "Firewall заблокировал порт 443, нужно удалить правило"
    
    # Пример 1: Успешное выполнение
    output_success = """
    PLAY RECAP *********************************************************************
    192.168.1.1              : ok=2    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
    """
    result1 = post_analyzer.analyze_execution_results(output_success, problem)
    print(f"Результат 1: {result1}")

    # Пример 2: Неудачное выполнение
    output_failure = """
    PLAY RECAP *********************************************************************
    192.168.1.1              : ok=1    changed=0    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
    """
    result2 = post_analyzer.analyze_execution_results(output_failure, problem)
    print(f"Результат 2: {result2}")
