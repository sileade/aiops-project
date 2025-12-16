"""
Notification Service с Redis очередью и множественными каналами доставки.

Features:
- Persistent queue для критических алертов
- Email, Slack, PagerDuty интеграции
- Retry механизм с exponential backoff
- Priority-based routing
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.utils.logger import logger
from config.settings import settings

# Lazy imports
_redis_client = None
_aiohttp_session = None


def _get_redis():
    """Lazy initialization of Redis client."""
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.Redis(
            host=getattr(settings, "redis_host", "localhost"),
            port=getattr(settings, "redis_port", 6379),
            db=getattr(settings, "redis_notifications_db", 3),
            decode_responses=True,
        )
        return _redis_client
    except ImportError:
        logger.warning("redis package not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        return None


async def _get_http_session():
    """Get or create aiohttp session."""
    global _aiohttp_session

    if _aiohttp_session is None or _aiohttp_session.closed:
        import aiohttp

        _aiohttp_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return _aiohttp_session


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationChannel(Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


@dataclass
class Notification:
    """Notification message structure."""

    id: str
    title: str
    message: str
    priority: NotificationPriority
    channels: list[NotificationChannel]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "channels": [c.value for c in self.channels],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Notification":
        return cls(
            id=data["id"],
            title=data["title"],
            message=data["message"],
            priority=NotificationPriority(data["priority"]),
            channels=[NotificationChannel(c) for c in data["channels"]],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
        )


class NotificationQueue:
    """
    Persistent notification queue using Redis.
    """

    QUEUE_KEY = "aiops:notifications:queue"
    FAILED_KEY = "aiops:notifications:failed"
    PROCESSED_KEY = "aiops:notifications:processed"

    def __init__(self):
        self._processing = False
        self._processor_task: asyncio.Task | None = None

    @property
    def redis(self):
        return _get_redis()

    async def enqueue(self, notification: Notification) -> bool:
        """Add notification to queue."""
        if not self.redis:
            logger.warning("Redis not available, notification not queued")
            return False

        try:
            # Use priority for scoring (higher priority = lower score = processed first)
            priority_scores = {
                NotificationPriority.CRITICAL: 0,
                NotificationPriority.HIGH: 1,
                NotificationPriority.MEDIUM: 2,
                NotificationPriority.LOW: 3,
            }
            score = priority_scores.get(notification.priority, 2) + (time.time() / 1e10)

            await self.redis.zadd(self.QUEUE_KEY, {json.dumps(notification.to_dict()): score})
            logger.info(f"Notification {notification.id} queued with priority {notification.priority.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue notification: {e}")
            return False

    async def dequeue(self) -> Notification | None:
        """Get next notification from queue."""
        if not self.redis:
            return None

        try:
            # Get highest priority item (lowest score)
            items = await self.redis.zrange(self.QUEUE_KEY, 0, 0)
            if not items:
                return None

            item = items[0]
            await self.redis.zrem(self.QUEUE_KEY, item)

            return Notification.from_dict(json.loads(item))
        except Exception as e:
            logger.error(f"Failed to dequeue notification: {e}")
            return None

    async def requeue_with_backoff(self, notification: Notification):
        """Requeue failed notification with exponential backoff."""
        notification.retry_count += 1

        if notification.retry_count > notification.max_retries:
            # Move to failed queue
            await self._move_to_failed(notification)
            return

        # Calculate backoff delay
        delay = min(300, 2**notification.retry_count * 10)  # Max 5 minutes

        logger.info(f"Requeuing notification {notification.id} with {delay}s delay (retry {notification.retry_count})")

        # Schedule requeue
        await asyncio.sleep(delay)
        await self.enqueue(notification)

    async def _move_to_failed(self, notification: Notification):
        """Move notification to failed queue."""
        if not self.redis:
            return

        try:
            await self.redis.lpush(self.FAILED_KEY, json.dumps(notification.to_dict()))
            logger.warning(
                f"Notification {notification.id} moved to failed queue after {notification.retry_count} retries"
            )
        except Exception as e:
            logger.error(f"Failed to move notification to failed queue: {e}")

    async def get_queue_stats(self) -> dict[str, int]:
        """Get queue statistics."""
        if not self.redis:
            return {"available": False}

        try:
            return {
                "available": True,
                "pending": await self.redis.zcard(self.QUEUE_KEY),
                "failed": await self.redis.llen(self.FAILED_KEY),
                "processed": await self.redis.get(self.PROCESSED_KEY) or 0,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}


class NotificationService:
    """
    Multi-channel notification service.
    """

    def __init__(self):
        self.queue = NotificationQueue()
        self._running = False
        self._channel_handlers: dict[NotificationChannel, callable] = {}

        # Register default handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register channel handlers."""
        self._channel_handlers = {
            NotificationChannel.TELEGRAM: self._send_telegram,
            NotificationChannel.EMAIL: self._send_email,
            NotificationChannel.SLACK: self._send_slack,
            NotificationChannel.PAGERDUTY: self._send_pagerduty,
            NotificationChannel.WEBHOOK: self._send_webhook,
        }

    async def send(
        self,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        channels: list[NotificationChannel] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Send notification through specified channels.

        Returns:
            Notification ID
        """
        # Generate unique ID
        notification_id = hashlib.md5(f"{title}{message}{time.time()}".encode()).hexdigest()[:12]

        # Default channels based on priority
        if channels is None:
            channels = self._get_default_channels(priority)

        notification = Notification(
            id=notification_id,
            title=title,
            message=message,
            priority=priority,
            channels=channels,
            metadata=metadata or {},
        )

        # Queue for processing
        await self.queue.enqueue(notification)

        # For critical notifications, also try immediate delivery
        if priority == NotificationPriority.CRITICAL:
            asyncio.create_task(self._process_notification(notification))

        return notification_id

    def _get_default_channels(self, priority: NotificationPriority) -> list[NotificationChannel]:
        """Get default channels based on priority."""
        if priority == NotificationPriority.CRITICAL:
            return [NotificationChannel.TELEGRAM, NotificationChannel.PAGERDUTY, NotificationChannel.SLACK]
        elif priority == NotificationPriority.HIGH:
            return [NotificationChannel.TELEGRAM, NotificationChannel.SLACK]
        else:
            return [NotificationChannel.TELEGRAM]

    async def start_processor(self):
        """Start background notification processor."""
        self._running = True
        logger.info("Starting notification processor")

        while self._running:
            try:
                notification = await self.queue.dequeue()

                if notification:
                    await self._process_notification(notification)
                else:
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Processor error: {e}")
                await asyncio.sleep(5)

        logger.info("Notification processor stopped")

    async def stop_processor(self):
        """Stop the notification processor."""
        self._running = False

    async def _process_notification(self, notification: Notification):
        """Process a single notification."""
        success = True
        failed_channels = []

        for channel in notification.channels:
            handler = self._channel_handlers.get(channel)
            if not handler:
                logger.warning(f"No handler for channel: {channel}")
                continue

            try:
                await handler(notification)
                logger.info(f"Notification {notification.id} sent via {channel.value}")
            except Exception as e:
                logger.error(f"Failed to send via {channel.value}: {e}")
                failed_channels.append(channel)
                success = False

        if not success and failed_channels:
            # Requeue with only failed channels
            notification.channels = failed_channels
            asyncio.create_task(self.queue.requeue_with_backoff(notification))
        else:
            # Increment processed counter
            if self.queue.redis:
                await self.queue.redis.incr(NotificationQueue.PROCESSED_KEY)

    # ==================== Channel Handlers ====================

    async def _send_telegram(self, notification: Notification):
        """Send via Telegram."""
        try:
            from app.services import telegram_service

            # Format message
            priority_emoji = {
                NotificationPriority.CRITICAL: "🚨",
                NotificationPriority.HIGH: "⚠️",
                NotificationPriority.MEDIUM: "📢",
                NotificationPriority.LOW: "ℹ️",
            }
            emoji = priority_emoji.get(notification.priority, "📢")

            text = f"{emoji} *{notification.title}*\n\n{notification.message}"
            await telegram_service.send_message(text)

        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            raise

    async def _send_email(self, notification: Notification):
        """Send via Email (SMTP)."""
        email_config = {
            "smtp_host": getattr(settings, "smtp_host", None),
            "smtp_port": getattr(settings, "smtp_port", 587),
            "smtp_user": getattr(settings, "smtp_user", None),
            "smtp_password": getattr(settings, "smtp_password", None),
            "email_from": getattr(settings, "email_from", None),
            "email_to": getattr(settings, "email_to", None),
        }

        if not all([email_config["smtp_host"], email_config["email_to"]]):
            logger.warning("Email not configured, skipping")
            return

        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            import aiosmtplib

            msg = MIMEMultipart()
            msg["From"] = email_config["email_from"]
            msg["To"] = email_config["email_to"]
            msg["Subject"] = f"[AIOps {notification.priority.value.upper()}] {notification.title}"

            body = f"""
AIOps Alert

Title: {notification.title}
Priority: {notification.priority.value}
Time: {notification.created_at}

{notification.message}
"""
            msg.attach(MIMEText(body, "plain"))

            await aiosmtplib.send(
                msg,
                hostname=email_config["smtp_host"],
                port=email_config["smtp_port"],
                username=email_config["smtp_user"],
                password=email_config["smtp_password"],
                use_tls=True,
            )

        except ImportError:
            logger.warning("aiosmtplib not installed, email disabled")
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            raise

    async def _send_slack(self, notification: Notification):
        """Send via Slack webhook."""
        webhook_url = getattr(settings, "slack_webhook_url", None)

        if not webhook_url:
            logger.warning("Slack webhook not configured, skipping")
            return

        try:
            session = await _get_http_session()

            # Color based on priority
            colors = {
                NotificationPriority.CRITICAL: "#FF0000",
                NotificationPriority.HIGH: "#FFA500",
                NotificationPriority.MEDIUM: "#FFFF00",
                NotificationPriority.LOW: "#00FF00",
            }

            payload = {
                "attachments": [
                    {
                        "color": colors.get(notification.priority, "#808080"),
                        "title": notification.title,
                        "text": notification.message,
                        "footer": "AIOps",
                        "ts": int(time.time()),
                    }
                ]
            }

            async with session.post(webhook_url, json=payload) as response:
                if response.status != 200:
                    raise Exception(f"Slack returned {response.status}")

        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            raise

    async def _send_pagerduty(self, notification: Notification):
        """Send via PagerDuty Events API."""
        routing_key = getattr(settings, "pagerduty_routing_key", None)

        if not routing_key:
            logger.warning("PagerDuty not configured, skipping")
            return

        try:
            session = await _get_http_session()

            # Map priority to PagerDuty severity
            severity_map = {
                NotificationPriority.CRITICAL: "critical",
                NotificationPriority.HIGH: "error",
                NotificationPriority.MEDIUM: "warning",
                NotificationPriority.LOW: "info",
            }

            payload = {
                "routing_key": routing_key,
                "event_action": "trigger",
                "dedup_key": notification.id,
                "payload": {
                    "summary": notification.title,
                    "severity": severity_map.get(notification.priority, "warning"),
                    "source": "AIOps",
                    "custom_details": {"message": notification.message, **notification.metadata},
                },
            }

            async with session.post("https://events.pagerduty.com/v2/enqueue", json=payload) as response:
                if response.status not in [200, 202]:
                    raise Exception(f"PagerDuty returned {response.status}")

        except Exception as e:
            logger.error(f"PagerDuty send failed: {e}")
            raise

    async def _send_webhook(self, notification: Notification):
        """Send via custom webhook."""
        webhook_url = notification.metadata.get("webhook_url") or getattr(settings, "custom_webhook_url", None)

        if not webhook_url:
            logger.warning("Webhook URL not provided, skipping")
            return

        try:
            session = await _get_http_session()

            payload = notification.to_dict()

            async with session.post(webhook_url, json=payload) as response:
                if response.status >= 400:
                    raise Exception(f"Webhook returned {response.status}")

        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            raise


# Global instance
notification_service = NotificationService()


# ==================== Convenience Functions ====================


async def send_alert(title: str, message: str, priority: str = "medium", channels: list[str] | None = None) -> str:
    """
    Convenience function to send alerts.

    Args:
        title: Alert title
        message: Alert message
        priority: low, medium, high, or critical
        channels: List of channel names (telegram, email, slack, pagerduty)

    Returns:
        Notification ID
    """
    priority_enum = NotificationPriority(priority.lower())

    channel_enums = None
    if channels:
        channel_enums = [NotificationChannel(c.lower()) for c in channels]

    return await notification_service.send(title=title, message=message, priority=priority_enum, channels=channel_enums)


async def send_critical_alert(title: str, message: str) -> str:
    """Send critical alert to all channels."""
    return await notification_service.send(title=title, message=message, priority=NotificationPriority.CRITICAL)
