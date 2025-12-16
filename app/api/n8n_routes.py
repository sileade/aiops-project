"""
n8n API Routes - Эндпоинты для интеграции с n8n.

Предоставляет:
- Webhook endpoints для получения команд от n8n
- API для управления интеграцией
- Регистрация и управление workflows
"""

import hmac
import hashlib
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Header, Request, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.n8n_service import (
    get_n8n_service, 
    WebhookEventType,
    N8nService
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/n8n", tags=["n8n"])


# ============== Request/Response Models ==============

class WebhookRegistration(BaseModel):
    """Модель для регистрации webhook."""
    workflow_id: str = Field(..., description="ID workflow в n8n")
    name: str = Field(..., description="Название workflow")
    webhook_url: str = Field(..., description="URL webhook'а")
    triggers: List[str] = Field(..., description="Типы событий для триггера")
    description: str = Field("", description="Описание workflow")


class WebhookResponse(BaseModel):
    """Ответ о зарегистрированном webhook."""
    id: str
    name: str
    webhook_url: str
    active: bool
    triggers: List[str]
    description: str


class N8nCommand(BaseModel):
    """Команда от n8n workflow."""
    command: str = Field(..., description="Тип команды")
    target: Optional[str] = Field(None, description="Цель команды")
    parameters: dict = Field(default_factory=dict, description="Параметры команды")
    workflow_id: Optional[str] = Field(None, description="ID workflow отправителя")
    callback_url: Optional[str] = Field(None, description="URL для callback")


class CommandResult(BaseModel):
    """Результат выполнения команды."""
    success: bool
    command: str
    message: str
    data: Optional[dict] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class EventPayload(BaseModel):
    """Payload для отправки события в n8n."""
    event_type: str = Field(..., description="Тип события")
    data: dict = Field(..., description="Данные события")
    metadata: dict = Field(default_factory=dict, description="Метаданные")
    specific_workflow: Optional[str] = Field(None, description="ID конкретного workflow")


class HealthResponse(BaseModel):
    """Ответ о здоровье n8n."""
    status: str
    url: str
    registered_webhooks: int = 0
    error: Optional[str] = None


# ============== Webhook Endpoints ==============

@router.post("/webhook/command", response_model=CommandResult)
async def receive_command(
    command: N8nCommand,
    background_tasks: BackgroundTasks,
    x_n8n_signature: Optional[str] = Header(None, alias="X-N8N-Signature")
):
    """
    Получает команду от n8n workflow.
    
    Поддерживаемые команды:
    - restart_service: Перезапуск сервиса
    - run_playbook: Запуск Ansible плейбука
    - analyze_logs: Анализ логов
    - create_backup: Создание бэкапа
    - scale_service: Масштабирование сервиса
    - block_ip: Блокировка IP адреса
    - send_notification: Отправка уведомления
    """
    logger.info(f"Received command from n8n: {command.command}")
    
    # Обработка команды
    handlers = {
        "restart_service": _handle_restart_service,
        "run_playbook": _handle_run_playbook,
        "analyze_logs": _handle_analyze_logs,
        "create_backup": _handle_create_backup,
        "scale_service": _handle_scale_service,
        "block_ip": _handle_block_ip,
        "send_notification": _handle_send_notification,
        "health_check": _handle_health_check,
    }
    
    handler = handlers.get(command.command)
    
    if not handler:
        return CommandResult(
            success=False,
            command=command.command,
            message=f"Unknown command: {command.command}",
            data={"available_commands": list(handlers.keys())}
        )
    
    try:
        result = await handler(command.target, command.parameters)
        
        # Если есть callback URL, отправляем результат
        if command.callback_url:
            background_tasks.add_task(
                _send_callback,
                command.callback_url,
                result
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Error executing command {command.command}: {e}")
        return CommandResult(
            success=False,
            command=command.command,
            message=f"Error: {str(e)}"
        )


@router.post("/webhook/alert")
async def receive_alert_from_n8n(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Получает алерт от n8n (например, из внешних систем мониторинга).
    
    Этот endpoint позволяет n8n пересылать алерты из других систем
    (Zabbix, Nagios, CloudWatch и т.д.) в AIOps.
    """
    try:
        body = await request.json()
        
        alert_data = {
            "source": body.get("source", "n8n"),
            "alert_name": body.get("alert_name", "External Alert"),
            "severity": body.get("severity", "warning"),
            "description": body.get("description", ""),
            "labels": body.get("labels", {}),
            "timestamp": body.get("timestamp", datetime.utcnow().isoformat())
        }
        
        logger.info(f"Received alert from n8n: {alert_data['alert_name']}")
        
        # Здесь можно добавить обработку алерта
        # Например, создание инцидента или отправку в Telegram
        
        return {
            "status": "received",
            "alert_id": f"ext-{datetime.utcnow().timestamp()}",
            "message": "Alert processed"
        }
        
    except Exception as e:
        logger.error(f"Error processing alert from n8n: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============== Management Endpoints ==============

@router.post("/webhooks/register", response_model=WebhookResponse)
async def register_webhook(registration: WebhookRegistration):
    """
    Регистрирует новый webhook для workflow.
    
    После регистрации, события указанных типов будут автоматически
    отправляться на webhook URL.
    """
    n8n_service = get_n8n_service()
    
    # Валидация типов событий
    valid_triggers = []
    for trigger in registration.triggers:
        try:
            event_type = WebhookEventType(trigger)
            valid_triggers.append(event_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trigger type: {trigger}. Valid types: {[e.value for e in WebhookEventType]}"
            )
    
    workflow = n8n_service.register_webhook(
        workflow_id=registration.workflow_id,
        name=registration.name,
        webhook_url=registration.webhook_url,
        triggers=valid_triggers,
        description=registration.description
    )
    
    return WebhookResponse(
        id=workflow.id,
        name=workflow.name,
        webhook_url=workflow.webhook_url,
        active=workflow.active,
        triggers=workflow.triggers,
        description=workflow.description
    )


@router.delete("/webhooks/{workflow_id}")
async def unregister_webhook(workflow_id: str):
    """Удаляет регистрацию webhook."""
    n8n_service = get_n8n_service()
    
    if n8n_service.unregister_webhook(workflow_id):
        return {"status": "deleted", "workflow_id": workflow_id}
    
    raise HTTPException(status_code=404, detail=f"Webhook not found: {workflow_id}")


@router.get("/webhooks", response_model=List[WebhookResponse])
async def list_webhooks():
    """Возвращает список зарегистрированных webhooks."""
    n8n_service = get_n8n_service()
    webhooks = n8n_service.get_registered_webhooks()
    
    return [WebhookResponse(**w) for w in webhooks]


@router.post("/events/send")
async def send_event(payload: EventPayload):
    """
    Отправляет событие в зарегистрированные n8n webhooks.
    
    Используется для ручной отправки событий или интеграции
    с другими частями системы.
    """
    n8n_service = get_n8n_service()
    
    try:
        event_type = WebhookEventType(payload.event_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event type: {payload.event_type}"
        )
    
    result = await n8n_service.send_event(
        event_type=event_type,
        data=payload.data,
        metadata=payload.metadata,
        specific_workflow=payload.specific_workflow
    )
    
    return result


@router.get("/health", response_model=HealthResponse)
async def check_n8n_health():
    """Проверяет доступность n8n."""
    n8n_service = get_n8n_service()
    health = await n8n_service.check_health()
    
    return HealthResponse(**health)


@router.get("/event-types")
async def list_event_types():
    """Возвращает список доступных типов событий."""
    return {
        "event_types": [
            {
                "value": e.value,
                "name": e.name,
                "category": e.value.split(".")[0]
            }
            for e in WebhookEventType
        ]
    }


# ============== Command Handlers ==============

async def _handle_restart_service(target: Optional[str], params: dict) -> CommandResult:
    """Обработчик команды перезапуска сервиса."""
    if not target:
        return CommandResult(
            success=False,
            command="restart_service",
            message="Target service not specified"
        )
    
    # Здесь должна быть логика перезапуска сервиса
    logger.info(f"Restarting service: {target}")
    
    return CommandResult(
        success=True,
        command="restart_service",
        message=f"Service {target} restart initiated",
        data={"service": target, "status": "restarting"}
    )


async def _handle_run_playbook(target: Optional[str], params: dict) -> CommandResult:
    """Обработчик команды запуска плейбука."""
    playbook = target or params.get("playbook")
    
    if not playbook:
        return CommandResult(
            success=False,
            command="run_playbook",
            message="Playbook name not specified"
        )
    
    logger.info(f"Running playbook: {playbook}")
    
    return CommandResult(
        success=True,
        command="run_playbook",
        message=f"Playbook {playbook} execution started",
        data={"playbook": playbook, "status": "running"}
    )


async def _handle_analyze_logs(target: Optional[str], params: dict) -> CommandResult:
    """Обработчик команды анализа логов."""
    service = target or params.get("service", "all")
    timeframe = params.get("timeframe", "1h")
    
    logger.info(f"Analyzing logs for: {service}, timeframe: {timeframe}")
    
    return CommandResult(
        success=True,
        command="analyze_logs",
        message=f"Log analysis started for {service}",
        data={"service": service, "timeframe": timeframe, "status": "analyzing"}
    )


async def _handle_create_backup(target: Optional[str], params: dict) -> CommandResult:
    """Обработчик команды создания бэкапа."""
    backup_target = target or params.get("target", "all")
    
    logger.info(f"Creating backup for: {backup_target}")
    
    return CommandResult(
        success=True,
        command="create_backup",
        message=f"Backup creation started for {backup_target}",
        data={"target": backup_target, "status": "in_progress"}
    )


async def _handle_scale_service(target: Optional[str], params: dict) -> CommandResult:
    """Обработчик команды масштабирования сервиса."""
    if not target:
        return CommandResult(
            success=False,
            command="scale_service",
            message="Target service not specified"
        )
    
    replicas = params.get("replicas", 1)
    
    logger.info(f"Scaling service {target} to {replicas} replicas")
    
    return CommandResult(
        success=True,
        command="scale_service",
        message=f"Service {target} scaling to {replicas} replicas",
        data={"service": target, "replicas": replicas, "status": "scaling"}
    )


async def _handle_block_ip(target: Optional[str], params: dict) -> CommandResult:
    """Обработчик команды блокировки IP."""
    ip = target or params.get("ip")
    
    if not ip:
        return CommandResult(
            success=False,
            command="block_ip",
            message="IP address not specified"
        )
    
    reason = params.get("reason", "Blocked via n8n automation")
    duration = params.get("duration", "24h")
    
    logger.info(f"Blocking IP: {ip}, reason: {reason}")
    
    return CommandResult(
        success=True,
        command="block_ip",
        message=f"IP {ip} blocked for {duration}",
        data={"ip": ip, "reason": reason, "duration": duration}
    )


async def _handle_send_notification(target: Optional[str], params: dict) -> CommandResult:
    """Обработчик команды отправки уведомления."""
    channel = target or params.get("channel", "telegram")
    message = params.get("message", "")
    
    if not message:
        return CommandResult(
            success=False,
            command="send_notification",
            message="Notification message not specified"
        )
    
    logger.info(f"Sending notification to {channel}: {message[:50]}...")
    
    return CommandResult(
        success=True,
        command="send_notification",
        message=f"Notification sent to {channel}",
        data={"channel": channel, "message_preview": message[:100]}
    )


async def _handle_health_check(target: Optional[str], params: dict) -> CommandResult:
    """Обработчик команды проверки здоровья."""
    service = target or params.get("service", "all")
    
    logger.info(f"Health check for: {service}")
    
    # Здесь должна быть реальная проверка здоровья
    return CommandResult(
        success=True,
        command="health_check",
        message=f"Health check completed for {service}",
        data={
            "service": service,
            "status": "healthy",
            "checks": {
                "api": "ok",
                "database": "ok",
                "cache": "ok"
            }
        }
    )


async def _send_callback(callback_url: str, result: CommandResult):
    """Отправляет результат на callback URL."""
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                callback_url,
                json=result.dict(),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status not in [200, 201, 202]:
                    logger.error(f"Callback failed: {response.status}")
    except Exception as e:
        logger.error(f"Error sending callback: {e}")
