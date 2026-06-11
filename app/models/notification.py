from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotificationHistory(Base):
    __tablename__ = "notification_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), index=True)
    sale_history_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sale_history.id")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    notified_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    matched_conditions: Mapped[str | None] = mapped_column(Text)  # JSON array of matched reason strings

    book = relationship("Book", backref="notification_histories")
    sale_history = relationship("SaleHistory", backref="notification_histories")
