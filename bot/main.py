"""
AIOps Telegram Bot с поддержкой AI-агента для понимания естественной речи.

Бот позволяет управлять IT-инфраструктурой через команды и естественный язык.
"""

import os
import sys
import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    ConversationHandler
)

# Добавляем путь к основному приложению
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import settings
from app.utils.logger import setup_logger
from app.services.ai_agent_service import get_ai_agent, Intent, ParsedIntent

logger = setup_logger("telegram_bot")
API_BASE_URL = f"http://{settings.api_host}:{settings.api_port}"

# Состояния для ConversationHandler
AWAITING_CONFIRMATION = 1


class TelegramBotHandler:
    """Обработчик команд Telegram бота с AI-агентом."""
    
    def __init__(self):
        self.ai_agent = get_ai_agent()
        self.pending_actions: Dict[int, ParsedIntent] = {}  # user_id -> pending intent
        self.conversation_context: Dict[int, list] = {}  # user_id -> message history
    
    def _is_authorized(self, user_id: int) -> bool:
        """Проверяет авторизацию пользователя."""
        if not settings.admin_chat_id:
            return True  # Если не настроен, разрешаем всем
        return str(user_id) == str(settings.admin_chat_id)
    
    def _add_to_context(self, user_id: int, role: str, content: str):
        """Добавляет сообщение в контекст диалога."""
        if user_id not in self.conversation_context:
            self.conversation_context[user_id] = []
        
        self.conversation_context[user_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # Храним только последние 10 сообщений
        if len(self.conversation_context[user_id]) > 10:
            self.conversation_context[user_id] = self.conversation_context[user_id][-10:]
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start."""
        user = update.effective_user
        
        if not self._is_authorized(user.id):
            await update.message.reply_html(
                f"Привет, {user.mention_html()}! К сожалению, у вас нет доступа к этой системе."
            )
            logger.warning(f"Unauthorized access attempt from user {user.id} ({user.username})")
            return
        
        welcome_message = f"""👋 Привет, {user.mention_html()}!

🤖 **AIOps Bot** готов к работе.

Я понимаю естественный язык! Просто напишите, что вам нужно:
• "Покажи статус серверов"
• "Проанализируй логи за последний час"
• "Перезапусти nginx"
• "Что с сервером web-01?"

📋 **Команды:**
/status - статус системы
/analyze <сервис> - анализ сервиса
/alerts - активные алерты
/vms - список виртуальных машин
/help - справка

💡 Или просто опишите проблему своими словами!"""

        await update.message.reply_html(welcome_message)
        self._add_to_context(user.id, "assistant", "Приветствие отправлено")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help."""
        help_text = """📚 **Справка по командам**

**Основные команды:**
• `/start` - начать работу с ботом
• `/status` - статус всех систем
• `/analyze <сервис>` - анализ конкретного сервиса
• `/alerts` - показать активные алерты
• `/vms` - список виртуальных машин
• `/network` - состояние сети

**Управление (требует подтверждения):**
• `/restart <сервис>` - перезапуск сервиса
• `/playbook <имя>` - запуск Ansible плейбука

**AI-ассистент:**
Просто напишите запрос на естественном языке:
• "Почему сайт тормозит?"
• "Найди ошибки в логах nginx"
• "Сколько памяти занимает база данных?"
• "Заблокируй IP 192.168.1.100"

**Примеры диалога:**
👤: Что-то сайт медленно работает
🤖: Анализирую... Обнаружена высокая нагрузка на CPU (85%). 
    Рекомендую перезапустить сервис nginx. Выполнить?
👤: Да
🤖: ✅ Сервис nginx перезапущен"""

        await update.message.reply_markdown(help_text)
    
    async def get_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /status."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Доступ запрещен")
            return
        
        await update.message.reply_text("⏳ Получаю статус системы...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/status", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        message = self._format_status(data)
                        await update.message.reply_markdown(message)
                    else:
                        await update.message.reply_text(f"❌ Ошибка API: {response.status}")
        except asyncio.TimeoutError:
            await update.message.reply_text("⏰ Таймаут при запросе к API")
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    def _format_status(self, data: dict) -> str:
        """Форматирует статус системы."""
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        # Определяем эмодзи для статусов
        def status_emoji(status: str) -> str:
            return "✅" if status in ["ok", "healthy", "running"] else "❌"
        
        return f"""📊 **Статус системы** `{timestamp}`

**Сервисы:**
{status_emoji(data.get('api_status', 'unknown'))} API: `{data.get('api_status', 'unknown')}`
{status_emoji(data.get('elasticsearch_status', 'unknown'))} Elasticsearch: `{data.get('elasticsearch_status', 'unknown')}`
{status_emoji(data.get('prometheus_status', 'unknown'))} Prometheus: `{data.get('prometheus_status', 'unknown')}`
{status_emoji(data.get('redis_status', 'unknown'))} Redis: `{data.get('redis_status', 'unknown')}`

**Метрики:**
⏳ Ожидают утверждения: **{data.get('pending_actions', 0)}**
⚠️ Аномалии (1ч): **{data.get('recent_anomalies', 0)}**"""
    
    async def get_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /alerts."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Доступ запрещен")
            return
        
        await update.message.reply_text("⏳ Получаю список алертов...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/api/v1/alerts", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        alerts = data.get("alerts", [])
                        
                        if not alerts:
                            await update.message.reply_text("✅ Активных алертов нет")
                            return
                        
                        message = f"🚨 **Активные алерты ({len(alerts)})**\n\n"
                        for alert in alerts[:10]:
                            severity = alert.get("severity", "info")
                            emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")
                            message += f"{emoji} **{alert.get('name', 'Unknown')}**\n"
                            message += f"   {alert.get('description', '')}\n\n"
                        
                        await update.message.reply_markdown(message)
                    else:
                        await update.message.reply_text(f"❌ Ошибка API: {response.status}")
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def list_vms(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /vms."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Доступ запрещен")
            return
        
        await update.message.reply_text("⏳ Получаю список виртуальных машин...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/api/v1/proxmox/vms", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        vms = data.get("vms", [])
                        
                        if not vms:
                            await update.message.reply_text("📦 Виртуальные машины не найдены")
                            return
                        
                        message = f"📦 **Виртуальные машины ({len(vms)})**\n\n"
                        for vm in vms:
                            status = vm.get("status", "unknown")
                            emoji = "🟢" if status == "running" else "🔴"
                            message += f"{emoji} **{vm.get('name', 'Unknown')}** (ID: {vm.get('id', '?')})\n"
                            message += f"   CPU: {vm.get('cpu', '?')} | RAM: {vm.get('memory', '?')}\n\n"
                        
                        await update.message.reply_markdown(message)
                    else:
                        await update.message.reply_text(f"❌ Ошибка API: {response.status}")
        except Exception as e:
            logger.error(f"Error getting VMs: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def analyze_service(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /analyze."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Доступ запрещен")
            return
        
        service_name = " ".join(context.args) if context.args else None
        
        if not service_name:
            await update.message.reply_text(
                "❓ Укажите имя сервиса.\n"
                "Пример: `/analyze nginx`"
            )
            return
        
        await update.message.reply_text(f"⏳ Запускаю анализ сервиса `{service_name}`...")
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"service_name": service_name}
                async with session.post(f"{API_BASE_URL}/analyze", json=payload, timeout=30) as response:
                    if response.status == 200:
                        await update.message.reply_text(
                            f"✅ Анализ для `{service_name}` запущен.\n"
                            "Результаты будут отправлены по готовности."
                        )
                    else:
                        data = await response.json()
                        await update.message.reply_text(f"❌ Ошибка: {data.get('detail', 'Unknown')}")
        except Exception as e:
            logger.error(f"Error analyzing service: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def handle_natural_language(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        """Обработчик сообщений на естественном языке."""
        user = update.effective_user
        message_text = update.message.text
        
        if not self._is_authorized(user.id):
            await update.message.reply_text("⛔ Доступ запрещен")
            return None
        
        logger.info(f"NL message from {user.id}: {message_text}")
        self._add_to_context(user.id, "user", message_text)
        
        # Показываем индикатор обработки
        processing_msg = await update.message.reply_text("🤔 Анализирую запрос...")
        
        try:
            # Парсим намерение с помощью AI-агента
            intent = await self.ai_agent.parse_message(
                message_text,
                context={"history": self.conversation_context.get(user.id, [])}
            )
            
            logger.info(f"Parsed intent: {intent.intent.value} (confidence: {intent.confidence})")
            
            # Удаляем сообщение "Анализирую..."
            await processing_msg.delete()
            
            # Если требуется подтверждение
            if intent.requires_confirmation:
                self.pending_actions[user.id] = intent
                
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Да", callback_data=f"confirm:{user.id}"),
                        InlineKeyboardButton("❌ Нет", callback_data=f"cancel:{user.id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"⚠️ **Требуется подтверждение**\n\n"
                    f"{intent.suggested_response}\n\n"
                    f"Выполнить действие?",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return AWAITING_CONFIRMATION
            
            # Выполняем действие
            result = await self._execute_intent(intent)
            
            # Генерируем ответ
            response = await self.ai_agent.generate_response(intent, result)
            self._add_to_context(user.id, "assistant", response)
            
            await update.message.reply_markdown(response)
            
        except Exception as e:
            logger.error(f"Error processing NL message: {e}")
            await processing_msg.edit_text(f"❌ Ошибка обработки: {e}")
        
        return None
    
    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработчик подтверждения действия."""
        query = update.callback_query
        await query.answer()
        
        action, user_id_str = query.data.split(":")
        user_id = int(user_id_str)
        
        if user_id not in self.pending_actions:
            await query.edit_message_text("❌ Действие устарело или уже выполнено")
            return ConversationHandler.END
        
        intent = self.pending_actions.pop(user_id)
        
        if action == "confirm":
            await query.edit_message_text("⏳ Выполняю...")
            
            try:
                result = await self._execute_intent(intent)
                response = await self.ai_agent.generate_response(intent, result)
                await query.edit_message_text(f"✅ {response}")
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка: {e}")
        else:
            await query.edit_message_text("🚫 Действие отменено")
        
        return ConversationHandler.END
    
    async def _execute_intent(self, intent: ParsedIntent) -> dict:
        """Выполняет действие на основе намерения."""
        
        # Маппинг намерений на API endpoints
        intent_handlers = {
            Intent.CHECK_STATUS: self._api_get_status,
            Intent.CHECK_HEALTH: self._api_check_health,
            Intent.GET_ALERTS: self._api_get_alerts,
            Intent.ANALYZE_LOGS: self._api_analyze_logs,
            Intent.FIND_ERRORS: self._api_find_errors,
            Intent.LIST_VMS: self._api_list_vms,
            Intent.CHECK_NETWORK: self._api_check_network,
            Intent.RESTART_SERVICE: self._api_restart_service,
            Intent.RUN_PLAYBOOK: self._api_run_playbook,
            Intent.HELP: self._get_help,
        }
        
        handler = intent_handlers.get(intent.intent)
        
        if handler:
            return await handler(intent.parameters)
        
        return {
            "success": False,
            "message": f"Действие '{intent.intent.value}' пока не реализовано"
        }
    
    async def _api_get_status(self, params: dict) -> dict:
        """Получает статус системы через API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/status", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _api_check_health(self, params: dict) -> dict:
        """Проверяет здоровье конкретного сервиса."""
        target = params.get("target", "all")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/health/{target}", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _api_get_alerts(self, params: dict) -> dict:
        """Получает список алертов."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/api/v1/alerts", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _api_analyze_logs(self, params: dict) -> dict:
        """Анализирует логи."""
        timeframe = params.get("timeframe", "1h")
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"timeframe": timeframe}
                async with session.post(f"{API_BASE_URL}/api/v1/analyze/logs", json=payload, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _api_find_errors(self, params: dict) -> dict:
        """Ищет ошибки в логах."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/api/v1/logs/errors", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _api_list_vms(self, params: dict) -> dict:
        """Получает список VM."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/api/v1/proxmox/vms", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _api_check_network(self, params: dict) -> dict:
        """Проверяет состояние сети."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/api/v1/network/status", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _api_restart_service(self, params: dict) -> dict:
        """Перезапускает сервис."""
        service = params.get("service")
        if not service:
            return {"success": False, "message": "Не указан сервис для перезапуска"}
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"service": service, "action": "restart"}
                async with session.post(f"{API_BASE_URL}/api/v1/services/control", json=payload, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data, "message": f"Сервис {service} перезапущен"}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _api_run_playbook(self, params: dict) -> dict:
        """Запускает Ansible плейбук."""
        playbook = params.get("playbook")
        if not playbook:
            return {"success": False, "message": "Не указан плейбук"}
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"playbook": playbook}
                async with session.post(f"{API_BASE_URL}/api/v1/ansible/run", json=payload, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    return {"success": False, "message": f"API error: {response.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def _get_help(self, params: dict) -> dict:
        """Возвращает справку."""
        return {
            "success": True,
            "data": {
                "commands": [
                    "/status - статус системы",
                    "/alerts - активные алерты",
                    "/vms - список VM",
                    "/analyze <сервис> - анализ сервиса",
                    "/help - справка"
                ],
                "nl_examples": [
                    "Покажи статус серверов",
                    "Найди ошибки в логах",
                    "Перезапусти nginx"
                ]
            }
        }
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик нажатий на инлайн-кнопки (для approve/reject планов)."""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        # Обработка подтверждения/отмены
        if data.startswith("confirm:") or data.startswith("cancel:"):
            await self.handle_confirmation(update, context)
            return
        
        # Обработка approve/reject планов
        if ":" in data:
            action, plan_id = data.split(":")
            
            payload = {"plan_id": plan_id, "approved": action == "approve"}
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{API_BASE_URL}/approve", json=payload) as response:
                        if response.status == 200:
                            result = await response.json()
                            await query.edit_message_text(
                                f"✅ План `{plan_id}`: **{result['message']}**",
                                parse_mode="Markdown"
                            )
                        else:
                            data = await response.json()
                            await query.edit_message_text(f"❌ Ошибка: {data.get('detail')}")
            except Exception as e:
                logger.error(f"Error processing approval: {e}")
                await query.edit_message_text(f"❌ Ошибка связи с API")


def main() -> None:
    """Запуск бота."""
    if not settings.telegram_token:
        logger.critical("TELEGRAM_TOKEN not found! Bot cannot start.")
        sys.exit(1)
    
    if not settings.admin_chat_id:
        logger.warning("ADMIN_CHAT_ID not set. Bot will respond to everyone.")
    
    # Создаем обработчик
    handler = TelegramBotHandler()
    
    # Создаем приложение
    application = Application.builder().token(settings.telegram_token).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", handler.start))
    application.add_handler(CommandHandler("help", handler.help_command))
    application.add_handler(CommandHandler("status", handler.get_status))
    application.add_handler(CommandHandler("alerts", handler.get_alerts))
    application.add_handler(CommandHandler("vms", handler.list_vms))
    application.add_handler(CommandHandler("analyze", handler.analyze_service))
    
    # Обработчик callback query (кнопки)
    application.add_handler(CallbackQueryHandler(handler.handle_callback_query))
    
    # Обработчик текстовых сообщений (NL)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handler.handle_natural_language
    ))
    
    logger.info("🤖 Telegram bot starting with AI agent support...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
