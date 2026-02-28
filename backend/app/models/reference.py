import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RefServiceType(Base):
    __tablename__ = "ref_service_type"

    code: Mapped[str] = mapped_column(String(5), primary_key=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)


class RefComplaintType(Base):
    __tablename__ = "ref_complaint_type"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)


class RefClosureReason(Base):
    __tablename__ = "ref_closure_reason"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    label_th: Mapped[str] = mapped_column(String(200), nullable=False)
    requires_note: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RefHandler(Base):
    __tablename__ = "ref_handler"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
