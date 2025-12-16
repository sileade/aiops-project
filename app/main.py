"""
AIOps Core API

Центральный API для управления AIOps системой.
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
import asyncio

from app.models.schemas import (
    AnalysisRequest,
    ApprovalRequest,
    SystemStatus,
    RemediationPlan
)
from app.services import analysis_service, system_service, telegram_service
from app.services.notification_service import notification_service
from app.services.streaming_service import streaming_service
from app.utils.logger import logger
from config.settings import settings

app = FastAPI(
    title="AIOps Core API",
    description="Центральный API для управления AIOps системой",
    version="2.0.0",
    debug=settings.api_debug,
)

# Background tasks
_background_tasks = []


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("AIOps Core API запускается...")
    
    # Start notification processor
    if settings.enable_notifications:
        task = asyncio.create_task(notification_service.start_processor())
        _background_tasks.append(task)
        logger.info("Notification processor started")
    
    # Initialize streaming service
    if settings.streaming_enabled:
        await streaming_service.initialize()
        logger.info("Streaming service initialized")
    
    await telegram_service.send_startup_message()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("AIOps Core API останавливается...")
    
    # Stop notification processor
    await notification_service.stop_processor()
    
    # Stop streaming consumer
    await streaming_service.stop_consumer()
    
    # Cancel background tasks
    for task in _background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    # Close data collector connections
    await analysis_service.data_collector.close()
    
    logger.info("AIOps Core API остановлен")


# ==================== General Endpoints ====================

@app.get("/", tags=["General"])
async def read_root():
    """Проверка работоспособности API."""
    return {"status": "AIOps Core API is running", "version": "2.0.0"}


@app.get("/health", tags=["General"])
async def health_check():
    """Health check endpoint for Docker/K8s."""
    return {
        "status": "healthy",
        "services": {
            "api": True,
            "notifications": settings.enable_notifications,
            "streaming": settings.streaming_enabled
        }
    }


@app.get("/status", response_model=SystemStatus, tags=["System"])
async def get_system_status():
    """Получение полного статуса системы."""
    return await system_service.get_full_system_status()


@app.get("/status/data-sources", tags=["System"])
async def get_data_sources_status():
    """Get status of data sources (Elasticsearch, Prometheus) with circuit breaker info."""
    return await analysis_service.get_data_sources_status()


@app.get("/status/notifications", tags=["System"])
async def get_notification_status():
    """Get notification queue status."""
    return await notification_service.queue.get_queue_stats()


@app.get("/status/streaming", tags=["System"])
async def get_streaming_status():
    """Get streaming service status."""
    return await streaming_service.get_stream_info()


# ==================== Analysis Endpoints ====================

@app.post("/analyze", tags=["Analysis"])
async def analyze_service_endpoint(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks
):
    """
    Запускает асинхронный анализ для указанного сервиса.
    """
    logger.info(f"Получен запрос на анализ для сервиса: {request.service_name}")
    await telegram_service.send_message(f"▶️ Начинаю анализ для сервиса: *{request.service_name}*")
    background_tasks.add_task(
        analysis_service.trigger_full_analysis,
        service_name=request.service_name,
        time_window=request.time_window
    )
    return {"status": "Analysis started in the background."}


# ==================== Action Endpoints ====================

@app.post("/approve", tags=["Actions"])
async def approve_remediation_plan(request: ApprovalRequest):
    """
    Утверждает или отклоняет план исправления.
    Вызывается из Telegram бота.
    """
    logger.info(f"Получено решение по плану {request.plan_id}: {'Утверждено' if request.approved else 'Отклонено'}")
    try:
        result = await analysis_service.process_approval(request.plan_id, request.approved, request.reason)
        return {"status": "success", "message": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/plans/{plan_id}", response_model=RemediationPlan, tags=["Actions"])
async def get_plan_by_id(plan_id: str):
    """Получение информации о плане по его ID."""
    try:
        plan = await system_service.get_plan_from_db(plan_id)
        return plan
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== Webhook Endpoints ====================

@app.post("/api/v1/webhooks/alertmanager", tags=["Webhooks"])
async def alertmanager_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint для Alertmanager.
    Принимает алерты и запускает анализ для критических событий.
    """
    if not settings.alertmanager_webhook_enabled:
        raise HTTPException(status_code=403, detail="Alertmanager webhook is disabled")
    
    try:
        payload = await request.json()
        logger.info(f"Received Alertmanager webhook: {payload.get('status')}")
        
        # Process in background
        background_tasks.add_task(
            analysis_service.handle_alertmanager_webhook,
            payload
        )
        
        return {"status": "accepted", "message": "Webhook received and queued for processing"}
    except Exception as e:
        logger.error(f"Error processing Alertmanager webhook: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/webhooks/logs", tags=["Webhooks"])
async def logs_webhook(request: Request):
    """
    Webhook endpoint для приема логов (от Filebeat, Fluentd, etc.).
    Публикует логи в Redis Streams для обработки.
    """
    if not settings.streaming_enabled:
        raise HTTPException(status_code=403, detail="Streaming is disabled")
    
    try:
        payload = await request.json()
        
        # Handle both single log and batch
        logs = payload if isinstance(payload, list) else [payload]
        
        from app.services.streaming_service import LogEntry
        
        for log_data in logs:
            log_entry = LogEntry(
                timestamp=log_data.get("@timestamp", log_data.get("timestamp", "")),
                service=log_data.get("service", {}).get("name", log_data.get("service", "unknown")),
                level=log_data.get("log", {}).get("level", log_data.get("level", "info")),
                message=log_data.get("message", ""),
                source=log_data.get("source", ""),
                metadata=log_data
            )
            await streaming_service.buffer_log(log_entry)
        
        return {"status": "accepted", "count": len(logs)}
    except Exception as e:
        logger.error(f"Error processing logs webhook: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/webhooks/custom", tags=["Webhooks"])
async def custom_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Generic webhook endpoint for custom integrations.
    """
    try:
        payload = await request.json()
        event_type = payload.get("event_type", "unknown")
        
        logger.info(f"Received custom webhook: {event_type}")
        
        # Route based on event type
        if event_type == "alert":
            service = payload.get("service", "unknown")
            message = payload.get("message", "Custom alert received")
            background_tasks.add_task(
                analysis_service.trigger_full_analysis,
                service_name=service,
                time_window="15m"
            )
        
        return {"status": "accepted", "event_type": event_type}
    except Exception as e:
        logger.error(f"Error processing custom webhook: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Notification Endpoints ====================

@app.post("/api/v1/notify", tags=["Notifications"])
async def send_notification(request: Request):
    """
    Send a notification through configured channels.
    """
    try:
        payload = await request.json()
        
        from app.services.notification_service import send_alert
        
        notification_id = await send_alert(
            title=payload.get("title", "Notification"),
            message=payload.get("message", ""),
            priority=payload.get("priority", "medium"),
            channels=payload.get("channels")
        )
        
        return {"status": "queued", "notification_id": notification_id}
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Metrics Endpoint ====================

@app.get("/metrics", tags=["Monitoring"])
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.
    """
    # Basic metrics - can be extended with prometheus_client library
    queue_stats = await notification_service.queue.get_queue_stats()
    stream_info = await streaming_service.get_stream_info()
    
    metrics = []
    
    # Notification queue metrics
    if queue_stats.get("available"):
        metrics.append(f'aiops_notifications_pending {queue_stats.get("pending", 0)}')
        metrics.append(f'aiops_notifications_failed {queue_stats.get("failed", 0)}')
        metrics.append(f'aiops_notifications_processed {queue_stats.get("processed", 0)}')
    
    # Streaming metrics
    if stream_info.get("available"):
        metrics.append(f'aiops_stream_length {stream_info.get("length", 0)}')
    
    return "\n".join(metrics)
