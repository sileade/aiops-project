"""
Unit tests for Cache Service implementation.
"""

import pytest

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.cache_service import generate_cache_key


class TestGenerateCacheKey:
    """Tests for cache key generation."""

    @pytest.mark.unit
    def test_generate_cache_key_returns_string(self):
        """generate_cache_key should return a string."""
        key = generate_cache_key("prefix", "data")
        assert isinstance(key, str)
        assert len(key) > 0

    @pytest.mark.unit
    def test_generate_cache_key_is_deterministic(self):
        """Same input should produce same key."""
        key1 = generate_cache_key("prefix", "data")
        key2 = generate_cache_key("prefix", "data")
        assert key1 == key2

    @pytest.mark.unit
    def test_generate_cache_key_different_for_different_data(self):
        """Different data should produce different keys."""
        key1 = generate_cache_key("prefix", "data1")
        key2 = generate_cache_key("prefix", "data2")
        assert key1 != key2

    @pytest.mark.unit
    def test_generate_cache_key_different_for_different_prefix(self):
        """Different prefix should produce different keys."""
        key1 = generate_cache_key("prefix1", "data")
        key2 = generate_cache_key("prefix2", "data")
        assert key1 != key2

    @pytest.mark.unit
    def test_generate_cache_key_handles_dict(self):
        """generate_cache_key should handle dict data."""
        data = {"key": "value", "number": 123}
        key = generate_cache_key("prefix", data)
        assert isinstance(key, str)
        assert len(key) > 0

    @pytest.mark.unit
    def test_generate_cache_key_handles_none(self):
        """generate_cache_key should handle None data."""
        key = generate_cache_key("prefix", None)
        assert isinstance(key, str)
        assert len(key) > 0

    @pytest.mark.unit
    def test_generate_cache_key_contains_prefix(self):
        """Generated key should contain the prefix."""
        key = generate_cache_key("my_prefix", "data")
        assert "my_prefix" in key

    @pytest.mark.unit
    def test_generate_cache_key_handles_unicode(self):
        """generate_cache_key should handle unicode data."""
        key = generate_cache_key("prefix", "данные на русском")
        assert isinstance(key, str)
        assert len(key) > 0
