"""
Конфигурация приложения AIOps
Все настройки загружаются из переменных окружения с fallback на значения по умолчанию.
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Основные настройки приложения"""
    
    # ==================== Telegram ====================
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    admin_chat_id: int = int(os.getenv("ADMIN_CHAT_ID", "0"))
    
    # ==================== API Server ====================
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_debug: bool = os.getenv("API_DEBUG", "true").lower() == "true"
    
    # ==================== Elasticsearch ====================
    elasticsearch_host: str = os.getenv("ELASTICSEARCH_HOST", "localhost")
    elasticsearch_port: int = int(os.getenv("ELASTICSEARCH_PORT", "9200"))
    elasticsearch_url: str = os.getenv(
        "ELASTICSEARCH_URL", 
        f"http://{os.getenv('ELASTICSEARCH_HOST', 'localhost')}:{os.getenv('ELASTICSEARCH_PORT', '9200')}"
    )
    
    # ==================== Prometheus ====================
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    
    # ==================== Redis ====================
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_url: str = os.getenv(
        "REDIS_URL",
        f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}"
    )
    # Redis databases for different purposes
    redis_cache_db: int = int(os.getenv("REDIS_CACHE_DB", "1"))
    redis_streams_db: int = int(os.getenv("REDIS_STREAMS_DB", "2"))
    redis_notifications_db: int = int(os.getenv("REDIS_NOTIFICATIONS_DB", "3"))
    
    # ==================== Milvus ====================
    milvus_host: str = os.getenv("MILVUS_HOST", "localhost")
    milvus_port: int = int(os.getenv("MILVUS_PORT", "19530"))
    
    # ==================== AI / LLM ====================
    # Primary: OpenAI-совместимый API
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    
    # Fallback: Ollama (локальная LLM)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    ollama_enabled: bool = os.getenv("OLLAMA_ENABLED", "true").lower() == "true"
    
    # Cache TTLs (seconds)
    cache_ttl_analysis: int = int(os.getenv("CACHE_TTL_ANALYSIS", "600"))
    cache_ttl_playbook: int = int(os.getenv("CACHE_TTL_PLAYBOOK", "1800"))
    cache_ttl_nl: int = int(os.getenv("CACHE_TTL_NL", "300"))
    
    # Legacy endpoints (для обратной совместимости)
    llm_endpoint: str = os.getenv("LLM_ENDPOINT", "http://localhost:8080")
    chronos_endpoint: str = os.getenv("CHRONOS_ENDPOINT", "http://localhost:8081")
    
    # ==================== Circuit Breaker ====================
    circuit_breaker_failure_threshold: int = int(os.getenv("CB_FAILURE_THRESHOLD", "5"))
    circuit_breaker_timeout: int = int(os.getenv("CB_TIMEOUT", "60"))
    circuit_breaker_success_threshold: int = int(os.getenv("CB_SUCCESS_THRESHOLD", "2"))
    
    # ==================== Proxmox ====================
    proxmox_host: str = os.getenv("PROXMOX_HOST", "")
    proxmox_user: str = os.getenv("PROXMOX_USER", "root@pam")
    proxmox_token_name: str = os.getenv("PROXMOX_TOKEN_NAME", "")
    proxmox_token_value: str = os.getenv("PROXMOX_TOKEN_VALUE", "")
    proxmox_verify_ssl: bool = os.getenv("PROXMOX_VERIFY_SSL", "false").lower() == "true"
    
    # Алиасы для обратной совместимости (uppercase)
    PROXMOX_HOST: str = os.getenv("PROXMOX_HOST", "")
    PROXMOX_USER: str = os.getenv("PROXMOX_USER", "root@pam")
    PROXMOX_TOKEN_NAME: str = os.getenv("PROXMOX_TOKEN_NAME", "")
    PROXMOX_TOKEN_VALUE: str = os.getenv("PROXMOX_TOKEN_VALUE", "")
    
    # ==================== MikroTik ====================
    mikrotik_host: str = os.getenv("MIKROTIK_HOST", "")
    mikrotik_user: str = os.getenv("MIKROTIK_USER", "admin")
    mikrotik_password: str = os.getenv("MIKROTIK_PASSWORD", "")
    mikrotik_port: int = int(os.getenv("MIKROTIK_PORT", "8728"))
    
    # ==================== UniFi ====================
    unifi_host: str = os.getenv("UNIFI_HOST", "")
    unifi_user: str = os.getenv("UNIFI_USER", "admin")
    unifi_password: str = os.getenv("UNIFI_PASSWORD", "")
    unifi_site: str = os.getenv("UNIFI_SITE", "default")
    
    # ==================== Ansible ====================
    ansible_inventory_path: str = os.getenv("ANSIBLE_INVENTORY_PATH", "/etc/ansible/hosts")
    ansible_playbook_dir: str = os.getenv("ANSIBLE_PLAYBOOK_DIR", "/app/data/playbooks")
    PLAYBOOKS_DIR: str = os.getenv("ANSIBLE_PLAYBOOK_DIR", "/app/data/playbooks")
    
    # ==================== Database ====================
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./aiops.db")
    
    # ==================== Notifications ====================
    # Email (SMTP)
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")
    
    # Slack
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    slack_channel: str = os.getenv("SLACK_CHANNEL", "#alerts")
    
    # PagerDuty
    pagerduty_routing_key: str = os.getenv("PAGERDUTY_ROUTING_KEY", "")
    pagerduty_service_id: str = os.getenv("PAGERDUTY_SERVICE_ID", "")
    
    # Custom Webhook
    custom_webhook_url: str = os.getenv("CUSTOM_WEBHOOK_URL", "")
    
    # ==================== Alertmanager ====================
    alertmanager_url: str = os.getenv("ALERTMANAGER_URL", "http://localhost:9093")
    alertmanager_webhook_enabled: bool = os.getenv("ALERTMANAGER_WEBHOOK_ENABLED", "true").lower() == "true"
    
    # ==================== Streaming ====================
    streaming_enabled: bool = os.getenv("STREAMING_ENABLED", "true").lower() == "true"
    streaming_batch_size: int = int(os.getenv("STREAMING_BATCH_SIZE", "100"))
    streaming_flush_interval: int = int(os.getenv("STREAMING_FLUSH_INTERVAL", "5"))
    
    # ==================== System ====================
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "development")
    
    # ==================== Feature Flags ====================
    enable_auto_remediation: bool = os.getenv("ENABLE_AUTO_REMEDIATION", "false").lower() == "true"
    enable_chatbot_nl: bool = os.getenv("ENABLE_CHATBOT_NL", "true").lower() == "true"
    enable_llm_fallback: bool = os.getenv("ENABLE_LLM_FALLBACK", "true").lower() == "true"
    enable_caching: bool = os.getenv("ENABLE_CACHING", "true").lower() == "true"
    enable_notifications: bool = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Глобальный экземпляр настроек
settings = Settings()


def get_settings() -> Settings:
    """Возвращает экземпляр настроек."""
    return settings
