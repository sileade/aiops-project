"""
Сервис для взаимодействия с моделью Qwen для интерпретации команд.
"""

import json

import aiohttp

from app.utils.logger import logger
from config.settings import settings


async def interpret_command(query: str) -> dict:
    """
    Интерпретирует команду на естественном языке в структурированную JSON-команду
    с помощью модели Qwen/Qwen2.5-32B-Instruct.
    """
    logger.info(f"Интерпретация команды через Qwen: '{query}'")

    prompt = f"""Ты — AI-ассистент для управления IT-инфраструктурой. Твоя задача — преобразовать запрос пользователя на естественном языке в структурированную JSON-команду. Не добавляй никаких объяснений, верни только JSON.

Доступные команды (поле "action"):
- `get_status`: Получить статус системы или конкретного сервиса.
- `analyze_service`: Запустить анализ для сервиса.
- `run_playbook`: Запустить Ansible плейбук (например, для перезапуска сервиса).
- `get_logs`: Получить логи для сервиса.

Поле "target" должно содержать имя сервиса или "system" для общих команд.
Поле "parameters" может содержать дополнительные параметры, например, `time_window` для логов или `playbook_name` для `run_playbook`.

Примеры:
- "покажи статус системы" -> {{"action": "get_status", "target": "system", "parameters": {{}}}}
- "проанализируй сервис auth-service" -> {{"action": "analyze_service", "target": "auth-service", "parameters": {{}}}}
- "покажи логи сервиса payment-gateway за последний час" -> {{"action": "get_logs", "target": "payment-gateway", "parameters": {{"time_window": "1h"}}}}
- "перезапусти nginx" -> {{"action": "run_playbook", "target": "nginx", "parameters": {{"playbook_name": "restart_nginx.yml"}}}}

Верни ТОЛЬКО JSON-объект.

Запрос пользователя: "{query}"
"""

    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 256, "do_sample": False}}

    # Используем тот же эндпоинт, что и для других LLM, предполагая, что там развернута нужная модель
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(settings.llm_endpoint, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    json_response_str = data[0]["generated_text"][len(prompt) :].strip()
                    try:
                        # Очистка от возможных артефактов
                        if json_response_str.startswith("```json"):
                            json_response_str = json_response_str[7:]
                        if json_response_str.endswith("```"):
                            json_response_str = json_response_str[:-3]

                        result_json = json.loads(json_response_str.strip())
                        logger.info(f"Qwen успешно интерпретировал команду: {result_json}")
                        return result_json
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка декодирования JSON от Qwen: {e}")
                        logger.error(f"Полученная строка: {json_response_str}")
                        raise ValueError("Qwen вернул некорректный JSON.")
                else:
                    logger.error(f"Ошибка при обращении к Qwen: {response.status} {await response.text()}")
                    raise ConnectionError(f"Ошибка API модели Qwen: {response.status}")
    except Exception as e:
        logger.error(f"Исключение при вызове Qwen: {e}")
        raise
