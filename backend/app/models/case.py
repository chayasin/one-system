import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Case(Base):
    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    source_channel: Mapped[str] = mapped_column(String(20), nullable=False)
    source_seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    service_type_code: Mapped[str] = mapped_column(String(5), nullable=False)
    complaint_type_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reporter_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    line_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    handler_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district_office: Mapped[str | None] = mapped_column(String(200), nullable=True)
    road_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gps_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    gps_lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expected_fix_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_officer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    overdue_tier: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    closure_reason_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_case_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    raw_extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class CaseHistory(Base):
    __tablename__ = "case_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    prev_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    prev_assigned_officer: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    new_assigned_officer: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    change_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CaseAttachment(Base):
    __tablename__ = "case_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[str] = mapped_column(String(20), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
