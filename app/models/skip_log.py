from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SkipLog(Base):
    __tablename__ = "skip_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    sale_history_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sale_history.id", ondelete="SET NULL")
    )
    skip_reason: Mapped[str] = mapped_column(Text, nullable=False)
    skipped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    book = relationship("Book", backref="skip_logs")
    sale_history = relationship("SaleHistory", backref="skip_logs")
