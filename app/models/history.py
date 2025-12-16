"""
Модели SQLAlchemy для хранения истории циклов AIOps.
"""

import uuid
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import enum

from app.database import Base

# --- Enums для статусов ---
class CycleStatus(enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REJECTED = "REJECTED"

class StepName(enum.Enum):
    DETECTION = "DETECTION"
    AI_ANALYSIS = "AI_ANALYSIS"
    PLAYBOOK_GENERATION = "PLAYBOOK_GENERATION"
    APPROVAL = "APPROVAL"
    EXECUTION = "EXECUTION"
    POST_ANALYSIS = "POST_ANALYSIS"
    VERIFICATION = "VERIFICATION"

class StepStatus(enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    SKIPPED = "SKIPPED"

# --- Основная таблица: RemediationCycle ---
class RemediationCycle(Base):
    __tablename__ = "remediation_cycles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(SQLAlchemyEnum(CycleStatus), default=CycleStatus.IN_PROGRESS)
    device_type = Column(String, nullable=False)
    device_host = Column(String, nullable=False)
    initial_problem = Column(String, nullable=False)
    final_summary = Column(String, nullable=True)

    # Связь с шагами цикла
    steps = relationship("CycleStep", back_populates="cycle", cascade="all, delete-orphan")
    agi_events = relationship("AGIHistory", back_populates="cycle", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RemediationCycle(id={self.id}, status={self.status})>"

# --- Таблица для шагов цикла: CycleStep ---
class CycleStep(Base):
    __tablename__ = "cycle_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("remediation_cycles.id"), nullable=False)
    step_name = Column(SQLAlchemyEnum(StepName), nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(SQLAlchemyEnum(StepStatus), default=StepStatus.PENDING)
    details = Column(JSON, nullable=True) # Хранение любой дополнительной информации

    # Связь с основным циклом
    cycle = relationship("RemediationCycle", back_populates="steps")

    def __repr__(self):
        return f"<CycleStep(name={self.step_name}, status={self.status})>"
