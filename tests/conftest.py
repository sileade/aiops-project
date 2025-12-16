"""
Pytest configuration and fixtures for AIOps Platform tests.
"""

import asyncio
import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# Event Loop Configuration
# ============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Mock Settings
# ============================================================================


@pytest.fixture
def mock_settings():
    """Mock settings for tests."""
    settings = MagicMock()
    settings.openai_api_key = "test-api-key"
    settings.openai_base_url = "https://api.openai.com/v1"
    settings.openai_model = "gpt-4.1-mini"
    settings.enable_llm_fallback = True
    settings.ollama_base_url = "http://localhost:11434/v1"
    settings.ollama_model = "llama3.2"
    settings.enable_caching = True
    settings.redis_url = "redis://localhost:6379/0"
    settings.cache_ttl_analysis = 600
    settings.cache_ttl_playbook = 1800
    settings.cache_ttl_nl = 300
    settings.cb_failure_threshold = 3
    settings.cb_timeout = 60
    settings.cb_success_threshold = 2
    settings.elasticsearch_url = "http://localhost:9200"
    settings.prometheus_url = "http://localhost:9090"
    settings.telegram_token = "test-token"
    settings.admin_chat_id = "123456789"
    return settings


# ============================================================================
# Mock Redis
# ============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    redis.keys = AsyncMock(return_value=[])
    redis.ping = AsyncMock(return_value=True)
    return redis


# ============================================================================
# Mock OpenAI Client
# ============================================================================


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message = MagicMock()
    response.choices[0].message.content = "Test AI response"
    return response


@pytest.fixture
def mock_openai_client(mock_openai_response):
    """Mock OpenAI client."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = MagicMock(return_value=mock_openai_response)
    return client


# ============================================================================
# Mock Elasticsearch
# ============================================================================


@pytest.fixture
def mock_elasticsearch():
    """Mock Elasticsearch client."""
    es = AsyncMock()
    es.search = AsyncMock(
        return_value={
            "hits": {
                "total": {"value": 10},
                "hits": [
                    {
                        "_source": {
                            "message": "Error: Connection timeout",
                            "@timestamp": "2024-12-16T10:00:00Z",
                            "level": "ERROR",
                            "service": "api-gateway",
                        }
                    },
                    {
                        "_source": {
                            "message": "Warning: High memory usage",
                            "@timestamp": "2024-12-16T10:01:00Z",
                            "level": "WARNING",
                            "service": "api-gateway",
                        }
                    },
                ],
            }
        }
    )
    es.ping = AsyncMock(return_value=True)
    es.close = AsyncMock()
    return es


# ============================================================================
# Mock Prometheus
# ============================================================================


@pytest.fixture
def mock_prometheus_response():
    """Mock Prometheus query response."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {"instance": "localhost:9090", "job": "prometheus"}, "value": [1702720800, "85.5"]}],
        },
    }


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_logs():
    """Sample log entries for testing."""
    return [
        {
            "message": "ERROR: Database connection failed",
            "timestamp": "2024-12-16T10:00:00Z",
            "level": "ERROR",
            "service": "api-gateway",
        },
        {
            "message": "WARNING: High CPU usage detected (95%)",
            "timestamp": "2024-12-16T10:01:00Z",
            "level": "WARNING",
            "service": "worker",
        },
        {
            "message": "INFO: Request processed successfully",
            "timestamp": "2024-12-16T10:02:00Z",
            "level": "INFO",
            "service": "api-gateway",
        },
    ]


@pytest.fixture
def sample_metrics():
    """Sample metrics for testing."""
    return {
        "cpu_usage": 85.5,
        "memory_usage": 72.3,
        "disk_usage": 45.0,
        "network_in": 1024000,
        "network_out": 512000,
        "request_rate": 150.5,
        "error_rate": 2.3,
    }


@pytest.fixture
def sample_analysis_result():
    """Sample analysis result for testing."""
    return {
        "service_name": "api-gateway",
        "severity": "high",
        "root_cause": "Database connection pool exhausted",
        "affected_components": ["api-gateway", "database"],
        "recommendations": [
            "Increase connection pool size",
            "Add connection timeout handling",
            "Implement circuit breaker",
        ],
        "confidence": 0.85,
    }


@pytest.fixture
def sample_playbook():
    """Sample Ansible playbook for testing."""
    return """---
- name: Fix database connection issues
  hosts: api-servers
  become: yes
  tasks:
    - name: Restart API service
      systemd:
        name: api-gateway
        state: restarted
    
    - name: Clear connection pool
      command: /opt/scripts/clear_pool.sh
"""


# ============================================================================
# Circuit Breaker Test Fixtures
# ============================================================================


@pytest.fixture
def circuit_breaker_config():
    """Configuration for circuit breaker tests."""
    return {"failure_threshold": 3, "timeout": 5, "success_threshold": 2}  # Short timeout for tests


# ============================================================================
# Async Test Helpers
# ============================================================================


@pytest.fixture
def async_mock():
    """Helper to create async mocks."""

    def _create_async_mock(return_value=None):
        mock = AsyncMock()
        mock.return_value = return_value
        return mock

    return _create_async_mock
