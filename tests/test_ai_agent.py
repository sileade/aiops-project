"""
Тесты для AI Agent Service.

Проверяет функциональность парсинга естественного языка
и определения намерений пользователя.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Импортируем тестируемые классы
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.ai_agent_service import (
    AIAgentService,
    Intent,
    ParsedIntent,
    get_ai_agent
)


class TestIntent:
    """Тесты для enum Intent."""
    
    def test_intent_values(self):
        """Проверяет наличие основных намерений."""
        assert Intent.CHECK_STATUS.value == "check_status"
        assert Intent.HELP.value == "help"
        assert Intent.RESTART_SERVICE.value == "restart_service"
        assert Intent.UNKNOWN.value == "unknown"
    
    def test_all_intents_have_values(self):
        """Проверяет, что все намерения имеют строковые значения."""
        for intent in Intent:
            assert isinstance(intent.value, str)
            assert len(intent.value) > 0


class TestParsedIntent:
    """Тесты для dataclass ParsedIntent."""
    
    def test_create_parsed_intent(self):
        """Проверяет создание ParsedIntent."""
        intent = ParsedIntent(
            intent=Intent.CHECK_STATUS,
            confidence=0.95,
            parameters={"target": "nginx"},
            original_message="проверь статус nginx",
            suggested_response="Проверяю статус...",
            requires_confirmation=False
        )
        
        assert intent.intent == Intent.CHECK_STATUS
        assert intent.confidence == 0.95
        assert intent.parameters == {"target": "nginx"}
        assert intent.requires_confirmation is False
    
    def test_parsed_intent_to_dict(self):
        """Проверяет сериализацию в словарь."""
        intent = ParsedIntent(
            intent=Intent.RESTART_SERVICE,
            confidence=0.9,
            parameters={"service": "nginx"},
            original_message="перезапусти nginx",
            suggested_response="Перезапустить nginx?",
            requires_confirmation=True
        )
        
        result = intent.to_dict()
        
        assert result["intent"] == "restart_service"
        assert result["confidence"] == 0.9
        assert result["parameters"]["service"] == "nginx"
        assert result["requires_confirmation"] is True
    
    def test_parsed_intent_default_values(self):
        """Проверяет значения по умолчанию."""
        intent = ParsedIntent(
            intent=Intent.UNKNOWN,
            confidence=0.5
        )
        
        assert intent.parameters == {}
        assert intent.original_message == ""
        assert intent.suggested_response == ""
        assert intent.requires_confirmation is False


class TestAIAgentServiceQuickPatterns:
    """Тесты для быстрого определения намерений по паттернам."""
    
    @pytest.fixture
    def agent(self):
        """Создает экземпляр агента для тестов."""
        with patch('app.services.ai_agent_service.AIService'):
            with patch('app.services.ai_agent_service.CacheService'):
                return AIAgentService()
    
    def test_quick_pattern_status(self, agent):
        """Проверяет определение намерения CHECK_STATUS."""
        result = agent._quick_pattern_match("покажи статус")
        
        assert result is not None
        assert result.intent == Intent.CHECK_STATUS
        assert result.confidence >= 0.8
    
    def test_quick_pattern_help(self, agent):
        """Проверяет определение намерения HELP."""
        result = agent._quick_pattern_match("помощь")
        
        assert result is not None
        assert result.intent == Intent.HELP
    
    def test_quick_pattern_alerts(self, agent):
        """Проверяет определение намерения GET_ALERTS."""
        result = agent._quick_pattern_match("покажи алерты")
        
        assert result is not None
        assert result.intent == Intent.GET_ALERTS
    
    def test_quick_pattern_restart(self, agent):
        """Проверяет определение намерения RESTART_SERVICE."""
        result = agent._quick_pattern_match("перезапусти nginx")
        
        assert result is not None
        assert result.intent == Intent.RESTART_SERVICE
        assert result.requires_confirmation is True
    
    def test_quick_pattern_vms(self, agent):
        """Проверяет определение намерения LIST_VMS."""
        result = agent._quick_pattern_match("список виртуалок")
        
        assert result is not None
        assert result.intent == Intent.LIST_VMS
    
    def test_quick_pattern_network(self, agent):
        """Проверяет определение намерения CHECK_NETWORK."""
        result = agent._quick_pattern_match("проверь сеть")
        
        assert result is not None
        assert result.intent == Intent.CHECK_NETWORK
    
    def test_quick_pattern_no_match(self, agent):
        """Проверяет отсутствие совпадения для неизвестного текста."""
        result = agent._quick_pattern_match("какая-то случайная фраза")
        
        assert result is None
    
    def test_quick_pattern_case_insensitive(self, agent):
        """Проверяет нечувствительность к регистру."""
        result1 = agent._quick_pattern_match("СТАТУС")
        result2 = agent._quick_pattern_match("Статус")
        result3 = agent._quick_pattern_match("статус")
        
        assert all(r is not None for r in [result1, result2, result3])
        assert all(r.intent == Intent.CHECK_STATUS for r in [result1, result2, result3])


class TestAIAgentServiceParamExtraction:
    """Тесты для извлечения параметров из сообщений."""
    
    @pytest.fixture
    def agent(self):
        """Создает экземпляр агента для тестов."""
        with patch('app.services.ai_agent_service.AIService'):
            with patch('app.services.ai_agent_service.CacheService'):
                return AIAgentService()
    
    def test_extract_ip_address(self, agent):
        """Проверяет извлечение IP адреса."""
        params = agent._extract_quick_params(
            "заблокируй IP 192.168.1.100",
            Intent.BLOCK_IP
        )
        
        assert params.get("ip") == "192.168.1.100"
    
    def test_extract_vm_id(self, agent):
        """Проверяет извлечение ID виртуальной машины."""
        params = agent._extract_quick_params(
            "перезагрузи VM id 100",
            Intent.RESTART_VM
        )
        
        assert params.get("vm_id") == "100"
    
    def test_extract_service_name(self, agent):
        """Проверяет извлечение имени сервиса."""
        params = agent._extract_quick_params(
            "перезапусти nginx",
            Intent.RESTART_SERVICE
        )
        
        assert params.get("service") == "nginx"
    
    def test_extract_timeframe_hours(self, agent):
        """Проверяет извлечение временного периода в часах."""
        params = agent._extract_quick_params(
            "анализ логов за 2 часа",
            Intent.ANALYZE_LOGS
        )
        
        assert params.get("timeframe") == "2h"
    
    def test_extract_timeframe_minutes(self, agent):
        """Проверяет извлечение временного периода в минутах."""
        params = agent._extract_quick_params(
            "логи за 30 минут",
            Intent.ANALYZE_LOGS
        )
        
        assert params.get("timeframe") == "30m"
    
    def test_extract_period_week(self, agent):
        """Проверяет извлечение периода 'неделя'."""
        params = agent._extract_quick_params(
            "отчет за неделю",
            Intent.GENERATE_REPORT
        )
        
        assert params.get("period") == "week"
    
    def test_extract_multiple_params(self, agent):
        """Проверяет извлечение нескольких параметров."""
        params = agent._extract_quick_params(
            "перезапусти nginx на сервере 192.168.1.10",
            Intent.RESTART_SERVICE
        )
        
        assert params.get("service") == "nginx"
        assert params.get("ip") == "192.168.1.10"


class TestAIAgentServiceAsync:
    """Асинхронные тесты для AI Agent Service."""
    
    @pytest.fixture
    def agent(self):
        """Создает экземпляр агента с мок-зависимостями."""
        with patch('app.services.ai_agent_service.AIService') as mock_ai:
            with patch('app.services.ai_agent_service.CacheService') as mock_cache:
                mock_cache_instance = MagicMock()
                mock_cache_instance.get = AsyncMock(return_value=None)
                mock_cache_instance.set = AsyncMock()
                mock_cache.return_value = mock_cache_instance
                
                agent = AIAgentService()
                agent.cache_service = mock_cache_instance
                return agent
    
    @pytest.mark.asyncio
    async def test_parse_empty_message(self, agent):
        """Проверяет обработку пустого сообщения."""
        result = await agent.parse_message("")
        
        assert result.intent == Intent.UNKNOWN
        assert result.confidence == 1.0
        assert "введите сообщение" in result.suggested_response.lower()
    
    @pytest.mark.asyncio
    async def test_parse_message_quick_match(self, agent):
        """Проверяет быстрое определение намерения."""
        result = await agent.parse_message("покажи статус")
        
        assert result.intent == Intent.CHECK_STATUS
        assert result.confidence >= 0.8
    
    @pytest.mark.asyncio
    async def test_parse_message_with_context(self, agent):
        """Проверяет парсинг с контекстом."""
        context = {"history": [{"role": "user", "content": "привет"}]}
        result = await agent.parse_message("помощь", context=context)
        
        assert result.intent == Intent.HELP


class TestGetAIAgent:
    """Тесты для функции get_ai_agent."""
    
    def test_get_ai_agent_singleton(self):
        """Проверяет, что функция возвращает singleton."""
        with patch('app.services.ai_agent_service.AIService'):
            with patch('app.services.ai_agent_service.CacheService'):
                # Сбрасываем singleton
                import app.services.ai_agent_service as module
                module._agent_instance = None
                
                agent1 = get_ai_agent()
                agent2 = get_ai_agent()
                
                assert agent1 is agent2


class TestResponseFormatting:
    """Тесты для форматирования ответов."""
    
    @pytest.fixture
    def agent(self):
        """Создает экземпляр агента для тестов."""
        with patch('app.services.ai_agent_service.AIService'):
            with patch('app.services.ai_agent_service.CacheService'):
                return AIAgentService()
    
    def test_format_status_response(self, agent):
        """Проверяет форматирование ответа о статусе."""
        result = {
            "data": {
                "services": {
                    "api": "running",
                    "redis": "running",
                    "elasticsearch": "stopped"
                },
                "metrics": {
                    "cpu": 45,
                    "memory": 60,
                    "disk": 30
                }
            }
        }
        
        response = agent._format_status_response(result)
        
        assert "Статус системы" in response
        assert "api" in response
        assert "CPU" in response
        assert "45%" in response
    
    def test_format_alerts_response_empty(self, agent):
        """Проверяет форматирование пустого списка алертов."""
        result = {"data": {"alerts": []}}
        
        response = agent._format_alerts_response(result)
        
        assert "нет" in response.lower()
    
    def test_format_alerts_response_with_alerts(self, agent):
        """Проверяет форматирование списка алертов."""
        result = {
            "data": {
                "alerts": [
                    {
                        "name": "High CPU",
                        "severity": "critical",
                        "description": "CPU > 90%"
                    },
                    {
                        "name": "Low Memory",
                        "severity": "warning",
                        "description": "Memory < 10%"
                    }
                ]
            }
        }
        
        response = agent._format_alerts_response(result)
        
        assert "High CPU" in response
        assert "Low Memory" in response
        assert "🔴" in response  # critical
        assert "🟡" in response  # warning
    
    def test_format_vms_response_empty(self, agent):
        """Проверяет форматирование пустого списка VM."""
        result = {"data": {"vms": []}}
        
        response = agent._format_vms_response(result)
        
        assert "не найден" in response.lower()
    
    def test_format_vms_response_with_vms(self, agent):
        """Проверяет форматирование списка VM."""
        result = {
            "data": {
                "vms": [
                    {
                        "id": "100",
                        "name": "web-server",
                        "status": "running",
                        "cpu": "2",
                        "memory": "4GB"
                    },
                    {
                        "id": "101",
                        "name": "db-server",
                        "status": "stopped",
                        "cpu": "4",
                        "memory": "8GB"
                    }
                ]
            }
        }
        
        response = agent._format_vms_response(result)
        
        assert "web-server" in response
        assert "db-server" in response
        assert "🟢" in response  # running
        assert "🔴" in response  # stopped


# Маркеры для pytest
pytestmark = [pytest.mark.unit]
