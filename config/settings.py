"""
Конфигурация приложения AIOps
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Основные настройки приложения"""
    
    # Telegram
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    admin_chat_id: int = int(os.getenv("ADMIN_CHAT_ID", "0"))
    
    # API Server
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_debug: bool = os.getenv("API_DEBUG", "true").lower() == "true"
    
    # Elasticsearch
    elasticsearch_host: str = os.getenv("ELASTICSEARCH_HOST", "localhost")
    elasticsearch_port: int = int(os.getenv("ELASTICSEARCH_PORT", "9200"))
    
    # Prometheus
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    
    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    
    # Milvus
    milvus_host: str = os.getenv("MILVUS_HOST", "localhost")
    milvus_port: int = int(os.getenv("MILVUS_PORT", "19530"))
    
    # AI Models
    llm_endpoint: str = os.getenv("LLM_ENDPOINT", "http://localhost:8080")
    chronos_endpoint: str = os.getenv("CHRONOS_ENDPOINT", "http://localhost:8081")
    
    # Ansible
    ansible_inventory_path: str = os.getenv("ANSIBLE_INVENTORY_PATH", "/etc/ansible/hosts")
    ansible_playbook_dir: str = os.getenv("ANSIBLE_PLAYBOOK_DIR", "/app/data/playbooks")
    
    # System
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./aiops.db")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
