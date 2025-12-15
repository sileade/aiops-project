"""
Сервис для взаимодействия с AI моделями.
"""
import aiohttp
import json
from app.utils.logger import logger
from config.settings import settings
from app.models.schemas import LogAnalysisResult, SeverityLevel

async def analyze_logs_with_llm(logs: str) -> LogAnalysisResult:
    """Анализирует логи с помощью LLM, развернутого на LLM_ENDPOINT."""
    logger.info("Отправка логов на анализ в LLM...")
    prompt = f"""Ты — эксперт по анализу логов. Проанализируй следующий фрагмент лога. Твоя задача:
1. Найти ключевые ошибки (ERROR, CRITICAL).
2. Определить наиболее вероятную первопричину.
3. Вернуть результат в формате JSON с полями `summary`, `root_cause`, `severity` (Low, Medium, High, Critical) и `relevant_logs` (список строк).

Лог:
---
{logs}
---
"""
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": 512, "do_sample": False}
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(settings.llm_endpoint, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    # Извлекаем JSON из ответа модели
                    json_response_str = data[0]['generated_text'][len(prompt):].strip()
                    try:
                        result_json = json.loads(json_response_str)
                        logger.info(f"LLM успешно проанализировал логи. Причина: {result_json.get('root_cause')}")
                        return LogAnalysisResult(**result_json)
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка декодирования JSON ответа от LLM: {e}")
                        logger.error(f"Полученная строка: {json_response_str}")
                        raise ValueError("LLM вернул некорректный JSON.")
                else:
                    logger.error(f"Ошибка при обращении к LLM: {response.status} {await response.text()}")
                    raise ConnectionError(f"Ошибка API модели анализа логов: {response.status}")
    except Exception as e:
        logger.error(f"Исключение при вызове LLM: {e}")
        raise

async def generate_remediation_plan(context: str) -> str:
    """Генерирует Ansible плейбук для исправления проблемы."""
    logger.info("Генерация Ansible плейбука с помощью LLM...")
    prompt = f"""Ты — старший DevOps-инженер. На основе предоставленных данных, сгенерируй план исправления в виде Ansible-плейбука. Плейбук должен быть безопасным и включать шаги проверки после выполнения. Верни только YAML-код плейбука.

Контекст:
---
{context}
---
"""
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": 1024, "do_sample": False}
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(settings.llm_endpoint, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    playbook_yaml = data[0]['generated_text'][len(prompt):].strip()
                    # Убираем возможные ```yaml и ``` обертки
                    if playbook_yaml.startswith("```yaml"):
                        playbook_yaml = playbook_yaml[7:]
                    if playbook_yaml.endswith("```"):
                        playbook_yaml = playbook_yaml[:-3]
                    
                    logger.info("LLM успешно сгенерировал плейбук.")
                    return playbook_yaml.strip()
                else:
                    logger.error(f"Ошибка при генерации плейбука: {response.status} {await response.text()}")
                    raise ConnectionError(f"Ошибка API модели генерации плейбуков: {response.status}")
    except Exception as e:
        logger.error(f"Исключение при генерации плейбука: {e}")
        raise
