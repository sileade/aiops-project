"""
Сервисный модуль для оркестрации полного цикла исправления: 
выполнение, пост-анализ и верификация.
"""

import logging
import os

from config.settings import settings
from app.services.ansible_service import AnsibleService
from app.services.post_analysis_service import PostAnalysisService
from app.services.verification_service import VerificationService
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)

class OrchestrationService:
    def __init__(self):
        self.ansible_service = AnsibleService()
        self.post_analysis_service = PostAnalysisService()
        self.verification_service = VerificationService()
        self.telegram_service = TelegramService()

    async def execute_and_verify_remediation(
        self, 
        playbook_name: str, 
        device_type: str, 
        device_host: str, 
        original_problem: str,
        original_log_query: dict
    ):
        """
        Оркестрирует полный цикл: выполнение, анализ, верификация.
        """
        playbook_path = os.path.join(settings.PLAYBOOKS_DIR, playbook_name)

        # --- Шаг 1: Выполнение плейбука ---
        await self.telegram_service.send_message(
            settings.admin_chat_id, 
            f"▶️ Выполняется плейбук `{playbook_name}`..."
        )
        success, output = self.ansible_service.run_playbook(playbook_path, device_type, device_host)

        if not success:
            await self.telegram_service.send_message(
                settings.admin_chat_id, 
                f"❌ **Ошибка выполнения плейбука!**\n\n```\n{output[-1000:]}```"
            )
            return

        await self.telegram_service.send_message(
            settings.admin_chat_id, 
            f"✅ Плейбук `{playbook_name}` выполнен."
        )

        # --- Шаг 2: Пост-анализ результатов ---
        await self.telegram_service.send_message(settings.admin_chat_id, "🤔 Анализ результатов выполнения...")
        analysis = self.post_analysis_service.analyze_execution_results(output, original_problem)
        
        await self.telegram_service.send_message(
            settings.admin_chat_id, 
            f"**Результат анализа:** `{analysis["status"]}`\n*Причина:* {analysis["reason"]}"
        )

        if analysis["status"] == "FAILURE":
            await self.telegram_service.send_message(settings.admin_chat_id, "Похоже, исправление не удалось. Рекомендуется ручная проверка.")
            return

        # --- Шаг 3: Верификация исправления ---
        await self.telegram_service.send_message(settings.admin_chat_id, "🔍 Верификация исправления... (ожидание 60 секунд)")
        is_fixed = self.verification_service.verify_fix(original_log_query, device_type)

        if is_fixed:
            await self.telegram_service.send_message(
                settings.admin_chat_id, 
                "🎉 **Проблема успешно решена!**\nОшибки в логах больше не появляются."
            )
        else:
            await self.telegram_service.send_message(
                settings.admin_chat_id, 
                "⚠️ **Верификация не удалась!**\nПроблема все еще присутствует. Запускаю повторный анализ..."
            )
            # Здесь можно запустить новый цикл анализа, возможно, с дополнительным контекстом
            # self.log_analyzer.analyze_and_propose_remediation(..., context="previous attempt failed")
