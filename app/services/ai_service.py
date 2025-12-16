"""
Сервис для взаимодействия с AI моделями через OpenAI-совместимый API.
Поддерживает анализ логов и генерацию Ansible плейбуков.
"""
import json
import os
from openai import AsyncOpenAI
from app.utils.logger import logger
from config.settings import settings
from app.models.schemas import LogAnalysisResult, SeverityLevel


# Инициализация клиента OpenAI (API ключ и base_url берутся из переменных окружения)
client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

# Модель по умолчанию (можно переопределить через settings)
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")


async def analyze_logs_with_llm(logs: str) -> LogAnalysisResult:
    """
    Анализирует логи с помощью LLM и возвращает структурированный результат.
    
    Args:
        logs: Строка с логами для анализа
        
    Returns:
        LogAnalysisResult с summary, root_cause, severity и relevant_logs
    """
    logger.info("Отправка логов на анализ в LLM...")
    
    system_prompt = """Ты — эксперт по анализу логов IT-инфраструктуры. Твоя задача — проанализировать предоставленные логи и выявить проблемы.

Ты ДОЛЖЕН вернуть ответ ТОЛЬКО в формате JSON без дополнительного текста:
{
    "summary": "Краткое описание найденной проблемы",
    "root_cause": "Наиболее вероятная первопричина проблемы",
    "severity": "Low|Medium|High|Critical",
    "relevant_logs": ["строка лога 1", "строка лога 2"]
}

Правила определения severity:
- Critical: Сервис полностью недоступен, потеря данных
- High: Серьезные ошибки, влияющие на работу пользователей
- Medium: Предупреждения, потенциальные проблемы
- Low: Информационные сообщения, незначительные ошибки"""

    user_prompt = f"""Проанализируй следующие логи и определи проблему:

---
{logs}
---

Верни результат в формате JSON."""

    try:
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=1024
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Очищаем от возможных markdown-оберток
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        try:
            result_json = json.loads(response_text)
            
            # Преобразуем severity в enum
            severity_map = {
                "low": SeverityLevel.LOW,
                "medium": SeverityLevel.MEDIUM,
                "high": SeverityLevel.HIGH,
                "critical": SeverityLevel.CRITICAL
            }
            severity_str = result_json.get("severity", "medium").lower()
            result_json["severity"] = severity_map.get(severity_str, SeverityLevel.MEDIUM)
            
            logger.info(f"LLM успешно проанализировал логи. Причина: {result_json.get('root_cause')}")
            return LogAnalysisResult(**result_json)
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON ответа от LLM: {e}")
            logger.error(f"Полученная строка: {response_text}")
            # Возвращаем базовый результат при ошибке парсинга
            return LogAnalysisResult(
                summary="Не удалось распарсить ответ AI",
                root_cause="Ошибка парсинга JSON",
                severity=SeverityLevel.MEDIUM,
                relevant_logs=[logs[:500]]
            )
            
    except Exception as e:
        logger.error(f"Исключение при вызове LLM: {e}")
        raise


async def generate_remediation_plan(context: str) -> str:
    """
    Генерирует Ansible плейбук для исправления проблемы.
    
    Args:
        context: Описание проблемы и контекст для генерации плейбука
        
    Returns:
        YAML-строка с Ansible плейбуком
    """
    logger.info("Генерация Ansible плейбука с помощью LLM...")
    
    system_prompt = """Ты — старший DevOps-инженер с опытом работы с Ansible. 
Твоя задача — создавать безопасные и эффективные Ansible плейбуки для исправления проблем в IT-инфраструктуре.

Правила:
1. Плейбук должен быть идемпотентным
2. Включай проверки перед выполнением опасных операций
3. Добавляй шаги верификации после исправления
4. Используй become: yes только когда необходимо
5. Добавляй комментарии на русском языке

Верни ТОЛЬКО YAML-код плейбука без дополнительного текста и markdown-оберток."""

    user_prompt = f"""На основе следующего контекста создай Ansible плейбук для исправления проблемы:

---
{context}
---

Создай плейбук, который:
1. Диагностирует текущее состояние
2. Выполняет исправление
3. Верифицирует результат"""

    try:
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=2048
        )
        
        playbook_yaml = response.choices[0].message.content.strip()
        
        # Убираем возможные markdown-обертки
        if playbook_yaml.startswith("```yaml"):
            playbook_yaml = playbook_yaml[7:]
        if playbook_yaml.startswith("```"):
            playbook_yaml = playbook_yaml[3:]
        if playbook_yaml.endswith("```"):
            playbook_yaml = playbook_yaml[:-3]
        
        logger.info("LLM успешно сгенерировал плейбук.")
        return playbook_yaml.strip()
        
    except Exception as e:
        logger.error(f"Исключение при генерации плейбука: {e}")
        raise


async def interpret_natural_language(query: str) -> dict:
    """
    Интерпретирует команду на естественном языке и возвращает структурированное действие.
    
    Args:
        query: Команда пользователя на естественном языке
        
    Returns:
        dict с полями action, target, parameters
    """
    logger.info(f"Интерпретация команды: {query}")
    
    system_prompt = """Ты — интерпретатор команд для AIOps системы. 
Твоя задача — преобразовать команду пользователя на естественном языке в структурированное действие.

Доступные действия:
- get_status: Получить статус (target: "system" или имя сервиса)
- analyze_service: Запустить анализ сервиса (target: имя сервиса)
- run_playbook: Запустить плейбук (target: имя сервиса, parameters.playbook_name: имя плейбука)
- get_logs: Получить логи (target: имя сервиса, parameters.time_window: период)
- restart_service: Перезапустить сервис (target: имя сервиса)
- list_vms: Список виртуальных машин
- vm_action: Действие с VM (target: vmid, parameters.action: start|stop|reboot)

Верни ТОЛЬКО JSON без дополнительного текста:
{
    "action": "название_действия",
    "target": "цель_действия",
    "parameters": {}
}"""

    try:
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            temperature=0.1,
            max_tokens=256
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Очищаем от markdown
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        
        result = json.loads(response_text.strip())
        logger.info(f"Интерпретировано: action={result.get('action')}, target={result.get('target')}")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга ответа интерпретатора: {e}")
        return {"action": "unknown", "target": None, "parameters": {}}
    except Exception as e:
        logger.error(f"Ошибка интерпретации команды: {e}")
        raise
