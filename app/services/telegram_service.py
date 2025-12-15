"""
Сервис для отправки сообщений в Telegram из бэкенда.
"""
import aiohttp
from config.settings import settings
from app.utils.logger import logger
from app.models.schemas import RemediationPlan

API_URL = f"https://api.telegram.org/bot{settings.telegram_token}"

async def send_message(text: str, parse_mode: str = "Markdown"):
    """Отправляет простое текстовое сообщение администратору."""
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": settings.admin_chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ошибка отправки сообщения в Telegram: {await response.text()}")
    except Exception as e:
        logger.error(f"Исключение при отправке сообщения в Telegram: {e}")

async def send_startup_message():
    """Отправляет сообщение о запуске API."""
    await send_message("✅ *AIOps Core API успешно запущен*\nГотов к работе!")

async def send_approval_request(plan: RemediationPlan):
    """Отправляет запрос на утверждение плана с кнопками."""
    text = (
        f"🚨 **Обнаружена Проблема: {plan.title}**\n\n"
        f"**Уровень серьезности:** `{plan.severity.value}`\n"
        f"**Описание:** {plan.description}\n\n"
        f"**Предлагаемый план:**\n```yaml\n{plan.playbook_yaml}```\n\n"
        f"Требуется ваше утверждение для выполнения плана ` {plan.plan_id} `."
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Утвердить", "callback_data": f"approve:{plan.plan_id}"},
                {"text": "❌ Отклонить", "callback_data": f"reject:{plan.plan_id}"}
            ]
        ]
    }

    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": settings.admin_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ошибка отправки запроса на утверждение: {await response.text()}")
    except Exception as e:
        logger.error(f"Исключение при отправке запроса на утверждение: {e}")
