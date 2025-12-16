"""
Сервис для обработки команд на естественном языке от AI чат-бота.
Поддерживает интерпретацию команд и выполнение действий.
"""

from typing import Any

from app.services import ai_service, analysis_service, system_service
from app.services.mikrotik_service import get_mikrotik_system_info
from app.services.proxmox_service import ProxmoxService
from app.utils.logger import logger


class ChatbotService:
    """Сервис для обработки команд чат-бота."""

    def __init__(self):
        self.proxmox_service: ProxmoxService | None = None

    def _get_proxmox_service(self) -> ProxmoxService:
        """Ленивая инициализация Proxmox сервиса."""
        if self.proxmox_service is None:
            self.proxmox_service = ProxmoxService()
        return self.proxmox_service

    async def process_natural_language_command(self, query: str) -> str:
        """
        Обрабатывает команду на естественном языке.

        Args:
            query: Команда пользователя на естественном языке

        Returns:
            Строка с результатом выполнения команды
        """
        try:
            # Шаг 1: Интерпретация команды с помощью AI
            command_json = await ai_service.interpret_natural_language(query)

            action = command_json.get("action", "unknown")
            target = command_json.get("target")
            parameters = command_json.get("parameters", {})

            logger.info(f"Интерпретирована команда: action={action}, target={target}, params={parameters}")

            # Шаг 2: Выполнение команды
            result = await self._execute_action(action, target, parameters)
            return result

        except Exception as e:
            logger.error(f"Ошибка при обработке команды '{query}': {e}", exc_info=True)
            return f"❌ Произошла ошибка при обработке команды: {str(e)}"

    async def _execute_action(self, action: str, target: str | None, parameters: dict[str, Any]) -> str:
        """
        Выполняет действие на основе интерпретированной команды.

        Args:
            action: Название действия
            target: Цель действия
            parameters: Дополнительные параметры

        Returns:
            Результат выполнения
        """
        handlers = {
            "get_status": self._handle_get_status,
            "analyze_service": self._handle_analyze_service,
            "run_playbook": self._handle_run_playbook,
            "get_logs": self._handle_get_logs,
            "restart_service": self._handle_restart_service,
            "list_vms": self._handle_list_vms,
            "vm_action": self._handle_vm_action,
            "get_mikrotik_info": self._handle_mikrotik_info,
            "reboot_mikrotik": self._handle_mikrotik_reboot,
            "help": self._handle_help,
            "unknown": self._handle_unknown,
        }

        handler = handlers.get(action, self._handle_unknown)
        return await handler(target, parameters)

    async def _handle_get_status(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик получения статуса."""
        try:
            if target == "system" or target is None:
                status = await system_service.get_full_system_status()
                return (
                    f"📊 **Статус системы**\n\n"
                    f"• API: `{status.api_status}`\n"
                    f"• Elasticsearch: `{status.elasticsearch_status}`\n"
                    f"• Prometheus: `{status.prometheus_status}`\n"
                    f"• Redis: `{status.redis_status}`\n\n"
                    f"• Ожидают утверждения: **{status.pending_actions}**\n"
                    f"• Недавние аномалии: **{status.recent_anomalies}**"
                )
            elif target == "proxmox":
                proxmox = self._get_proxmox_service()
                if proxmox.proxmox:
                    nodes = proxmox.get_all_nodes()
                    vms = proxmox.get_all_vms()
                    return (
                        f"📊 **Статус Proxmox**\n\n"
                        f"• Нод в кластере: **{len(nodes)}**\n"
                        f"• Всего VM/контейнеров: **{len(vms)}**\n\n"
                        f"**Ноды:**\n" + "\n".join([f"  • {n['node']}: `{n.get('status', 'unknown')}`" for n in nodes])
                    )
                else:
                    return "❌ Нет подключения к Proxmox"
            elif target == "mikrotik":
                info = await get_mikrotik_system_info()
                return (
                    f"📊 **Статус MikroTik**\n\n"
                    f"• Версия: `{info.get('version', 'N/A')}`\n"
                    f"• Uptime: `{info.get('uptime', 'N/A')}`\n"
                    f"• CPU: `{info.get('cpu-load', 'N/A')}%`\n"
                    f"• RAM: `{info.get('free-memory', 'N/A')}` свободно"
                )
            else:
                # Статус конкретного сервиса
                return f"ℹ️ Получение статуса для сервиса '{target}' в разработке."

        except Exception as e:
            logger.error(f"Ошибка получения статуса: {e}")
            return f"❌ Ошибка получения статуса: {str(e)}"

    async def _handle_analyze_service(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик запуска анализа сервиса."""
        if not target:
            return "⚠️ Пожалуйста, укажите имя сервиса для анализа."

        time_window = parameters.get("time_window", "15m")

        # Запускаем анализ в фоне
        import asyncio

        asyncio.create_task(analysis_service.trigger_full_analysis(target, time_window))

        return f"🔍 Анализ для сервиса **{target}** запущен.\nВременное окно: `{time_window}`\n\nРезультаты будут отправлены отдельным сообщением."

    async def _handle_run_playbook(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик запуска плейбука."""
        playbook_name = parameters.get("playbook_name")

        if not playbook_name:
            return "⚠️ Пожалуйста, укажите имя плейбука для запуска."

        if not target:
            return "⚠️ Пожалуйста, укажите целевой хост или сервис."

        return (
            f"📋 Запуск плейбука **{playbook_name}** для **{target}**\n\n"
            f"⚠️ Для безопасности, запуск плейбуков требует явного утверждения.\n"
            f"Используйте команду `/analyze {target}` для генерации и утверждения плана исправления."
        )

    async def _handle_get_logs(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик получения логов."""
        if not target:
            return "⚠️ Пожалуйста, укажите сервис для получения логов."

        time_window = parameters.get("time_window", "15m")

        try:
            from app.services.analysis_service import data_collector

            logs = await data_collector.collect_logs_from_elasticsearch(target, time_window)

            if not logs:
                return f"ℹ️ Логи для сервиса **{target}** за последние `{time_window}` не найдены."

            # Форматируем последние 10 логов
            log_lines = []
            for log in logs[:10]:
                timestamp = log.get("timestamp", "N/A")
                level = log.get("level", "INFO")
                message = log.get("message", "")[:100]
                log_lines.append(f"`[{timestamp}]` **{level}**: {message}")

            return (
                f"📜 **Логи для {target}** (последние {len(logs)} записей за `{time_window}`):\n\n"
                + "\n".join(log_lines)
                + f"\n\n_Показаны последние 10 из {len(logs)} записей_"
            )

        except Exception as e:
            logger.error(f"Ошибка получения логов: {e}")
            return f"❌ Ошибка получения логов: {str(e)}"

    async def _handle_restart_service(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик перезапуска сервиса."""
        if not target:
            return "⚠️ Пожалуйста, укажите сервис для перезапуска."

        return (
            f"⚠️ Перезапуск сервиса **{target}** требует подтверждения.\n\n"
            f"Для безопасности, используйте команду `/analyze {target}` "
            f"для генерации плана исправления с возможностью утверждения."
        )

    async def _handle_list_vms(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик списка виртуальных машин."""
        try:
            proxmox = self._get_proxmox_service()

            if not proxmox.proxmox:
                return "❌ Нет подключения к Proxmox"

            vms = proxmox.get_all_vms()

            if not vms:
                return "ℹ️ Виртуальные машины не найдены."

            vm_lines = []
            for vm in vms[:20]:  # Ограничиваем до 20
                status_emoji = "🟢" if vm.get("status") == "running" else "🔴"
                vm_lines.append(
                    f"{status_emoji} **{vm.get('name', 'N/A')}** (ID: {vm.get('vmid')})\n"
                    f"   Нода: `{vm.get('node')}` | Статус: `{vm.get('status')}`"
                )

            return f"🖥️ **Список VM/контейнеров** ({len(vms)} всего):\n\n" + "\n".join(vm_lines)

        except Exception as e:
            logger.error(f"Ошибка получения списка VM: {e}")
            return f"❌ Ошибка получения списка VM: {str(e)}"

    async def _handle_vm_action(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик действий с VM."""
        if not target:
            return "⚠️ Пожалуйста, укажите ID виртуальной машины."

        action = parameters.get("action", "status")
        node = parameters.get("node")

        try:
            vmid = int(target)
        except ValueError:
            return f"⚠️ Некорректный ID виртуальной машины: {target}"

        try:
            proxmox = self._get_proxmox_service()

            if not proxmox.proxmox:
                return "❌ Нет подключения к Proxmox"

            # Если нода не указана, пытаемся найти её
            if not node:
                vms = proxmox.get_all_vms()
                vm_info = next((vm for vm in vms if vm.get("vmid") == vmid), None)
                if vm_info:
                    node = vm_info.get("node")
                else:
                    return f"❌ VM с ID {vmid} не найдена"

            if action == "start":
                proxmox.start_vm(node, vmid)
                return f"▶️ VM **{vmid}** запускается на ноде `{node}`"
            elif action == "stop":
                proxmox.stop_vm(node, vmid)
                return f"⏹️ VM **{vmid}** останавливается на ноде `{node}`"
            elif action == "reboot":
                proxmox.reboot_vm(node, vmid)
                return f"🔄 VM **{vmid}** перезагружается на ноде `{node}`"
            elif action == "status":
                status = proxmox.get_vm_status(node, vmid)
                return (
                    f"📊 **Статус VM {vmid}**\n\n"
                    f"• Статус: `{status.get('status', 'N/A')}`\n"
                    f"• CPU: `{status.get('cpu', 0) * 100:.1f}%`\n"
                    f"• RAM: `{status.get('mem', 0) / 1024 / 1024:.0f} MB`"
                )
            else:
                return f"⚠️ Неизвестное действие: {action}"

        except Exception as e:
            logger.error(f"Ошибка выполнения действия с VM: {e}")
            return f"❌ Ошибка: {str(e)}"

    async def _handle_mikrotik_info(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик информации о MikroTik."""
        return await self._handle_get_status("mikrotik", parameters)

    async def _handle_mikrotik_reboot(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик перезагрузки MikroTik."""
        return (
            "⚠️ Перезагрузка MikroTik требует явного подтверждения.\n\n"
            "Для выполнения этого действия, пожалуйста, используйте "
            "специальную команду с подтверждением."
        )

    async def _handle_help(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик справки."""
        return (
            "🤖 **AIOps Чат-бот - Справка**\n\n"
            "Я понимаю команды на естественном языке. Вот примеры:\n\n"
            "📊 **Статус:**\n"
            '• "Покажи статус системы"\n'
            '• "Какой статус Proxmox?"\n'
            '• "Информация о MikroTik"\n\n'
            "🔍 **Анализ:**\n"
            '• "Проанализируй сервис nginx"\n'
            '• "Проверь логи за последний час"\n\n'
            "🖥️ **Виртуальные машины:**\n"
            '• "Покажи список VM"\n'
            '• "Статус VM 100"\n'
            '• "Запусти VM 101"\n\n'
            "📜 **Логи:**\n"
            '• "Покажи логи nginx"\n'
            '• "Ошибки за последние 30 минут"\n\n'
            "_Также доступны стандартные команды: /status, /analyze, /pending_"
        )

    async def _handle_unknown(self, target: str | None, parameters: dict[str, Any]) -> str:
        """Обработчик неизвестных команд."""
        return (
            "🤔 Не удалось распознать команду.\n\n"
            'Попробуйте переформулировать или используйте команду "помощь" '
            "для просмотра доступных действий."
        )


# Глобальный экземпляр сервиса
chatbot_service = ChatbotService()


async def process_natural_language_command(query: str) -> str:
    """
    Функция-обертка для обратной совместимости.

    Args:
        query: Команда пользователя

    Returns:
        Результат выполнения
    """
    return await chatbot_service.process_natural_language_command(query)
