from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SummaryCasesDaily(Base):
    __tablename__ = "summary_cases_daily"

    summary_date: Mapped[date] = mapped_column(Date, primary_key=True)
    source_channel: Mapped[str] = mapped_column(String(20), primary_key=True)
    province: Mapped[str] = mapped_column(String(100), primary_key=True, default="")
    district_office: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    service_type_code: Mapped[str] = mapped_column(String(5), primary_key=True)
    complaint_type_code: Mapped[str] = mapped_column(String(10), primary_key=True, default="")
    priority: Mapped[str] = mapped_column(String(10), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), primary_key=True)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closed_within_sla: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_close_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
