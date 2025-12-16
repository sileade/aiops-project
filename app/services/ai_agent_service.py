"""
AI Agent Service - Интеллектуальный агент для понимания естественной речи.

Этот сервис обрабатывает сообщения пользователей на естественном языке,
определяет намерения (intents) и извлекает параметры для выполнения действий.
"""

import json
import re
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

from app.services.ai_service import AIService
from app.services.cache_service import CacheService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Intent(Enum):
    """Поддерживаемые намерения пользователя."""
    
    # Мониторинг и статус
    CHECK_STATUS = "check_status"
    CHECK_HEALTH = "check_health"
    GET_METRICS = "get_metrics"
    
    # Анализ и диагностика
    ANALYZE_LOGS = "analyze_logs"
    FIND_ERRORS = "find_errors"
    DIAGNOSE_PROBLEM = "diagnose_problem"
    
    # Управление сервисами
    RESTART_SERVICE = "restart_service"
    STOP_SERVICE = "stop_service"
    START_SERVICE = "start_service"
    
    # Управление VM (Proxmox)
    LIST_VMS = "list_vms"
    VM_STATUS = "vm_status"
    RESTART_VM = "restart_vm"
    
    # Сеть (MikroTik)
    CHECK_NETWORK = "check_network"
    LIST_CONNECTIONS = "list_connections"
    BLOCK_IP = "block_ip"
    
    # Автоматизация
    RUN_PLAYBOOK = "run_playbook"
    CREATE_BACKUP = "create_backup"
    
    # Отчеты
    GENERATE_REPORT = "generate_report"
    GET_ALERTS = "get_alerts"
    
    # Помощь
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class ParsedIntent:
    """Результат парсинга намерения пользователя."""
    
    intent: Intent
    confidence: float
    parameters: dict = field(default_factory=dict)
    original_message: str = ""
    suggested_response: str = ""
    requires_confirmation: bool = False
    
    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "parameters": self.parameters,
            "original_message": self.original_message,
            "suggested_response": self.suggested_response,
            "requires_confirmation": self.requires_confirmation
        }


class AIAgentService:
    """
    AI-агент для обработки естественной речи.
    
    Использует LLM для понимания намерений пользователя и извлечения
    параметров из сообщений на естественном языке.
    """
    
    # Примеры для few-shot learning
    INTENT_EXAMPLES = """
Примеры сообщений и их интерпретация:

"Покажи статус серверов" -> intent: check_status, params: {}
"Что с сервером web-01?" -> intent: check_health, params: {target: "web-01"}
"Перезапусти nginx" -> intent: restart_service, params: {service: "nginx"}
"Проанализируй логи за последний час" -> intent: analyze_logs, params: {timeframe: "1h"}
"Найди ошибки в логах" -> intent: find_errors, params: {}
"Почему сайт тормозит?" -> intent: diagnose_problem, params: {symptom: "slow website"}
"Список виртуалок" -> intent: list_vms, params: {}
"Перезагрузи VM с ID 100" -> intent: restart_vm, params: {vm_id: "100"}
"Проверь сеть" -> intent: check_network, params: {}
"Заблокируй IP 192.168.1.100" -> intent: block_ip, params: {ip: "192.168.1.100"}
"Запусти плейбук деплоя" -> intent: run_playbook, params: {playbook: "deploy"}
"Сделай бэкап базы данных" -> intent: create_backup, params: {target: "database"}
"Сгенерируй отчет за неделю" -> intent: generate_report, params: {period: "week"}
"Покажи алерты" -> intent: get_alerts, params: {}
"Помощь" -> intent: help, params: {}
"""

    SYSTEM_PROMPT = """Ты - AI-ассистент для управления IT-инфраструктурой.
Твоя задача - понять намерение пользователя и извлечь параметры из сообщения.

Доступные намерения (intents):
- check_status: проверка общего статуса системы
- check_health: проверка здоровья конкретного сервиса/сервера
- get_metrics: получение метрик
- analyze_logs: анализ логов
- find_errors: поиск ошибок в логах
- diagnose_problem: диагностика проблемы
- restart_service: перезапуск сервиса
- stop_service: остановка сервиса
- start_service: запуск сервиса
- list_vms: список виртуальных машин
- vm_status: статус конкретной VM
- restart_vm: перезапуск VM
- check_network: проверка сети
- list_connections: список соединений
- block_ip: блокировка IP адреса
- run_playbook: запуск Ansible плейбука
- create_backup: создание резервной копии
- generate_report: генерация отчета
- get_alerts: получение алертов
- help: справка
- unknown: неизвестное намерение

{examples}

Ответь в формате JSON:
{{
    "intent": "название_намерения",
    "confidence": 0.0-1.0,
    "parameters": {{}},
    "suggested_response": "предложенный ответ пользователю",
    "requires_confirmation": true/false (для опасных операций)
}}

Опасные операции (requires_confirmation=true): restart_service, stop_service, restart_vm, block_ip, run_playbook
"""

    def __init__(self):
        self.ai_service = AIService()
        self.cache_service = CacheService()
        
        # Паттерны для быстрого определения намерений без LLM
        self.quick_patterns = {
            Intent.CHECK_STATUS: [
                r"статус", r"status", r"как дела", r"что происходит"
            ],
            Intent.HELP: [
                r"помощь", r"help", r"помоги", r"что умеешь", r"команды"
            ],
            Intent.GET_ALERTS: [
                r"алерт", r"alert", r"тревог", r"предупрежд"
            ],
            Intent.ANALYZE_LOGS: [
                r"анализ.*лог", r"проанализируй.*лог", r"analyze.*log"
            ],
            Intent.FIND_ERRORS: [
                r"найди.*ошибк", r"поиск.*ошибок", r"find.*error", r"ошибки"
            ],
            Intent.LIST_VMS: [
                r"список.*vm", r"виртуалк", r"list.*vm", r"вм"
            ],
            Intent.CHECK_NETWORK: [
                r"сеть", r"network", r"пинг", r"ping", r"связь"
            ],
            Intent.RESTART_SERVICE: [
                r"перезапусти", r"restart", r"рестарт"
            ],
        }
    
    async def parse_message(self, message: str, context: Optional[dict] = None) -> ParsedIntent:
        """
        Парсит сообщение пользователя и определяет намерение.
        
        Args:
            message: Сообщение пользователя
            context: Дополнительный контекст (история диалога и т.д.)
            
        Returns:
            ParsedIntent с определенным намерением и параметрами
        """
        message = message.strip()
        
        if not message:
            return ParsedIntent(
                intent=Intent.UNKNOWN,
                confidence=1.0,
                original_message=message,
                suggested_response="Пожалуйста, введите сообщение."
            )
        
        # Попробуем быстрое определение по паттернам
        quick_result = self._quick_pattern_match(message)
        if quick_result and quick_result.confidence > 0.8:
            logger.info(f"Quick pattern match: {quick_result.intent.value}")
            return quick_result
        
        # Проверяем кэш
        cache_key = f"intent:{hash(message.lower())}"
        cached = await self.cache_service.get(cache_key)
        if cached:
            logger.info(f"Cache hit for intent parsing")
            return self._dict_to_parsed_intent(cached, message)
        
        # Используем LLM для понимания намерения
        try:
            result = await self._parse_with_llm(message, context)
            
            # Кэшируем результат
            await self.cache_service.set(cache_key, result.to_dict(), ttl=1800)
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing message with LLM: {e}")
            # Fallback на быстрое определение
            return quick_result or ParsedIntent(
                intent=Intent.UNKNOWN,
                confidence=0.5,
                original_message=message,
                suggested_response="Извините, не удалось понять ваш запрос. Попробуйте переформулировать или введите /help для справки."
            )
    
    def _quick_pattern_match(self, message: str) -> Optional[ParsedIntent]:
        """Быстрое определение намерения по паттернам."""
        message_lower = message.lower()
        
        for intent, patterns in self.quick_patterns.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    # Извлекаем параметры
                    params = self._extract_quick_params(message, intent)
                    
                    return ParsedIntent(
                        intent=intent,
                        confidence=0.85,
                        parameters=params,
                        original_message=message,
                        suggested_response=self._get_quick_response(intent, params),
                        requires_confirmation=intent in [
                            Intent.RESTART_SERVICE, 
                            Intent.RESTART_VM,
                            Intent.BLOCK_IP
                        ]
                    )
        
        return None
    
    def _extract_quick_params(self, message: str, intent: Intent) -> dict:
        """Извлекает параметры из сообщения для быстрого парсинга."""
        params = {}
        
        # IP адреса
        ip_match = re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', message)
        if ip_match:
            params["ip"] = ip_match.group(1)
        
        # VM ID
        vm_match = re.search(r'\b(?:vm|вм|id)\s*[:#]?\s*(\d+)\b', message.lower())
        if vm_match:
            params["vm_id"] = vm_match.group(1)
        
        # Имена сервисов
        services = ["nginx", "apache", "mysql", "postgres", "redis", "docker", "api", "bot"]
        for service in services:
            if service in message.lower():
                params["service"] = service
                break
        
        # Временные периоды
        time_patterns = {
            r"(\d+)\s*(?:час|hour|h)": ("timeframe", lambda m: f"{m.group(1)}h"),
            r"(\d+)\s*(?:мин|min|m)": ("timeframe", lambda m: f"{m.group(1)}m"),
            r"(\d+)\s*(?:день|day|d)": ("timeframe", lambda m: f"{m.group(1)}d"),
            r"недел|week": ("period", lambda m: "week"),
            r"месяц|month": ("period", lambda m: "month"),
        }
        
        for pattern, (key, extractor) in time_patterns.items():
            match = re.search(pattern, message.lower())
            if match:
                params[key] = extractor(match)
                break
        
        return params
    
    def _get_quick_response(self, intent: Intent, params: dict) -> str:
        """Генерирует быстрый ответ для известного намерения."""
        responses = {
            Intent.CHECK_STATUS: "Проверяю статус системы...",
            Intent.HELP: "Показываю справку по командам...",
            Intent.GET_ALERTS: "Получаю список активных алертов...",
            Intent.ANALYZE_LOGS: f"Анализирую логи{' за ' + params.get('timeframe', '') if params.get('timeframe') else ''}...",
            Intent.FIND_ERRORS: "Ищу ошибки в логах...",
            Intent.LIST_VMS: "Получаю список виртуальных машин...",
            Intent.CHECK_NETWORK: "Проверяю состояние сети...",
            Intent.RESTART_SERVICE: f"Перезапустить сервис {params.get('service', 'указанный')}?",
        }
        
        return responses.get(intent, "Обрабатываю запрос...")
    
    async def _parse_with_llm(self, message: str, context: Optional[dict] = None) -> ParsedIntent:
        """Парсит сообщение с помощью LLM."""
        
        prompt = f"""Сообщение пользователя: "{message}"

{f"Контекст диалога: {json.dumps(context, ensure_ascii=False)}" if context else ""}

Определи намерение пользователя и извлеки параметры."""

        system_prompt = self.SYSTEM_PROMPT.format(examples=self.INTENT_EXAMPLES)
        
        response = await self.ai_service.generate_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=500
        )
        
        # Парсим JSON ответ
        try:
            # Извлекаем JSON из ответа
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                
                intent_str = data.get("intent", "unknown")
                try:
                    intent = Intent(intent_str)
                except ValueError:
                    intent = Intent.UNKNOWN
                
                return ParsedIntent(
                    intent=intent,
                    confidence=float(data.get("confidence", 0.7)),
                    parameters=data.get("parameters", {}),
                    original_message=message,
                    suggested_response=data.get("suggested_response", ""),
                    requires_confirmation=data.get("requires_confirmation", False)
                )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
        
        return ParsedIntent(
            intent=Intent.UNKNOWN,
            confidence=0.5,
            original_message=message,
            suggested_response="Не удалось точно определить намерение. Уточните запрос."
        )
    
    def _dict_to_parsed_intent(self, data: dict, original_message: str) -> ParsedIntent:
        """Конвертирует словарь в ParsedIntent."""
        try:
            intent = Intent(data.get("intent", "unknown"))
        except ValueError:
            intent = Intent.UNKNOWN
            
        return ParsedIntent(
            intent=intent,
            confidence=data.get("confidence", 0.5),
            parameters=data.get("parameters", {}),
            original_message=original_message,
            suggested_response=data.get("suggested_response", ""),
            requires_confirmation=data.get("requires_confirmation", False)
        )
    
    async def generate_response(
        self, 
        intent: ParsedIntent, 
        execution_result: Optional[dict] = None
    ) -> str:
        """
        Генерирует человекочитаемый ответ на основе результата выполнения.
        
        Args:
            intent: Распознанное намерение
            execution_result: Результат выполнения команды
            
        Returns:
            Форматированный ответ для пользователя
        """
        if not execution_result:
            return intent.suggested_response
        
        # Для простых случаев используем шаблоны
        if execution_result.get("success"):
            if intent.intent == Intent.CHECK_STATUS:
                return self._format_status_response(execution_result)
            elif intent.intent == Intent.GET_ALERTS:
                return self._format_alerts_response(execution_result)
            elif intent.intent == Intent.LIST_VMS:
                return self._format_vms_response(execution_result)
        
        # Для сложных случаев используем LLM
        prompt = f"""Сформулируй краткий и понятный ответ пользователю.

Намерение: {intent.intent.value}
Параметры: {json.dumps(intent.parameters, ensure_ascii=False)}
Результат выполнения: {json.dumps(execution_result, ensure_ascii=False)}

Ответ должен быть на русском языке, кратким и информативным."""

        response = await self.ai_service.generate_completion(
            prompt=prompt,
            system_prompt="Ты - AI-ассистент. Формулируй ответы кратко и по делу.",
            temperature=0.5,
            max_tokens=300
        )
        
        return response
    
    def _format_status_response(self, result: dict) -> str:
        """Форматирует ответ о статусе системы."""
        data = result.get("data", {})
        
        lines = ["📊 **Статус системы**\n"]
        
        if "services" in data:
            lines.append("**Сервисы:**")
            for service, status in data["services"].items():
                emoji = "✅" if status == "running" else "❌"
                lines.append(f"  {emoji} {service}: {status}")
        
        if "metrics" in data:
            lines.append("\n**Метрики:**")
            metrics = data["metrics"]
            if "cpu" in metrics:
                lines.append(f"  💻 CPU: {metrics['cpu']}%")
            if "memory" in metrics:
                lines.append(f"  🧠 RAM: {metrics['memory']}%")
            if "disk" in metrics:
                lines.append(f"  💾 Disk: {metrics['disk']}%")
        
        return "\n".join(lines)
    
    def _format_alerts_response(self, result: dict) -> str:
        """Форматирует ответ со списком алертов."""
        alerts = result.get("data", {}).get("alerts", [])
        
        if not alerts:
            return "✅ Активных алертов нет"
        
        lines = [f"🚨 **Активные алерты ({len(alerts)})**\n"]
        
        for alert in alerts[:10]:  # Максимум 10 алертов
            severity = alert.get("severity", "info")
            emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")
            lines.append(f"{emoji} **{alert.get('name', 'Unknown')}**")
            lines.append(f"   {alert.get('description', 'No description')}")
        
        if len(alerts) > 10:
            lines.append(f"\n... и еще {len(alerts) - 10} алертов")
        
        return "\n".join(lines)
    
    def _format_vms_response(self, result: dict) -> str:
        """Форматирует ответ со списком VM."""
        vms = result.get("data", {}).get("vms", [])
        
        if not vms:
            return "📦 Виртуальные машины не найдены"
        
        lines = [f"📦 **Виртуальные машины ({len(vms)})**\n"]
        
        for vm in vms:
            status = vm.get("status", "unknown")
            emoji = "🟢" if status == "running" else "🔴" if status == "stopped" else "🟡"
            lines.append(f"{emoji} **{vm.get('name', 'Unknown')}** (ID: {vm.get('id', '?')})")
            lines.append(f"   CPU: {vm.get('cpu', '?')} | RAM: {vm.get('memory', '?')} | Status: {status}")
        
        return "\n".join(lines)


# Singleton instance
_agent_instance: Optional[AIAgentService] = None


def get_ai_agent() -> AIAgentService:
    """Получить экземпляр AI-агента."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AIAgentService()
    return _agent_instance
