#!/usr/bin/env python3
"""
Тестовый сценарий для демонстрации:
1. Fallback на Ollama при недоступности OpenAI
2. Кэширование ответов в Redis
3. Circuit Breaker паттерн

Запуск: python tests/test_resilience_demo.py
"""

import asyncio
import sys
import os
import time
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==================== Console Colors ====================


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_step(step: int, text: str):
    print(f"{Colors.CYAN}[Шаг {step}]{Colors.ENDC} {text}")


def print_success(text: str):
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")


def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")


def print_error(text: str):
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")


def print_info(text: str):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")


# ==================== Mock Classes ====================


class MockRedisCache:
    """Mock Redis для демонстрации кэширования."""

    def __init__(self):
        self._cache = {}
        self._hits = 0
        self._misses = 0

    async def get(self, key: str):
        if key in self._cache:
            self._hits += 1
            print_info(f"Cache HIT: {key[:50]}...")
            return self._cache[key]
        self._misses += 1
        print_info(f"Cache MISS: {key[:50]}...")
        return None

    async def set(self, key: str, value, ttl: int = 600):
        self._cache[key] = value
        print_info(f"Cache SET: {key[:50]}... (TTL: {ttl}s)")

    async def health_check(self):
        return {"status": "healthy", "hits": self._hits, "misses": self._misses}

    def get_stats(self):
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / max(1, self._hits + self._misses)) * 100:.1f}%",
            "cached_keys": len(self._cache),
        }


class MockCircuitBreaker:
    """Mock Circuit Breaker для демонстрации."""

    def __init__(self, name: str, failure_threshold: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_failure_time = None

    @property
    def is_open(self):
        return self.state == "OPEN"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            print_warning(f"Circuit Breaker '{self.name}' ОТКРЫТ после {self.failure_count} ошибок")

    def record_success(self):
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            print_success(f"Circuit Breaker '{self.name}' ЗАКРЫТ")

    def get_status(self):
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failure_count,
            "threshold": self.failure_threshold,
        }


# ==================== Test Scenarios ====================


async def scenario_1_openai_available():
    """Сценарий 1: OpenAI доступен - используем основной провайдер."""
    print_header("Сценарий 1: OpenAI доступен")

    cache = MockRedisCache()
    openai_cb = MockCircuitBreaker("openai", failure_threshold=3)
    ollama_cb = MockCircuitBreaker("ollama", failure_threshold=5)

    logs_sample = """
    2024-01-15 10:23:45 ERROR [api-gateway] Connection refused to backend service
    2024-01-15 10:23:46 ERROR [api-gateway] Retry attempt 1 failed
    2024-01-15 10:23:47 ERROR [api-gateway] Circuit breaker opened for backend
    """

    print_step(1, "Получен запрос на анализ логов")
    print(f"   Логи: {logs_sample[:100]}...")

    print_step(2, "Проверяем кэш...")
    cached = await cache.get("aiops:analysis:abc123")

    if not cached:
        print_step(3, "Кэш пуст, вызываем OpenAI API...")

        # Симуляция успешного вызова OpenAI
        if not openai_cb.is_open:
            print_info("OpenAI Circuit Breaker: CLOSED - вызов разрешен")
            await asyncio.sleep(0.5)  # Симуляция задержки API

            # Успешный ответ
            result = {
                "summary": "Сервис api-gateway не может подключиться к backend",
                "root_cause": "Backend сервис недоступен или перегружен",
                "severity": "high",
                "relevant_logs": ["Connection refused", "Circuit breaker opened"],
            }

            openai_cb.record_success()
            print_success("OpenAI вернул ответ")

            print_step(4, "Сохраняем результат в кэш...")
            await cache.set("aiops:analysis:abc123", result, ttl=600)

    print_step(5, "Результат анализа:")
    print(
        f"""
   {Colors.GREEN}📊 Summary:{Colors.ENDC} {result['summary']}
   {Colors.GREEN}🔍 Root Cause:{Colors.ENDC} {result['root_cause']}
   {Colors.GREEN}⚠️  Severity:{Colors.ENDC} {result['severity']}
    """
    )

    return cache, openai_cb


async def scenario_2_cache_hit():
    """Сценарий 2: Повторный запрос - данные из кэша."""
    print_header("Сценарий 2: Повторный запрос (Cache Hit)")

    # Используем кэш из предыдущего сценария
    cache = MockRedisCache()

    # Предзаполняем кэш
    cached_result = {
        "summary": "Сервис api-gateway не может подключиться к backend",
        "root_cause": "Backend сервис недоступен или перегружен",
        "severity": "high",
    }
    await cache.set("aiops:analysis:abc123", cached_result, ttl=600)
    cache._hits = 0  # Сбрасываем счетчик

    print_step(1, "Получен повторный запрос на анализ тех же логов")

    print_step(2, "Проверяем кэш...")
    cached = await cache.get("aiops:analysis:abc123")

    if cached:
        print_success("Данные найдены в кэше!")
        print_info("OpenAI API НЕ вызывается - экономим время и деньги")

        print_step(3, "Результат из кэша:")
        print(
            f"""
   {Colors.GREEN}📊 Summary:{Colors.ENDC} {cached['summary']}
   {Colors.GREEN}🔍 Root Cause:{Colors.ENDC} {cached['root_cause']}
   {Colors.GREEN}⚠️  Severity:{Colors.ENDC} {cached['severity']}
        """
        )

    print_step(4, "Статистика кэша:")
    stats = cache.get_stats()
    print(f"   Hits: {stats['hits']}, Misses: {stats['misses']}, Hit Rate: {stats['hit_rate']}")

    return cache


async def scenario_3_openai_fails_fallback_ollama():
    """Сценарий 3: OpenAI недоступен - fallback на Ollama."""
    print_header("Сценарий 3: OpenAI недоступен → Fallback на Ollama")

    cache = MockRedisCache()
    openai_cb = MockCircuitBreaker("openai", failure_threshold=3)
    ollama_cb = MockCircuitBreaker("ollama", failure_threshold=5)

    logs_sample = """
    2024-01-15 11:00:00 CRITICAL [database] Connection pool exhausted
    2024-01-15 11:00:01 ERROR [database] Query timeout after 30s
    """

    print_step(1, "Получен запрос на анализ новых логов")
    print(f"   Логи: {logs_sample[:80]}...")

    print_step(2, "Проверяем кэш...")
    cached = await cache.get("aiops:analysis:def456")

    print_step(3, "Пытаемся вызвать OpenAI API...")

    # Симуляция 3 неудачных попыток OpenAI
    for attempt in range(1, 4):
        print_error(f"OpenAI попытка {attempt}: Connection timeout")
        openai_cb.record_failure()
        await asyncio.sleep(0.2)

    print_step(4, "OpenAI Circuit Breaker открыт, переключаемся на Ollama...")
    print_info(f"OpenAI CB Status: {openai_cb.get_status()}")

    # Fallback на Ollama
    if not ollama_cb.is_open:
        print_info("Ollama Circuit Breaker: CLOSED - вызов разрешен")
        print_info("Вызываем локальную LLM (Ollama)...")
        await asyncio.sleep(0.8)  # Ollama может быть медленнее

        result = {
            "summary": "Исчерпан пул соединений с базой данных",
            "root_cause": "Слишком много активных соединений или утечка соединений",
            "severity": "critical",
            "provider": "ollama",  # Помечаем источник
        }

        ollama_cb.record_success()
        print_success("Ollama вернул ответ (fallback успешен)")

        print_step(5, "Сохраняем результат в кэш...")
        await cache.set("aiops:analysis:def456", result, ttl=600)

    print_step(6, "Результат анализа (от Ollama):")
    print(
        f"""
   {Colors.GREEN}📊 Summary:{Colors.ENDC} {result['summary']}
   {Colors.GREEN}🔍 Root Cause:{Colors.ENDC} {result['root_cause']}
   {Colors.GREEN}⚠️  Severity:{Colors.ENDC} {result['severity']}
   {Colors.YELLOW}🤖 Provider:{Colors.ENDC} {result['provider']}
    """
    )

    return openai_cb, ollama_cb


async def scenario_4_both_llm_fail():
    """Сценарий 4: Оба LLM недоступны - graceful degradation."""
    print_header("Сценарий 4: Оба LLM недоступны → Graceful Degradation")

    openai_cb = MockCircuitBreaker("openai", failure_threshold=3)
    ollama_cb = MockCircuitBreaker("ollama", failure_threshold=3)

    # Открываем оба circuit breaker
    for _ in range(3):
        openai_cb.record_failure()
        ollama_cb.record_failure()

    print_step(1, "Получен запрос на анализ")

    print_step(2, "Проверяем OpenAI Circuit Breaker...")
    print_warning(f"OpenAI CB: {openai_cb.get_status()['state']} - вызов заблокирован")

    print_step(3, "Проверяем Ollama Circuit Breaker...")
    print_warning(f"Ollama CB: {ollama_cb.get_status()['state']} - вызов заблокирован")

    print_step(4, "Оба LLM недоступны, возвращаем degraded response...")

    degraded_result = {
        "summary": "AI анализ временно недоступен",
        "root_cause": "Все LLM провайдеры недоступны",
        "severity": "medium",
        "degraded": True,
        "recommendation": "Проверьте логи вручную или дождитесь восстановления сервисов",
    }

    print_step(5, "Degraded Response:")
    print(
        f"""
   {Colors.YELLOW}📊 Summary:{Colors.ENDC} {degraded_result['summary']}
   {Colors.YELLOW}🔍 Root Cause:{Colors.ENDC} {degraded_result['root_cause']}
   {Colors.YELLOW}💡 Recommendation:{Colors.ENDC} {degraded_result['recommendation']}
    """
    )

    print_info("Система продолжает работать в ограниченном режиме")
    print_info("Базовые функции (сбор логов, метрик) остаются доступными")

    return degraded_result


async def scenario_5_circuit_breaker_recovery():
    """Сценарий 5: Восстановление Circuit Breaker."""
    print_header("Сценарий 5: Восстановление Circuit Breaker")

    openai_cb = MockCircuitBreaker("openai", failure_threshold=3)

    # Открываем circuit breaker
    for _ in range(3):
        openai_cb.record_failure()

    print_step(1, f"Начальное состояние: {openai_cb.get_status()['state']}")

    print_step(2, "Ожидаем timeout (обычно 60 секунд)...")
    print_info("В демо пропускаем ожидание...")

    # Симуляция перехода в HALF_OPEN
    openai_cb.state = "HALF_OPEN"
    openai_cb.failure_count = 0
    print_step(3, f"Состояние после timeout: {openai_cb.state}")

    print_step(4, "Пробный запрос к OpenAI...")
    await asyncio.sleep(0.3)

    # Успешный запрос
    print_success("OpenAI вернул успешный ответ")
    openai_cb.record_success()

    print_step(5, f"Финальное состояние: {openai_cb.get_status()['state']}")
    print_success("Circuit Breaker восстановлен, система работает в нормальном режиме")


async def run_all_scenarios():
    """Запуск всех сценариев."""
    print(
        f"""
{Colors.BOLD}{Colors.CYAN}
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   AIOps Resilience Demo: Fallback & Caching                  ║
║                                                              ║
║   Демонстрация отказоустойчивости системы:                   ║
║   • Circuit Breaker для защиты от каскадных сбоев            ║
║   • Fallback на Ollama при недоступности OpenAI              ║
║   • Redis кэширование для экономии ресурсов                  ║
║   • Graceful degradation при полном отказе LLM               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
{Colors.ENDC}
    """
    )

    input(f"{Colors.YELLOW}Нажмите Enter для запуска сценария 1...{Colors.ENDC}")
    await scenario_1_openai_available()

    input(f"\n{Colors.YELLOW}Нажмите Enter для запуска сценария 2...{Colors.ENDC}")
    await scenario_2_cache_hit()

    input(f"\n{Colors.YELLOW}Нажмите Enter для запуска сценария 3...{Colors.ENDC}")
    await scenario_3_openai_fails_fallback_ollama()

    input(f"\n{Colors.YELLOW}Нажмите Enter для запуска сценария 4...{Colors.ENDC}")
    await scenario_4_both_llm_fail()

    input(f"\n{Colors.YELLOW}Нажмите Enter для запуска сценария 5...{Colors.ENDC}")
    await scenario_5_circuit_breaker_recovery()

    print_header("Демонстрация завершена")
    print(
        f"""
{Colors.GREEN}Итоги демонстрации:{Colors.ENDC}

1. {Colors.GREEN}✅{Colors.ENDC} Circuit Breaker защищает от каскадных сбоев
2. {Colors.GREEN}✅{Colors.ENDC} Fallback на Ollama обеспечивает непрерывность работы
3. {Colors.GREEN}✅{Colors.ENDC} Redis кэширование экономит время и деньги
4. {Colors.GREEN}✅{Colors.ENDC} Graceful degradation при полном отказе LLM
5. {Colors.GREEN}✅{Colors.ENDC} Автоматическое восстановление после сбоев

{Colors.CYAN}Конфигурация в .env:{Colors.ENDC}
  ENABLE_LLM_FALLBACK=true
  ENABLE_CACHING=true
  OLLAMA_BASE_URL=http://ollama:11434/v1
  CACHE_TTL_ANALYSIS=600
    """
    )


async def run_non_interactive():
    """Запуск без интерактивного режима."""
    print(
        f"""
{Colors.BOLD}{Colors.CYAN}
╔══════════════════════════════════════════════════════════════╗
║   AIOps Resilience Demo (Non-Interactive Mode)               ║
╚══════════════════════════════════════════════════════════════╝
{Colors.ENDC}
    """
    )

    await scenario_1_openai_available()
    await asyncio.sleep(0.5)

    await scenario_2_cache_hit()
    await asyncio.sleep(0.5)

    await scenario_3_openai_fails_fallback_ollama()
    await asyncio.sleep(0.5)

    await scenario_4_both_llm_fail()
    await asyncio.sleep(0.5)

    await scenario_5_circuit_breaker_recovery()

    print_header("Демонстрация завершена")


if __name__ == "__main__":
    # Проверяем режим запуска
    if "--non-interactive" in sys.argv or "-n" in sys.argv:
        asyncio.run(run_non_interactive())
    else:
        try:
            asyncio.run(run_all_scenarios())
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Демонстрация прервана пользователем{Colors.ENDC}")
