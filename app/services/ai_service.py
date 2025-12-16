"""
Сервис для взаимодействия с AI моделями.

Features:
- Primary: OpenAI-совместимый API
- Fallback: Ollama (локальная LLM)
- Кэширование ответов в Redis
- Circuit Breaker для graceful degradation
"""

import hashlib
import json
import os
from typing import Any

from openai import AsyncOpenAI

from app.models.schemas import LogAnalysisResult, SeverityLevel
from app.services.cache_service import cache
from app.utils.circuit_breaker import (
    CircuitBreakerOpenError,
    ollama_breaker,
    openai_breaker,
)
from app.utils.logger import logger

# ==================== LLM Clients ====================

# Primary: OpenAI client
openai_client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

# Fallback: Ollama client (OpenAI-compatible API)
ollama_client: AsyncOpenAI | None = None
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def _get_ollama_client() -> AsyncOpenAI | None:
    """Lazy initialization of Ollama client."""
    global ollama_client
    if ollama_client is None:
        try:
            ollama_client = AsyncOpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)  # Ollama doesn't need real API key
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama client: {e}")
    return ollama_client


# Default models
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")

# Cache TTLs (seconds)
CACHE_TTL_ANALYSIS = 600  # 10 minutes for log analysis
CACHE_TTL_PLAYBOOK = 1800  # 30 minutes for playbooks
CACHE_TTL_NL = 300  # 5 minutes for NL interpretation


# ==================== Helper Functions ====================


def _clean_json_response(text: str) -> str:
    """Remove markdown wrappers from JSON response."""
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _clean_yaml_response(text: str) -> str:
    """Remove markdown wrappers from YAML response."""
    if text.startswith("```yaml"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def _call_llm_with_fallback(messages: list, temperature: float = 0.1, max_tokens: int = 1024) -> str:
    """
    Call LLM with automatic fallback from OpenAI to Ollama.

    Returns the response text or raises exception if all providers fail.
    """
    last_error = None

    # Try OpenAI first
    try:
        if not openai_breaker.is_open:
            response = await openai_breaker.call(
                openai_client.chat.completions.create,
                model=DEFAULT_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
    except CircuitBreakerOpenError:
        logger.warning("OpenAI circuit breaker is OPEN, trying fallback...")
    except Exception as e:
        last_error = e
        logger.warning(f"OpenAI call failed: {e}, trying Ollama fallback...")

    # Fallback to Ollama
    ollama = _get_ollama_client()
    if ollama:
        try:
            if not ollama_breaker.is_open:
                response = await ollama_breaker.call(
                    ollama.chat.completions.create,
                    model=OLLAMA_MODEL,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                logger.info("Successfully used Ollama fallback")
                return response.choices[0].message.content.strip()
        except CircuitBreakerOpenError:
            logger.error("Both OpenAI and Ollama circuit breakers are OPEN")
        except Exception as e:
            logger.error(f"Ollama fallback also failed: {e}")
            last_error = e

    # All providers failed
    if last_error:
        raise last_error
    raise RuntimeError("All LLM providers unavailable")


# ==================== Main Functions ====================


async def analyze_logs_with_llm(logs: str) -> LogAnalysisResult:
    """
    Анализирует логи с помощью LLM и возвращает структурированный результат.
    Использует кэширование и fallback на Ollama.
    """
    logger.info("Отправка логов на анализ в LLM...")

    # Generate cache key based on logs content
    logs_hash = hashlib.md5(logs.encode()).hexdigest()[:16]
    cache_key = f"aiops:analysis:{logs_hash}"

    # Check cache
    cached = await cache.get(cache_key)
    if cached:
        logger.info("Возвращаем закэшированный результат анализа")
        return LogAnalysisResult(**cached)

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
{logs[:8000]}
---

Верни результат в формате JSON."""

    try:
        response_text = await _call_llm_with_fallback(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1,
            max_tokens=1024,
        )

        response_text = _clean_json_response(response_text)

        try:
            result_json = json.loads(response_text)

            # Map severity to enum
            severity_map = {
                "low": SeverityLevel.LOW,
                "medium": SeverityLevel.MEDIUM,
                "high": SeverityLevel.HIGH,
                "critical": SeverityLevel.CRITICAL,
            }
            severity_str = result_json.get("severity", "medium").lower()
            result_json["severity"] = severity_map.get(severity_str, SeverityLevel.MEDIUM)

            # Cache the result
            cache_data = {
                "summary": result_json.get("summary"),
                "root_cause": result_json.get("root_cause"),
                "severity": result_json["severity"].value,
                "relevant_logs": result_json.get("relevant_logs", []),
            }
            await cache.set(cache_key, cache_data, CACHE_TTL_ANALYSIS)

            logger.info(f"LLM успешно проанализировал логи. Причина: {result_json.get('root_cause')}")
            return LogAnalysisResult(**result_json)

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON ответа от LLM: {e}")
            return LogAnalysisResult(
                summary="Не удалось распарсить ответ AI",
                root_cause="Ошибка парсинга JSON",
                severity=SeverityLevel.MEDIUM,
                relevant_logs=[logs[:500]],
            )

    except Exception as e:
        logger.error(f"Исключение при вызове LLM: {e}")
        # Return degraded response instead of raising
        return LogAnalysisResult(
            summary="AI анализ временно недоступен",
            root_cause=f"Ошибка LLM: {str(e)[:100]}",
            severity=SeverityLevel.MEDIUM,
            relevant_logs=[logs[:500]],
        )


async def generate_remediation_plan(context: str) -> str:
    """
    Генерирует Ansible плейбук для исправления проблемы.
    Использует кэширование и fallback.
    """
    logger.info("Генерация Ansible плейбука с помощью LLM...")

    # Generate cache key
    context_hash = hashlib.md5(context.encode()).hexdigest()[:16]
    cache_key = f"aiops:playbook:{context_hash}"

    # Check cache
    cached = await cache.get(cache_key)
    if cached:
        logger.info("Возвращаем закэшированный плейбук")
        return cached

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
{context[:4000]}
---

Создай плейбук, который:
1. Диагностирует текущее состояние
2. Выполняет исправление
3. Верифицирует результат"""

    try:
        response_text = await _call_llm_with_fallback(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.2,
            max_tokens=2048,
        )

        playbook_yaml = _clean_yaml_response(response_text)

        # Cache the result
        await cache.set(cache_key, playbook_yaml, CACHE_TTL_PLAYBOOK)

        logger.info("LLM успешно сгенерировал плейбук.")
        return playbook_yaml

    except Exception as e:
        logger.error(f"Исключение при генерации плейбука: {e}")
        # Return a basic diagnostic playbook as fallback
        return """---
# Базовый диагностический плейбук (LLM недоступен)
- name: Basic Diagnostic Playbook
  hosts: all
  gather_facts: yes
  tasks:
    - name: Сбор информации о системе
      debug:
        msg: "Hostname: {{ ansible_hostname }}, OS: {{ ansible_distribution }}"

    - name: Проверка дискового пространства
      shell: df -h
      register: disk_space

    - name: Вывод информации о дисках
      debug:
        var: disk_space.stdout_lines
"""


async def interpret_natural_language(query: str) -> dict:
    """
    Интерпретирует команду на естественном языке.
    Использует кэширование для частых команд.
    """
    logger.info(f"Интерпретация команды: {query}")

    # Generate cache key
    query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()[:16]
    cache_key = f"aiops:nl:{query_hash}"

    # Check cache
    cached = await cache.get(cache_key)
    if cached:
        logger.info("Возвращаем закэшированную интерпретацию")
        return cached

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
        response_text = await _call_llm_with_fallback(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
            temperature=0.1,
            max_tokens=256,
        )

        response_text = _clean_json_response(response_text)
        result = json.loads(response_text)

        # Cache the result
        await cache.set(cache_key, result, CACHE_TTL_NL)

        logger.info(f"Интерпретировано: action={result.get('action')}, target={result.get('target')}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга ответа интерпретатора: {e}")
        return {"action": "unknown", "target": None, "parameters": {}}
    except Exception as e:
        logger.error(f"Ошибка интерпретации команды: {e}")
        return {"action": "error", "target": None, "parameters": {"error": str(e)}}


# ==================== Health Check ====================


async def get_llm_status() -> dict[str, Any]:
    """Get status of all LLM providers."""
    return {
        "openai": {
            "circuit_breaker": openai_breaker.get_status(),
            "model": DEFAULT_MODEL,
        },
        "ollama": {
            "circuit_breaker": ollama_breaker.get_status(),
            "model": OLLAMA_MODEL,
            "base_url": OLLAMA_BASE_URL,
        },
        "cache": await cache.health_check(),
    }
