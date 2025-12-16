"""
Тесты для N8n Service.

Проверяет функциональность интеграции с n8n.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

# Импортируем тестируемые классы
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.n8n_service import (
    N8nService,
    WebhookEventType,
    WebhookPayload,
    N8nWorkflow,
    get_n8n_service
)


class TestWebhookEventType:
    """Тесты для enum WebhookEventType."""
    
    def test_alert_events(self):
        """Проверяет наличие событий алертов."""
        assert WebhookEventType.ALERT_FIRED.value == "alert.fired"
        assert WebhookEventType.ALERT_RESOLVED.value == "alert.resolved"
    
    def test_incident_events(self):
        """Проверяет наличие событий инцидентов."""
        assert WebhookEventType.INCIDENT_CREATED.value == "incident.created"
        assert WebhookEventType.INCIDENT_UPDATED.value == "incident.updated"
        assert WebhookEventType.INCIDENT_RESOLVED.value == "incident.resolved"
    
    def test_action_events(self):
        """Проверяет наличие событий действий."""
        assert WebhookEventType.ACTION_REQUESTED.value == "action.requested"
        assert WebhookEventType.ACTION_COMPLETED.value == "action.completed"
    
    def test_all_events_have_dot_notation(self):
        """Проверяет формат значений событий."""
        for event in WebhookEventType:
            assert "." in event.value


class TestWebhookPayload:
    """Тесты для dataclass WebhookPayload."""
    
    def test_create_payload(self):
        """Проверяет создание payload."""
        payload = WebhookPayload(
            event_type=WebhookEventType.ALERT_FIRED,
            data={"alert_name": "High CPU"},
            metadata={"source": "prometheus"}
        )
        
        assert payload.event_type == WebhookEventType.ALERT_FIRED
        assert payload.data["alert_name"] == "High CPU"
        assert payload.source == "aiops"
    
    def test_payload_to_dict(self):
        """Проверяет сериализацию в словарь."""
        payload = WebhookPayload(
            event_type=WebhookEventType.INCIDENT_CREATED,
            data={"incident_id": "INC-001"}
        )
        
        result = payload.to_dict()
        
        assert result["event_type"] == "incident.created"
        assert result["source"] == "aiops"
        assert "timestamp" in result
        assert result["data"]["incident_id"] == "INC-001"
    
    def test_payload_default_values(self):
        """Проверяет значения по умолчанию."""
        payload = WebhookPayload(
            event_type=WebhookEventType.HEALTH_CHECK
        )
        
        assert payload.data == {}
        assert payload.metadata == {}
        assert payload.source == "aiops"


class TestN8nWorkflow:
    """Тесты для dataclass N8nWorkflow."""
    
    def test_create_workflow(self):
        """Проверяет создание workflow."""
        workflow = N8nWorkflow(
            id="wf-001",
            name="Alert Handler",
            webhook_url="http://n8n:5678/webhook/alerts",
            triggers=["alert.fired", "alert.resolved"]
        )
        
        assert workflow.id == "wf-001"
        assert workflow.name == "Alert Handler"
        assert workflow.active is True
        assert len(workflow.triggers) == 2
    
    def test_workflow_default_values(self):
        """Проверяет значения по умолчанию."""
        workflow = N8nWorkflow(
            id="wf-002",
            name="Test",
            webhook_url="http://test"
        )
        
        assert workflow.active is True
        assert workflow.description == ""
        assert workflow.triggers == []


class TestN8nService:
    """Тесты для N8nService."""
    
    @pytest.fixture
    def service(self):
        """Создает экземпляр сервиса для тестов."""
        with patch('app.services.n8n_service.settings') as mock_settings:
            mock_settings.n8n_url = "http://n8n:5678"
            mock_settings.n8n_api_key = "test-key"
            mock_settings.n8n_webhook_secret = "test-secret"
            return N8nService()
    
    def test_register_webhook(self, service):
        """Проверяет регистрацию webhook."""
        workflow = service.register_webhook(
            workflow_id="wf-001",
            name="Test Workflow",
            webhook_url="http://n8n:5678/webhook/test",
            triggers=[WebhookEventType.ALERT_FIRED],
            description="Test description"
        )
        
        assert workflow.id == "wf-001"
        assert workflow.name == "Test Workflow"
        assert "wf-001" in service.webhooks
    
    def test_unregister_webhook(self, service):
        """Проверяет удаление регистрации webhook."""
        service.register_webhook(
            workflow_id="wf-001",
            name="Test",
            webhook_url="http://test",
            triggers=[WebhookEventType.ALERT_FIRED]
        )
        
        result = service.unregister_webhook("wf-001")
        
        assert result is True
        assert "wf-001" not in service.webhooks
    
    def test_unregister_nonexistent_webhook(self, service):
        """Проверяет удаление несуществующего webhook."""
        result = service.unregister_webhook("nonexistent")
        
        assert result is False
    
    def test_get_registered_webhooks(self, service):
        """Проверяет получение списка зарегистрированных webhooks."""
        service.register_webhook(
            workflow_id="wf-001",
            name="Workflow 1",
            webhook_url="http://test1",
            triggers=[WebhookEventType.ALERT_FIRED]
        )
        service.register_webhook(
            workflow_id="wf-002",
            name="Workflow 2",
            webhook_url="http://test2",
            triggers=[WebhookEventType.INCIDENT_CREATED]
        )
        
        webhooks = service.get_registered_webhooks()
        
        assert len(webhooks) == 2
        assert any(w["id"] == "wf-001" for w in webhooks)
        assert any(w["id"] == "wf-002" for w in webhooks)
    
    def test_sign_payload(self, service):
        """Проверяет подписание payload."""
        payload = {"test": "data"}
        
        signature = service._sign_payload(payload)
        
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest
    
    def test_sign_payload_consistency(self, service):
        """Проверяет консистентность подписи."""
        payload = {"key": "value"}
        
        sig1 = service._sign_payload(payload)
        sig2 = service._sign_payload(payload)
        
        assert sig1 == sig2
    
    def test_sign_payload_different_for_different_data(self, service):
        """Проверяет различие подписей для разных данных."""
        sig1 = service._sign_payload({"a": 1})
        sig2 = service._sign_payload({"a": 2})
        
        assert sig1 != sig2


class TestN8nServiceAsync:
    """Асинхронные тесты для N8nService."""
    
    @pytest.fixture
    def service(self):
        """Создает экземпляр сервиса с мок-зависимостями."""
        with patch('app.services.n8n_service.settings') as mock_settings:
            mock_settings.n8n_url = "http://n8n:5678"
            mock_settings.n8n_api_key = "test-key"
            mock_settings.n8n_webhook_secret = "test-secret"
            return N8nService()
    
    @pytest.mark.asyncio
    async def test_send_event_no_webhooks(self, service):
        """Проверяет отправку события без зарегистрированных webhooks."""
        result = await service.send_event(
            event_type=WebhookEventType.ALERT_FIRED,
            data={"alert_name": "Test"}
        )
        
        assert len(result["skipped"]) > 0
        assert result["skipped"][0]["reason"] == "no_matching_webhooks"
    
    @pytest.mark.asyncio
    async def test_send_event_with_webhook(self, service):
        """Проверяет отправку события с зарегистрированным webhook."""
        service.register_webhook(
            workflow_id="wf-001",
            name="Test",
            webhook_url="http://n8n:5678/webhook/test",
            triggers=[WebhookEventType.ALERT_FIRED]
        )
        
        with patch.object(service, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value="OK")
            
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response
            
            mock_session_instance = MagicMock()
            mock_session_instance.post.return_value = mock_context
            mock_session.return_value = mock_session_instance
            
            result = await service.send_event(
                event_type=WebhookEventType.ALERT_FIRED,
                data={"alert_name": "Test"}
            )
            
            assert len(result["sent"]) == 1
            assert result["sent"][0]["workflow_id"] == "wf-001"
    
    @pytest.mark.asyncio
    async def test_send_alert(self, service):
        """Проверяет отправку алерта."""
        service.register_webhook(
            workflow_id="wf-001",
            name="Alert Handler",
            webhook_url="http://test",
            triggers=[WebhookEventType.ALERT_FIRED]
        )
        
        with patch.object(service, 'send_event', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"sent": [], "failed": [], "skipped": []}
            
            await service.send_alert(
                alert_name="High CPU",
                severity="critical",
                description="CPU > 90%"
            )
            
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["event_type"] == WebhookEventType.ALERT_FIRED
            assert call_args[1]["data"]["alert_name"] == "High CPU"
    
    @pytest.mark.asyncio
    async def test_send_alert_resolved(self, service):
        """Проверяет отправку разрешенного алерта."""
        with patch.object(service, 'send_event', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"sent": [], "failed": [], "skipped": []}
            
            await service.send_alert(
                alert_name="High CPU",
                severity="critical",
                description="CPU normalized",
                resolved=True
            )
            
            call_args = mock_send.call_args
            assert call_args[1]["event_type"] == WebhookEventType.ALERT_RESOLVED
    
    @pytest.mark.asyncio
    async def test_send_incident(self, service):
        """Проверяет отправку инцидента."""
        with patch.object(service, 'send_event', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"sent": [], "failed": [], "skipped": []}
            
            await service.send_incident(
                incident_id="INC-001",
                title="Database Down",
                severity="critical",
                status="created",
                affected_services=["api", "web"]
            )
            
            call_args = mock_send.call_args
            assert call_args[1]["event_type"] == WebhookEventType.INCIDENT_CREATED
            assert call_args[1]["data"]["incident_id"] == "INC-001"
    
    @pytest.mark.asyncio
    async def test_check_health_success(self, service):
        """Проверяет успешную проверку здоровья n8n."""
        with patch.object(service, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response
            
            mock_session_instance = MagicMock()
            mock_session_instance.get.return_value = mock_context
            mock_session.return_value = mock_session_instance
            
            result = await service.check_health()
            
            assert result["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_check_health_failure(self, service):
        """Проверяет обработку недоступности n8n."""
        with patch.object(service, '_get_session') as mock_session:
            mock_session.side_effect = Exception("Connection refused")
            
            result = await service.check_health()
            
            assert result["status"] == "unavailable"
            assert "error" in result


class TestGetN8nService:
    """Тесты для функции get_n8n_service."""
    
    def test_get_n8n_service_singleton(self):
        """Проверяет, что функция возвращает singleton."""
        with patch('app.services.n8n_service.settings'):
            # Сбрасываем singleton
            import app.services.n8n_service as module
            module._n8n_instance = None
            
            service1 = get_n8n_service()
            service2 = get_n8n_service()
            
            assert service1 is service2


# Маркеры для pytest
pytestmark = [pytest.mark.unit]
