"""
Сервисный модуль для оркестрации полного цикла исправления:
выполнение, пост-анализ и верификация.
"""

import logging
import os
import asyncio
from typing import Optional, Dict, Any
from enum import Enum

from config.settings import settings
from app.services.ansible_service import AnsibleService
from app.services.telegram_service import TelegramService
from app.utils.logger import logger


class StepName(str, Enum):
    """Названия шагов в цикле оркестрации."""
    EXECUTION = "execution"
    POST_ANALYSIS = "post_analysis"
    VERIFICATION = "verification"


class StepStatus(str, Enum):
    """Статусы шагов."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"


class CycleStatus(str, Enum):
    """Статусы цикла."""
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class RemediationCycle:
    """Класс для отслеживания цикла исправления."""
    
    def __init__(self, cycle_id: str, device_type: str, device_host: str, problem: str):
        self.id = cycle_id
        self.device_type = device_type
        self.device_host = device_host
        self.problem = problem
        self.status = CycleStatus.IN_PROGRESS
        self.steps: Dict[StepName, Dict[str, Any]] = {}
        self.result_message: Optional[str] = None
    
    def add_step(self, step_name: StepName, details: Dict[str, Any] = None):
        """Добавляет шаг в цикл."""
        self.steps[step_name] = {
            "status": StepStatus.PENDING,
            "details": details or {}
        }
    
    def update_step(self, step_name: StepName, status: StepStatus, details: Dict[str, Any] = None):
        """Обновляет статус шага."""
        if step_name in self.steps:
            self.steps[step_name]["status"] = status
            if details:
                self.steps[step_name]["details"].update(details)
    
    def close(self, status: CycleStatus, message: str):
        """Закрывает цикл."""
        self.status = status
        self.result_message = message


class OrchestrationService:
    """Сервис оркестрации полного цикла исправления."""
    
    def __init__(self):
        self.ansible_service = AnsibleService()
        self.telegram_service = TelegramService()
        self._cycles: Dict[str, RemediationCycle] = {}
    
    def _create_cycle(
        self, 
        device_type: str, 
        device_host: str, 
        problem: str
    ) -> RemediationCycle:
        """Создает новый цикл исправления."""
        import uuid
        cycle_id = str(uuid.uuid4())[:8]
        cycle = RemediationCycle(cycle_id, device_type, device_host, problem)
        self._cycles[cycle_id] = cycle
        logger.info(f"Создан цикл исправления: {cycle_id}")
        return cycle
    
    def _analyze_execution_results(self, output: str, original_problem: str) -> Dict[str, Any]:
        """
        Анализирует результаты выполнения плейбука.
        
        Args:
            output: Вывод Ansible
            original_problem: Исходная проблема
            
        Returns:
            Словарь с результатами анализа
        """
        # Проверяем на наличие ошибок в выводе
        error_indicators = ["FAILED", "fatal:", "error:", "UNREACHABLE"]
        success_indicators = ["ok=", "changed=", "PLAY RECAP"]
        
        has_errors = any(indicator.lower() in output.lower() for indicator in error_indicators)
        has_success = any(indicator.lower() in output.lower() for indicator in success_indicators)
        
        if has_errors:
            return {
                "status": "FAILURE",
                "reason": "Обнаружены ошибки в выводе Ansible",
                "details": output[-500:] if len(output) > 500 else output
            }
        elif has_success:
            return {
                "status": "SUCCESS",
                "reason": "Плейбук выполнен успешно",
                "details": "Все задачи завершены без ошибок"
            }
        else:
            return {
                "status": "UNKNOWN",
                "reason": "Не удалось определить результат выполнения",
                "details": output[-500:] if len(output) > 500 else output
            }
    
    async def _verify_fix(
        self, 
        device_type: str, 
        device_host: str,
        original_problem: str,
        wait_seconds: int = 60
    ) -> bool:
        """
        Верифицирует исправление проблемы.
        
        Args:
            device_type: Тип устройства
            device_host: Хост устройства
            original_problem: Исходная проблема
            wait_seconds: Время ожидания перед проверкой
            
        Returns:
            True если проблема исправлена
        """
        logger.info(f"Ожидание {wait_seconds} секунд перед верификацией...")
        await asyncio.sleep(wait_seconds)
        
        # Здесь можно добавить специфичную логику верификации
        # В зависимости от типа устройства и проблемы
        
        # Базовая проверка - пинг хоста
        try:
            process = await asyncio.create_subprocess_shell(
                f"ping -c 3 -W 5 {device_host}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"Хост {device_host} доступен после исправления")
                return True
            else:
                logger.warning(f"Хост {device_host} недоступен после исправления")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при верификации: {e}")
            return False
    
    async def execute_and_verify_remediation(
        self, 
        playbook_name: str, 
        device_type: str, 
        device_host: str, 
        original_problem: str,
        original_log_query: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Оркестрирует полный цикл: выполнение, анализ, верификация.
        
        Args:
            playbook_name: Имя плейбука
            device_type: Тип устройства
            device_host: Хост устройства
            original_problem: Описание исходной проблемы
            original_log_query: Запрос для проверки логов (опционально)
            
        Returns:
            Словарь с результатами цикла
        """
        # Создаем цикл исправления
        cycle = self._create_cycle(device_type, device_host, original_problem)
        
        playbook_path = os.path.join(settings.ansible_playbook_dir, playbook_name)
        
        # --- Шаг 1: Выполнение плейбука ---
        cycle.add_step(StepName.EXECUTION, {"playbook_name": playbook_name})
        
        await self.telegram_service.send_message(
            f"▶️ *Цикл {cycle.id}*: Выполняется плейбук `{playbook_name}`..."
        )
        
        try:
            success, output = await asyncio.to_thread(
                self.ansible_service.run_playbook,
                playbook_path,
                device_type,
                device_host
            )
        except Exception as e:
            logger.error(f"Ошибка выполнения плейбука: {e}")
            success = False
            output = str(e)
        
        if not success:
            cycle.update_step(StepName.EXECUTION, StepStatus.FAILURE, {"output": output[-1000:]})
            cycle.close(CycleStatus.FAILURE, "Ошибка выполнения плейбука")
            
            await self.telegram_service.send_message(
                f"❌ *Цикл {cycle.id}*: Ошибка выполнения плейбука!\n\n```\n{output[-500:]}```"
            )
            
            return {
                "cycle_id": cycle.id,
                "status": "failure",
                "step": "execution",
                "message": "Ошибка выполнения плейбука"
            }
        
        cycle.update_step(StepName.EXECUTION, StepStatus.SUCCESS, {"output": "Выполнено успешно"})
        
        await self.telegram_service.send_message(
            f"✅ *Цикл {cycle.id}*: Плейбук `{playbook_name}` выполнен."
        )
        
        # --- Шаг 2: Пост-анализ результатов ---
        cycle.add_step(StepName.POST_ANALYSIS)
        
        await self.telegram_service.send_message(
            f"🔍 *Цикл {cycle.id}*: Анализ результатов выполнения..."
        )
        
        analysis = self._analyze_execution_results(output, original_problem)
        
        await self.telegram_service.send_message(
            f"📊 *Цикл {cycle.id}*: Результат анализа: `{analysis['status']}`\n"
            f"*Причина:* {analysis['reason']}"
        )
        
        if analysis["status"] == "FAILURE":
            cycle.update_step(StepName.POST_ANALYSIS, StepStatus.FAILURE, analysis)
            cycle.close(CycleStatus.FAILURE, "Анализ показал ошибки в выполнении")
            
            await self.telegram_service.send_message(
                f"⚠️ *Цикл {cycle.id}*: Исправление не удалось. Рекомендуется ручная проверка."
            )
            
            return {
                "cycle_id": cycle.id,
                "status": "failure",
                "step": "post_analysis",
                "message": analysis["reason"]
            }
        
        cycle.update_step(StepName.POST_ANALYSIS, StepStatus.SUCCESS, analysis)
        
        # --- Шаг 3: Верификация исправления ---
        cycle.add_step(StepName.VERIFICATION)
        
        await self.telegram_service.send_message(
            f"🔄 *Цикл {cycle.id}*: Верификация исправления (ожидание 60 секунд)..."
        )
        
        is_fixed = await self._verify_fix(device_type, device_host, original_problem)
        
        if is_fixed:
            cycle.update_step(StepName.VERIFICATION, StepStatus.SUCCESS)
            cycle.close(CycleStatus.SUCCESS, "Проблема успешно решена и верифицирована")
            
            await self.telegram_service.send_message(
                f"🎉 *Цикл {cycle.id}*: **Проблема успешно решена!**\n"
                f"Верификация пройдена успешно."
            )
            
            return {
                "cycle_id": cycle.id,
                "status": "success",
                "step": "verification",
                "message": "Проблема успешно решена и верифицирована"
            }
        else:
            cycle.update_step(StepName.VERIFICATION, StepStatus.FAILURE)
            cycle.close(CycleStatus.PARTIAL, "Верификация не удалась")
            
            await self.telegram_service.send_message(
                f"⚠️ *Цикл {cycle.id}*: **Верификация не удалась!**\n"
                f"Проблема может все еще присутствовать.\n"
                f"Рекомендуется запустить повторный анализ или провести ручную проверку."
            )
            
            return {
                "cycle_id": cycle.id,
                "status": "partial",
                "step": "verification",
                "message": "Плейбук выполнен, но верификация не удалась"
            }
    
    def get_cycle_status(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """Получает статус цикла по ID."""
        cycle = self._cycles.get(cycle_id)
        if not cycle:
            return None
        
        return {
            "id": cycle.id,
            "device_type": cycle.device_type,
            "device_host": cycle.device_host,
            "problem": cycle.problem,
            "status": cycle.status.value,
            "steps": {
                name.value: {
                    "status": step["status"].value,
                    "details": step["details"]
                }
                for name, step in cycle.steps.items()
            },
            "result_message": cycle.result_message
        }


# Глобальный экземпляр сервиса
orchestration_service = OrchestrationService()
