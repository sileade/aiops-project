import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class AGIHistory(Base):
    __tablename__ = "agi_history"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    cycle_id = Column(Integer, ForeignKey("cycles.id"))
    event_type = Column(String)
    details = Column(JSON)

    cycle = relationship("Cycle", back_populates="agi_events")
