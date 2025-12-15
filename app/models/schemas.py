"""
Pydantic модели для API
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class SeverityLevel(str, Enum):
    """Уровни серьезности проблем"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ActionStatus(str, Enum):
    """Статусы действий"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"

class LogAnalysisResult(BaseModel):
    """Результат анализа логов"""
    summary: str
    root_cause: str
    severity: SeverityLevel
    relevant_logs: List[str]
    timestamp: datetime = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "summary": "Database connection refused",
                "root_cause": "PostgreSQL service is down",
                "severity": "critical",
                "relevant_logs": ["ERROR: connection refused at 10:30:45"],
                "timestamp": "2025-12-15T10:30:45"
            }
        }

class MetricsAnomalyResult(BaseModel):
    """Результат анализа метрик"""
    metric_name: str
    current_value: float
    expected_range: tuple
    anomaly_score: float
    description: str
    timestamp: datetime = None

class RemediationPlan(BaseModel):
    """План исправления проблемы"""
    plan_id: str
    title: str
    description: str
    severity: SeverityLevel
    playbook_yaml: str
    estimated_duration: int  # в секундах
    status: ActionStatus = ActionStatus.PENDING
    created_at: datetime = None
    approved_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    execution_result: Optional[str] = None

class AnalysisRequest(BaseModel):
    """Запрос на анализ"""
    service_name: str
    time_window: str = "15m"
    include_logs: bool = True
    include_metrics: bool = True

class ApprovalRequest(BaseModel):
    """Запрос на утверждение плана"""
    plan_id: str
    approved: bool
    reason: Optional[str] = None

class SystemStatus(BaseModel):
    """Статус системы"""
    api_status: str
    elasticsearch_status: str
    prometheus_status: str
    redis_status: str
    pending_actions: int
    recent_anomalies: int
    timestamp: datetime = None
