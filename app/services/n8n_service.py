"""
n8n Integration Service - Интеграция с платформой автоматизации n8n.

Этот сервис обеспечивает двустороннюю интеграцию между AIOps и n8n:
- Отправка событий и алертов в n8n webhooks
- Получение команд от n8n workflows
- Управление автоматизациями
"""

import asyncio
import aiohttp
import json
import hmac
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from app.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class WebhookEventType(Enum):
    """Типы событий для отправки в n8n."""
    
    # Алерты
    ALERT_FIRED = "alert.fired"
    ALERT_RESOLVED = "alert.resolved"
    
    # Инциденты
    INCIDENT_CREATED = "incident.created"
    INCIDENT_UPDATED = "incident.updated"
    INCIDENT_RESOLVED = "incident.resolved"
    
    # Аномалии
    ANOMALY_DETECTED = "anomaly.detected"
    
    # Действия
    ACTION_REQUESTED = "action.requested"
    ACTION_APPROVED = "action.approved"
    ACTION_REJECTED = "action.rejected"
    ACTION_COMPLETED = "action.completed"
    
    # Система
    HEALTH_CHECK = "system.health_check"
    BACKUP_COMPLETED = "backup.completed"
    DEPLOYMENT_STARTED = "deployment.started"
    DEPLOYMENT_COMPLETED = "deployment.completed"


@dataclass
class WebhookPayload:
    """Структура данных для отправки в webhook."""
    
    event_type: WebhookEventType
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = "aiops"
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "data": self.data,
            "metadata": self.metadata
        }


@dataclass
class N8nWorkflow:
    """Информация о workflow в n8n."""
    
    id: str
    name: str
    webhook_url: str
    active: bool = True
    description: str = ""
    triggers: List[str] = field(default_factory=list)  # Типы событий, которые триггерят workflow


class N8nService:
    """
    Сервис интеграции с n8n.
    
    Поддерживает:
    - Отправку событий через webhooks
    - Регистрацию workflows
    - Проверку здоровья n8n
    - Подписание запросов для безопасности
    """
    
    def __init__(self):
        self.base_url = getattr(settings, 'n8n_url', 'http://n8n:5678')
        self.api_key = getattr(settings, 'n8n_api_key', None)
        self.webhook_secret = getattr(settings, 'n8n_webhook_secret', 'aiops-webhook-secret')
        
        # Зарегистрированные webhooks
        self.webhooks: Dict[str, N8nWorkflow] = {}
        
        # Очередь событий для отложенной отправки
        self.event_queue: List[WebhookPayload] = []
        
        # HTTP сессия
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получает или создает HTTP сессию."""
        if self._session is None or self._session.closed:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "AIOps/1.0"
            }
            if self.api_key:
                headers["X-N8N-API-KEY"] = self.api_key
            
            self._session = aiohttp.ClientSession(headers=headers)
        
        return self._session
    
    async def close(self):
        """Закрывает HTTP сессию."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _sign_payload(self, payload: dict) -> str:
        """Подписывает payload для верификации."""
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.webhook_secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def register_webhook(
        self, 
        workflow_id: str, 
        name: str, 
        webhook_url: str,
        triggers: List[WebhookEventType],
        description: str = ""
    ) -> N8nWorkflow:
        """
        Регистрирует webhook для workflow.
        
        Args:
            workflow_id: ID workflow в n8n
            name: Название workflow
            webhook_url: URL webhook'а
            triggers: Список типов событий, которые триггерят workflow
            description: Описание workflow
            
        Returns:
            Зарегистрированный workflow
        """
        workflow = N8nWorkflow(
            id=workflow_id,
            name=name,
            webhook_url=webhook_url,
            triggers=[t.value for t in triggers],
            description=description
        )
        
        self.webhooks[workflow_id] = workflow
        logger.info(f"Registered webhook: {name} ({workflow_id})")
        
        return workflow
    
    def unregister_webhook(self, workflow_id: str) -> bool:
        """Удаляет регистрацию webhook."""
        if workflow_id in self.webhooks:
            del self.webhooks[workflow_id]
            logger.info(f"Unregistered webhook: {workflow_id}")
            return True
        return False
    
    async def send_event(
        self, 
        event_type: WebhookEventType, 
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        specific_workflow: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Отправляет событие в n8n webhooks.
        
        Args:
            event_type: Тип события
            data: Данные события
            metadata: Дополнительные метаданные
            specific_workflow: ID конкретного workflow (если None, отправляется всем подходящим)
            
        Returns:
            Результаты отправки
        """
        payload = WebhookPayload(
            event_type=event_type,
            data=data,
            metadata=metadata or {}
        )
        
        results = {
            "sent": [],
            "failed": [],
            "skipped": []
        }
        
        # Находим подходящие webhooks
        target_workflows = []
        
        if specific_workflow:
            if specific_workflow in self.webhooks:
                target_workflows.append(self.webhooks[specific_workflow])
        else:
            for workflow in self.webhooks.values():
                if workflow.active and event_type.value in workflow.triggers:
                    target_workflows.append(workflow)
        
        if not target_workflows:
            logger.warning(f"No webhooks registered for event type: {event_type.value}")
            results["skipped"].append({
                "reason": "no_matching_webhooks",
                "event_type": event_type.value
            })
            return results
        
        # Отправляем в каждый webhook
        session = await self._get_session()
        payload_dict = payload.to_dict()
        signature = self._sign_payload(payload_dict)
        
        for workflow in target_workflows:
            try:
                headers = {
                    "X-AIOps-Signature": signature,
                    "X-AIOps-Event": event_type.value
                }
                
                async with session.post(
                    workflow.webhook_url,
                    json=payload_dict,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status in [200, 201, 202]:
                        results["sent"].append({
                            "workflow_id": workflow.id,
                            "workflow_name": workflow.name,
                            "status": response.status
                        })
                        logger.info(f"Event {event_type.value} sent to {workflow.name}")
                    else:
                        results["failed"].append({
                            "workflow_id": workflow.id,
                            "workflow_name": workflow.name,
                            "status": response.status,
                            "error": await response.text()
                        })
                        logger.error(f"Failed to send event to {workflow.name}: {response.status}")
                        
            except asyncio.TimeoutError:
                results["failed"].append({
                    "workflow_id": workflow.id,
                    "workflow_name": workflow.name,
                    "error": "timeout"
                })
                logger.error(f"Timeout sending event to {workflow.name}")
                
            except Exception as e:
                results["failed"].append({
                    "workflow_id": workflow.id,
                    "workflow_name": workflow.name,
                    "error": str(e)
                })
                logger.error(f"Error sending event to {workflow.name}: {e}")
        
        return results
    
    async def send_alert(
        self, 
        alert_name: str, 
        severity: str, 
        description: str,
        labels: Optional[Dict[str, str]] = None,
        resolved: bool = False
    ) -> Dict[str, Any]:
        """
        Отправляет алерт в n8n.
        
        Args:
            alert_name: Название алерта
            severity: Уровень серьезности (critical, warning, info)
            description: Описание алерта
            labels: Дополнительные метки
            resolved: True если алерт разрешен
            
        Returns:
            Результат отправки
        """
        event_type = WebhookEventType.ALERT_RESOLVED if resolved else WebhookEventType.ALERT_FIRED
        
        data = {
            "alert_name": alert_name,
            "severity": severity,
            "description": description,
            "labels": labels or {},
            "status": "resolved" if resolved else "firing"
        }
        
        return await self.send_event(event_type, data)
    
    async def send_incident(
        self,
        incident_id: str,
        title: str,
        severity: str,
        status: str,
        description: str = "",
        affected_services: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Отправляет информацию об инциденте в n8n.
        
        Args:
            incident_id: ID инцидента
            title: Заголовок инцидента
            severity: Уровень серьезности
            status: Статус (created, updated, resolved)
            description: Описание
            affected_services: Затронутые сервисы
            
        Returns:
            Результат отправки
        """
        event_map = {
            "created": WebhookEventType.INCIDENT_CREATED,
            "updated": WebhookEventType.INCIDENT_UPDATED,
            "resolved": WebhookEventType.INCIDENT_RESOLVED
        }
        
        event_type = event_map.get(status, WebhookEventType.INCIDENT_UPDATED)
        
        data = {
            "incident_id": incident_id,
            "title": title,
            "severity": severity,
            "status": status,
            "description": description,
            "affected_services": affected_services or []
        }
        
        return await self.send_event(event_type, data)
    
    async def send_action_request(
        self,
        action_id: str,
        action_type: str,
        target: str,
        parameters: Dict[str, Any],
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Отправляет запрос на действие в n8n для автоматизации.
        
        Args:
            action_id: ID действия
            action_type: Тип действия (restart, scale, deploy, etc.)
            target: Цель действия (сервис, VM и т.д.)
            parameters: Параметры действия
            reason: Причина действия
            
        Returns:
            Результат отправки
        """
        data = {
            "action_id": action_id,
            "action_type": action_type,
            "target": target,
            "parameters": parameters,
            "reason": reason
        }
        
        return await self.send_event(WebhookEventType.ACTION_REQUESTED, data)
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Проверяет доступность n8n.
        
        Returns:
            Статус здоровья n8n
        """
        try:
            session = await self._get_session()
            
            async with session.get(
                f"{self.base_url}/healthz",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    return {
                        "status": "healthy",
                        "url": self.base_url,
                        "registered_webhooks": len(self.webhooks)
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "url": self.base_url,
                        "error": f"HTTP {response.status}"
                    }
                    
        except Exception as e:
            return {
                "status": "unavailable",
                "url": self.base_url,
                "error": str(e)
            }
    
    def get_registered_webhooks(self) -> List[Dict[str, Any]]:
        """Возвращает список зарегистрированных webhooks."""
        return [
            {
                "id": w.id,
                "name": w.name,
                "webhook_url": w.webhook_url,
                "active": w.active,
                "triggers": w.triggers,
                "description": w.description
            }
            for w in self.webhooks.values()
        ]


# Singleton instance
_n8n_instance: Optional[N8nService] = None


def get_n8n_service() -> N8nService:
    """Получить экземпляр N8n сервиса."""
    global _n8n_instance
    if _n8n_instance is None:
        _n8n_instance = N8nService()
    return _n8n_instance
