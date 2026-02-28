import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SlaConfig(Base):
    __tablename__ = "sla_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    priority: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    temp_fix_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    permanent_fix_days: Mapped[int] = mapped_column(Integer, nullable=False)
    overdue_t1_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    overdue_t2_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    overdue_t3_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    overdue_t4_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
