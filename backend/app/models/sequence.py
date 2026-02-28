from sqlalchemy import Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CaseSequence(Base):
    __tablename__ = "case_sequence"

    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
