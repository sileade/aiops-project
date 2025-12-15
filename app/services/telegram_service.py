
"""
Сервис для отправки сообщений в Telegram из бэкенда.
"""
import aiohttp
import os
from config.settings import settings
from app.utils.logger import logger
from app.models.schemas import RemediationPlan
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

API_URL = f"https://api.telegram.org/bot{settings.telegram_token}"

class TelegramService:
    def __init__(self):
        pass

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        """Отправляет простое текстовое сообщение."""
        url = f"{API_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup.to_json()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка отправки сообщения в Telegram: {await response.text()}")
        except Exception as e:
            logger.error(f"Исключение при отправке сообщения в Telegram: {e}")

    async def send_approval_request(self, chat_id: int, problem_description: str, log_snippet: str, playbook_path: str):
        """
        Отправляет запрос на утверждение исправления с инлайн-кнопками.
        """
        text = f"""🚨 **Обнаружена проблема!**

**Анализ AI:**
{problem_description}

**Фрагмент лога:**
```
{log_snippet}
```

**Предлагаемый плейбук:** `{os.path.basename(playbook_path)}`

Вы хотите применить это исправление?"""

        keyboard = [
            [InlineKeyboardButton("✅ Утвердить", callback_data=f"approve_{os.path.basename(playbook_path)}")],
            [InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{os.path.basename(playbook_path)}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.send_message(chat_id, text, reply_markup=reply_markup)

    async def send_startup_message(self):
        """Отправляет сообщение о запуске API."""
        await self.send_message(settings.admin_chat_id, "✅ *AIOps Core API успешно запущен*\nГотов к работе!")
