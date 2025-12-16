"""
Unit tests for Circuit Breaker implementation.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerConfig, CircuitBreakerOpenError


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    @pytest.fixture
    def breaker_config(self):
        """Create a circuit breaker config with short timeouts for testing."""
        return CircuitBreakerConfig(failure_threshold=3, timeout=1.0, success_threshold=2)  # 1 second for fast tests

    @pytest.fixture
    def breaker(self, breaker_config):
        """Create a fresh circuit breaker for each test."""
        # Clear singleton instances for testing
        name = f"test_breaker_{id(breaker_config)}"
        if name in CircuitBreaker._instances:
            del CircuitBreaker._instances[name]
        return CircuitBreaker(name, breaker_config)

    @pytest.mark.unit
    def test_initial_state_is_closed(self, breaker):
        """Circuit breaker should start in CLOSED state."""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed is True
        assert breaker.is_open is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_record_success_in_closed_state(self, breaker):
        """Recording success in CLOSED state should reset failure count."""
        breaker._state.failure_count = 2
        await breaker._record_success()
        assert breaker._state.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_record_failure_increments_count(self, breaker):
        """Recording failure should increment failure count."""
        await breaker._record_failure(Exception("test"))
        assert breaker._state.failure_count == 1
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self, breaker):
        """Circuit should open after reaching failure threshold."""
        for _ in range(3):
            await breaker._record_failure(Exception("test"))

        assert breaker.state == CircuitState.OPEN
        assert breaker._state.failure_count == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_is_available_when_closed(self, breaker):
        """Circuit should be available when CLOSED."""
        result = await breaker._check_state()
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_is_not_available_when_open(self, breaker):
        """Circuit should not be available when OPEN."""
        # Open the circuit
        for _ in range(3):
            await breaker._record_failure(Exception("test"))

        result = await breaker._check_state()
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self, breaker):
        """Circuit should transition to HALF_OPEN after timeout."""
        # Open the circuit
        for _ in range(3):
            await breaker._record_failure(Exception("test"))

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Check state triggers transition
        result = await breaker._check_state()
        assert result is True
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_half_open_closes_after_success_threshold(self, breaker):
        """Circuit should close after success threshold in HALF_OPEN."""
        # Open and transition to half-open
        for _ in range(3):
            await breaker._record_failure(Exception("test"))
        await asyncio.sleep(1.1)
        await breaker._check_state()  # Trigger transition to HALF_OPEN

        assert breaker.state == CircuitState.HALF_OPEN

        # Record successes
        await breaker._record_success()
        assert breaker.state == CircuitState.HALF_OPEN

        await breaker._record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker._state.failure_count == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_half_open_reopens_on_failure(self, breaker):
        """Circuit should reopen on failure in HALF_OPEN state."""
        # Open and transition to half-open
        for _ in range(3):
            await breaker._record_failure(Exception("test"))
        await asyncio.sleep(1.1)
        await breaker._check_state()  # Trigger transition to HALF_OPEN

        assert breaker.state == CircuitState.HALF_OPEN

        # Record failure
        await breaker._record_failure(Exception("test"))
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.unit
    def test_get_status(self, breaker):
        """get_status should return correct information."""
        status = breaker.get_status()

        assert "name" in status
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["success_count"] == 0
        assert "last_failure" in status

    @pytest.mark.unit
    def test_reset(self, breaker):
        """reset should restore initial state."""
        # Modify state
        breaker._state.failure_count = 5
        breaker._state.state = CircuitState.OPEN

        # Reset
        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker._state.failure_count == 0
        assert breaker._state.success_count == 0


class TestCircuitBreakerDecorator:
    """Tests for Circuit Breaker decorator functionality."""

    @pytest.fixture
    def breaker(self):
        """Create a fresh circuit breaker for decorator tests."""
        name = f"decorator_test_{time.time()}"
        return CircuitBreaker(name, CircuitBreakerConfig(failure_threshold=2, timeout=1.0, success_threshold=1))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_decorator_allows_successful_calls(self, breaker):
        """Decorator should allow successful calls through."""

        @breaker
        async def successful_func():
            return "success"

        result = await successful_func()
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_decorator_records_failures(self, breaker):
        """Decorator should record failures."""

        @breaker
        async def failing_func():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            await failing_func()

        assert breaker._state.failure_count == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_decorator_opens_circuit_after_threshold(self, breaker):
        """Decorator should open circuit after failure threshold."""

        @breaker
        async def failing_func():
            raise ValueError("test error")

        for _ in range(2):
            with pytest.raises(ValueError):
                await failing_func()

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_decorator_rejects_when_open(self, breaker):
        """Decorator should reject calls when circuit is open."""

        @breaker
        async def failing_func():
            raise ValueError("test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await failing_func()

        # Next call should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            await failing_func()


class TestCircuitBreakerAsync:
    """Async tests for Circuit Breaker with actual async operations."""

    @pytest.fixture
    def breaker(self):
        """Create a circuit breaker for async tests."""
        name = f"async_test_{time.time()}"
        return CircuitBreaker(name, CircuitBreakerConfig(failure_threshold=2, timeout=1.0, success_threshold=1))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_async_operation_success(self, breaker):
        """Test circuit breaker with successful async operation."""

        async def successful_operation():
            await asyncio.sleep(0.01)
            return "success"

        result = await breaker.call(successful_operation)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker._state.failure_count == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_async_operation_failure(self, breaker):
        """Test circuit breaker with failing async operation."""

        async def failing_operation():
            await asyncio.sleep(0.01)
            raise ConnectionError("Connection failed")

        for _ in range(2):
            with pytest.raises(ConnectionError):
                await breaker.call(failing_operation)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_circuit_prevents_calls_when_open(self, breaker):
        """Test that open circuit prevents calls."""
        call_count = 0

        async def tracked_operation():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Failed")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await breaker.call(tracked_operation)

        assert breaker.state == CircuitState.OPEN
        initial_call_count = call_count

        # Try more calls - should be blocked
        for _ in range(5):
            with pytest.raises(CircuitBreakerOpenError):
                await breaker.call(tracked_operation)

        # No additional calls should have been made
        assert call_count == initial_call_count


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    @pytest.mark.unit
    def test_default_config_values(self):
        """Default config should have sensible values."""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 30.0
        assert config.excluded_exceptions == ()

    @pytest.mark.unit
    def test_custom_config_values(self):
        """Custom config should override defaults."""
        config = CircuitBreakerConfig(
            failure_threshold=10, success_threshold=5, timeout=60.0, excluded_exceptions=(ValueError,)
        )

        assert config.failure_threshold == 10
        assert config.success_threshold == 5
        assert config.timeout == 60.0
        assert config.excluded_exceptions == (ValueError,)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_excluded_exceptions_not_counted(self):
        """Excluded exceptions should not count as failures."""
        name = f"excluded_test_{time.time()}"
        config = CircuitBreakerConfig(failure_threshold=2, excluded_exceptions=(ValueError,))
        breaker = CircuitBreaker(name, config)

        # Record excluded exception
        await breaker._record_failure(ValueError("excluded"))
        assert breaker._state.failure_count == 0

        # Record non-excluded exception
        await breaker._record_failure(TypeError("not excluded"))
        assert breaker._state.failure_count == 1
