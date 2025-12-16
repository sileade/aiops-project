"""
Circuit Breaker pattern implementation for graceful degradation.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failures exceeded threshold, requests fail fast
- HALF_OPEN: Testing if service recovered
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any

from app.utils.logger import logger


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Number of failures before opening
    success_threshold: int = 2  # Successes needed to close from half-open
    timeout: float = 30.0  # Seconds before trying half-open
    excluded_exceptions: tuple = ()  # Exceptions that don't count as failures


@dataclass
class CircuitBreakerState:
    """State tracking for circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    last_state_change: float = field(default_factory=time.time)


class CircuitBreaker:
    """
    Circuit Breaker implementation for protecting external service calls.

    Usage:
        breaker = CircuitBreaker("openai", config=CircuitBreakerConfig(failure_threshold=3))

        @breaker
        async def call_openai():
            ...
    """

    _instances: dict = {}

    def __new__(cls, name: str, config: CircuitBreakerConfig | None = None):
        """Singleton per name to share state across calls."""
        if name not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[name] = instance
        return cls._instances[name]

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        if self._initialized:
            return

        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitBreakerState()
        self._lock = asyncio.Lock()
        self._initialized = True

        logger.info(f"Circuit breaker '{name}' initialized with threshold={self.config.failure_threshold}")

    @property
    def state(self) -> CircuitState:
        return self._state.state

    @property
    def is_closed(self) -> bool:
        return self._state.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state.state == CircuitState.OPEN

    async def _check_state(self) -> bool:
        """Check if request should be allowed. Returns True if allowed."""
        async with self._lock:
            if self._state.state == CircuitState.CLOSED:
                return True

            if self._state.state == CircuitState.OPEN:
                # Check if timeout has passed
                if time.time() - self._state.last_failure_time >= self.config.timeout:
                    self._state.state = CircuitState.HALF_OPEN
                    self._state.success_count = 0
                    logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN")
                    return True
                return False

            # HALF_OPEN - allow limited requests
            return True

    async def _record_success(self):
        """Record a successful call."""
        async with self._lock:
            if self._state.state == CircuitState.HALF_OPEN:
                self._state.success_count += 1
                if self._state.success_count >= self.config.success_threshold:
                    self._state.state = CircuitState.CLOSED
                    self._state.failure_count = 0
                    logger.info(f"Circuit breaker '{self.name}' CLOSED after recovery")
            elif self._state.state == CircuitState.CLOSED:
                # Reset failure count on success
                self._state.failure_count = 0

    async def _record_failure(self, exception: Exception):
        """Record a failed call."""
        # Check if exception should be excluded
        if isinstance(exception, self.config.excluded_exceptions):
            return

        async with self._lock:
            self._state.failure_count += 1
            self._state.last_failure_time = time.time()

            if self._state.state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._state.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker '{self.name}' OPEN again after failure in half-open")

            elif self._state.state == CircuitState.CLOSED:
                if self._state.failure_count >= self.config.failure_threshold:
                    self._state.state = CircuitState.OPEN
                    logger.warning(f"Circuit breaker '{self.name}' OPEN after {self._state.failure_count} failures")

    def __call__(self, func: Callable) -> Callable:
        """Decorator for protecting async functions."""

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if not await self._check_state():
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN. Service unavailable.")

            try:
                result = await func(*args, **kwargs)
                await self._record_success()
                return result
            except Exception as e:
                await self._record_failure(e)
                raise

        return wrapper

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Call a function through the circuit breaker."""
        if not await self._check_state():
            raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN. Service unavailable.")

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure(e)
            raise

    def reset(self):
        """Manually reset the circuit breaker."""
        self._state = CircuitBreakerState()
        logger.info(f"Circuit breaker '{self.name}' manually reset")

    def get_status(self) -> dict:
        """Get current status of the circuit breaker."""
        return {
            "name": self.name,
            "state": self._state.state.value,
            "failure_count": self._state.failure_count,
            "success_count": self._state.success_count,
            "last_failure": self._state.last_failure_time,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected."""

    pass


# Pre-configured circuit breakers for common services
openai_breaker = CircuitBreaker("openai", CircuitBreakerConfig(failure_threshold=3, timeout=60.0, success_threshold=2))

ollama_breaker = CircuitBreaker("ollama", CircuitBreakerConfig(failure_threshold=5, timeout=30.0, success_threshold=1))

elasticsearch_breaker = CircuitBreaker("elasticsearch", CircuitBreakerConfig(failure_threshold=5, timeout=30.0))

prometheus_breaker = CircuitBreaker("prometheus", CircuitBreakerConfig(failure_threshold=5, timeout=30.0))
