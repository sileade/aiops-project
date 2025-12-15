
import os
import sys
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Добавляем путь к основному приложению для импорта настроек
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger("telegram_bot")
API_BASE_URL = f"http://{settings.api_host}:{settings.api_port}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    user = update.effective_user
    if str(user.id) != str(settings.admin_chat_id):
        await update.message.reply_html(
            f"Привет, {user.mention_html()}! К сожалению, у вас нет доступа к этой системе."
        )
        logger.warning(f"Попытка несанкционированного доступа от пользователя {user.id} ({user.username})")
        return
    
    await update.message.reply_html(
        f"👋 Привет, {user.mention_html()}! AIOps Бот готов к работе."
        "\n\nИспользуйте следующие команды для управления:" 
        "\n- `/status` - получить полный статус системы" 
        "\n- `/analyze <service_name>` - запустить анализ для сервиса"
    )

async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /status."""
    logger.info("Получен запрос на статус системы...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/status") as response:
                if response.status == 200:
                    data = await response.json()
                    message = (
                        f"**Статус Системы** `({data['timestamp']})`\n\n"
                        f"- API Сервер: `{data['api_status']}`\n"
                        f"- Elasticsearch: `{data['elasticsearch_status']}`\n"
                        f"- Prometheus: `{data['prometheus_status']}`\n"
                        f"- Redis: `{data['redis_status']}`\n\n"
                        f"- Ожидают утверждения: **{data['pending_actions']}**\n"
                        f"- Недавние аномалии (1ч): **{data['recent_anomalies']}**"
                    )
                    await update.message.reply_markdown(message)
                else:
                    await update.message.reply_text(f"Ошибка при получении статуса: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при запросе статуса к API: {e}")
        await update.message.reply_text(f"Не удалось подключиться к API: {e}")

async def analyze_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /analyze."""
    service_name = " ".join(context.args)
    if not service_name:
        await update.message.reply_text("Пожалуйста, укажите имя сервиса. Пример: `/analyze my-app`")
        return

    logger.info(f"Запрос на анализ сервиса '{service_name}' через Telegram...")
    payload = {"service_name": service_name}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE_URL}/analyze", json=payload) as response:
                if response.status == 200:
                    await update.message.reply_text(f"Анализ для сервиса '{service_name}' запущен в фоновом режиме.")
                else:
                    data = await response.json()
                    await update.message.reply_text(f"Ошибка при запуске анализа: {data.get('detail', 'Неизвестная ошибка')}")
    except Exception as e:
        logger.error(f"Ошибка при вызове API для анализа: {e}")
        await update.message.reply_text(f"Не удалось подключиться к API: {e}")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()

    action, plan_id = query.data.split(":")
    logger.info(f"Получено решение '{action}' для плана '{plan_id}'")

    payload = {"plan_id": plan_id, "approved": action == "approve"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE_URL}/approve", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    await query.edit_message_text(text=f"Решение по плану `{plan_id}` принято: *{result['message']}*")
                else:
                    data = await response.json()
                    await query.edit_message_text(text=f"Ошибка при обработке решения: {data.get('detail')}")
    except Exception as e:
        logger.error(f"Ошибка при отправке решения в API: {e}")
        await query.edit_message_text(text=f"Не удалось связаться с API для обработки решения.")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения как команды для AI чат-бота."""
    query = update.message.text
    logger.info(f"Получено текстовое сообщение для AI чата: ‘{query}’")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE_URL}/chat?query={query}") as response:
                if response.status == 200:
                    data = await response.json()
                    await update.message.reply_text(data.get("response", "Не удалось получить ответ."))
                else:
                    await update.message.reply_text(f"Ошибка при обработке вашего запроса: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при вызове API чата: {e}")
        await update.message.reply_text(f"Не удалось подключиться к API чата: {e}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных команд."""
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Извините, я не знаю такой команды.")

def main() -> None:
    """Запуск бота."""
    if not settings.telegram_token:
        logger.critical("Токен Telegram не найден! Бот не может быть запущен.")
        sys.exit(1)
    if not settings.admin_chat_id:
        logger.warning("ADMIN_CHAT_ID не установлен. Бот будет отвечать всем.")

    application = Application.builder().token(settings.telegram_token).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", get_status))
    application.add_handler(CommandHandler("analyze", analyze_service))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
        # Обработчик для текстовых сообщений (AI чат)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Telegram бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
