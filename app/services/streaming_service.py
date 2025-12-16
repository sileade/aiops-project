"""
Streaming Service для обработки логов через Redis Streams.

Features:
- Потоковая обработка логов в реальном времени
- Consumer groups для масштабирования
- Автоматическое обнаружение аномалий
- Буферизация и батчинг
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.utils.logger import logger
from config.settings import settings

# Lazy import redis
_redis_client = None


def _get_redis():
    """Lazy initialization of Redis client for streams."""
    global _redis_client
    
    if _redis_client is not None:
        return _redis_client
    
    try:
        import redis.asyncio as aioredis
        
        _redis_client = aioredis.Redis(
            host=getattr(settings, 'redis_host', 'localhost'),
            port=getattr(settings, 'redis_port', 6379),
            db=getattr(settings, 'redis_streams_db', 2),
            decode_responses=True,
            socket_connect_timeout=5,
        )
        logger.info("Redis Streams client initialized")
        return _redis_client
    except ImportError:
        logger.warning("redis package not installed. Streaming disabled.")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Redis Streams: {e}")
        return None


@dataclass
class LogEntry:
    """Структура записи лога."""
    timestamp: str
    service: str
    level: str
    message: str
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dict for Redis Stream."""
        return {
            "timestamp": self.timestamp,
            "service": self.service,
            "level": self.level,
            "message": self.message,
            "source": self.source,
            "metadata": json.dumps(self.metadata)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "LogEntry":
        """Create from Redis Stream entry."""
        metadata = {}
        if "metadata" in data:
            try:
                metadata = json.loads(data["metadata"])
            except:
                pass
        
        return cls(
            timestamp=data.get("timestamp", ""),
            service=data.get("service", "unknown"),
            level=data.get("level", "info"),
            message=data.get("message", ""),
            source=data.get("source", ""),
            metadata=metadata
        )


class StreamingService:
    """
    Service for processing logs via Redis Streams.
    
    Usage:
        streaming = StreamingService()
        
        # Publish log
        await streaming.publish_log(LogEntry(...))
        
        # Start consumer
        await streaming.start_consumer(handler_func)
    """
    
    STREAM_KEY = "aiops:logs:stream"
    CONSUMER_GROUP = "aiops-processors"
    MAX_STREAM_LENGTH = 100000  # Max entries in stream
    BATCH_SIZE = 100
    BLOCK_MS = 5000  # Block for 5 seconds waiting for new messages
    
    def __init__(self):
        self._running = False
        self._consumer_task: Optional[asyncio.Task] = None
        self._handlers: List[Callable] = []
        self._buffer: List[LogEntry] = []
        self._buffer_lock = asyncio.Lock()
        self._last_flush = time.time()
        self._flush_interval = 5.0  # Flush buffer every 5 seconds
    
    @property
    def redis(self):
        return _get_redis()
    
    async def initialize(self) -> bool:
        """Initialize stream and consumer group."""
        if not self.redis:
            logger.warning("Redis not available, streaming disabled")
            return False
        
        try:
            # Create consumer group if not exists
            try:
                await self.redis.xgroup_create(
                    self.STREAM_KEY,
                    self.CONSUMER_GROUP,
                    id="0",
                    mkstream=True
                )
                logger.info(f"Created consumer group: {self.CONSUMER_GROUP}")
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    raise
                logger.debug(f"Consumer group already exists: {self.CONSUMER_GROUP}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize streaming: {e}")
            return False
    
    async def publish_log(self, log: LogEntry) -> Optional[str]:
        """
        Publish a log entry to the stream.
        
        Returns:
            Stream entry ID or None if failed
        """
        if not self.redis:
            return None
        
        try:
            entry_id = await self.redis.xadd(
                self.STREAM_KEY,
                log.to_dict(),
                maxlen=self.MAX_STREAM_LENGTH,
                approximate=True
            )
            return entry_id
        except Exception as e:
            logger.error(f"Failed to publish log: {e}")
            return None
    
    async def publish_batch(self, logs: List[LogEntry]) -> int:
        """
        Publish multiple log entries.
        
        Returns:
            Number of successfully published entries
        """
        if not self.redis:
            return 0
        
        published = 0
        pipeline = self.redis.pipeline()
        
        for log in logs:
            pipeline.xadd(
                self.STREAM_KEY,
                log.to_dict(),
                maxlen=self.MAX_STREAM_LENGTH,
                approximate=True
            )
        
        try:
            results = await pipeline.execute()
            published = sum(1 for r in results if r)
        except Exception as e:
            logger.error(f"Failed to publish batch: {e}")
        
        return published
    
    async def buffer_log(self, log: LogEntry):
        """
        Buffer a log entry for batch publishing.
        Automatically flushes when buffer is full or interval elapsed.
        """
        async with self._buffer_lock:
            self._buffer.append(log)
            
            # Flush if buffer full or interval elapsed
            if len(self._buffer) >= self.BATCH_SIZE or \
               (time.time() - self._last_flush) > self._flush_interval:
                await self._flush_buffer()
    
    async def _flush_buffer(self):
        """Flush buffered logs to stream."""
        if not self._buffer:
            return
        
        logs_to_publish = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = time.time()
        
        published = await self.publish_batch(logs_to_publish)
        logger.debug(f"Flushed {published}/{len(logs_to_publish)} logs to stream")
    
    def add_handler(self, handler: Callable):
        """Add a handler function for processing logs."""
        self._handlers.append(handler)
    
    async def start_consumer(
        self,
        consumer_name: str = "consumer-1",
        handler: Optional[Callable] = None
    ):
        """
        Start consuming logs from the stream.
        
        Args:
            consumer_name: Unique name for this consumer
            handler: Optional handler function (also uses registered handlers)
        """
        if not await self.initialize():
            logger.error("Cannot start consumer: initialization failed")
            return
        
        if handler:
            self.add_handler(handler)
        
        self._running = True
        logger.info(f"Starting stream consumer: {consumer_name}")
        
        while self._running:
            try:
                # Read from stream
                messages = await self.redis.xreadgroup(
                    self.CONSUMER_GROUP,
                    consumer_name,
                    {self.STREAM_KEY: ">"},
                    count=self.BATCH_SIZE,
                    block=self.BLOCK_MS
                )
                
                if not messages:
                    continue
                
                # Process messages
                for stream_name, entries in messages:
                    for entry_id, data in entries:
                        try:
                            log = LogEntry.from_dict(data)
                            
                            # Call all handlers
                            for h in self._handlers:
                                try:
                                    if asyncio.iscoroutinefunction(h):
                                        await h(log)
                                    else:
                                        h(log)
                                except Exception as e:
                                    logger.error(f"Handler error: {e}")
                            
                            # Acknowledge message
                            await self.redis.xack(
                                self.STREAM_KEY,
                                self.CONSUMER_GROUP,
                                entry_id
                            )
                            
                        except Exception as e:
                            logger.error(f"Error processing entry {entry_id}: {e}")
                
            except asyncio.CancelledError:
                logger.info("Consumer cancelled")
                break
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                await asyncio.sleep(1)
        
        logger.info("Consumer stopped")
    
    async def stop_consumer(self):
        """Stop the consumer."""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
    
    async def get_stream_info(self) -> Dict[str, Any]:
        """Get information about the stream."""
        if not self.redis:
            return {"available": False}
        
        try:
            info = await self.redis.xinfo_stream(self.STREAM_KEY)
            groups = await self.redis.xinfo_groups(self.STREAM_KEY)
            
            return {
                "available": True,
                "length": info.get("length", 0),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
                "consumer_groups": len(groups),
                "groups": [
                    {
                        "name": g.get("name"),
                        "consumers": g.get("consumers"),
                        "pending": g.get("pending")
                    }
                    for g in groups
                ]
            }
        except Exception as e:
            return {"available": False, "error": str(e)}
    
    async def get_pending_count(self) -> int:
        """Get count of pending (unacknowledged) messages."""
        if not self.redis:
            return 0
        
        try:
            pending = await self.redis.xpending(self.STREAM_KEY, self.CONSUMER_GROUP)
            return pending.get("pending", 0) if pending else 0
        except:
            return 0


# ==================== Anomaly Detection Handler ====================

class AnomalyDetector:
    """
    Real-time anomaly detection for log streams.
    """
    
    def __init__(self):
        self._error_counts: Dict[str, int] = {}
        self._error_window = 60  # 1 minute window
        self._error_threshold = 10  # Errors per minute to trigger alert
        self._last_reset = time.time()
        self._alerted_services: set = set()
    
    async def process_log(self, log: LogEntry):
        """Process a log entry for anomaly detection."""
        # Reset counters every minute
        if time.time() - self._last_reset > self._error_window:
            self._error_counts.clear()
            self._alerted_services.clear()
            self._last_reset = time.time()
        
        # Count errors
        if log.level.lower() in ["error", "critical", "fatal"]:
            service = log.service
            self._error_counts[service] = self._error_counts.get(service, 0) + 1
            
            # Check threshold
            if self._error_counts[service] >= self._error_threshold:
                if service not in self._alerted_services:
                    self._alerted_services.add(service)
                    await self._trigger_alert(service, self._error_counts[service])
    
    async def _trigger_alert(self, service: str, error_count: int):
        """Trigger an alert for anomaly."""
        logger.warning(f"ANOMALY DETECTED: {service} has {error_count} errors in last minute")
        
        # Import here to avoid circular imports
        try:
            from app.services import telegram_service
            await telegram_service.send_message(
                f"🚨 *Anomaly Detected*\n"
                f"Service: {service}\n"
                f"Errors: {error_count} in last minute\n"
                f"Threshold: {self._error_threshold}"
            )
        except Exception as e:
            logger.error(f"Failed to send anomaly alert: {e}")


# Global instances
streaming_service = StreamingService()
anomaly_detector = AnomalyDetector()


async def default_log_handler(log: LogEntry):
    """Default handler that performs anomaly detection."""
    await anomaly_detector.process_log(log)


# Register default handler
streaming_service.add_handler(default_log_handler)
