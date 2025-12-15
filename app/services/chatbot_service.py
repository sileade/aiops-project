"""
Сервис для обработки команд от AI чат-бота.
"""
from app.services import qwen_service, system_service, analysis_service, automation_service
from app.utils.logger import logger

async def process_natural_language_command(query: str) -> str:
    """Обрабатывает команду на естественном языке."""
    try:
        # Шаг 1: Интерпретация команды
        command_json = await qwen_service.interpret_command(query)
        action = command_json.get("action")
        target = command_json.get("target")
        parameters = command_json.get("parameters", {})

        # Шаг 2: Выполнение команды
        if action == "get_status":
            if target == "system":
                status = await system_service.get_full_system_status()
                return f"Статус системы:\n- API: {status.api_status}\n- Elasticsearch: {status.elasticsearch_status}\n- Prometheus: {status.prometheus_status}\n- Redis: {status.redis_status}"
            else:
                # Логика для получения статуса конкретного сервиса
                return f"Статус для сервиса ‘{target}’ пока не реализован."

        elif action == "analyze_service":
            await analysis_service.trigger_full_analysis(target, parameters.get("time_window", "15m"))
            return f"Анализ для сервиса ‘{target}’ запущен."

        elif action == "run_playbook":
            playbook_name = parameters.get("playbook_name")
            # Здесь нужна логика для создания и выполнения плана
            # Для простоты, пока просто возвращаем сообщение
            return f"Запуск плейбука ‘{playbook_name}’ для ‘{target}’ пока не реализован."

        elif action == "get_logs":
            # Логика для получения логов
            return f"Получение логов для ‘{target}’ пока не реализовано."

        else:
            return f"Неизвестное действие: {action}"

    except Exception as e:
        logger.error(f"Ошибка при обработке команды ‘{query}’: {e}")
        return f"Произошла ошибка при обработке вашей команды: {e}"
