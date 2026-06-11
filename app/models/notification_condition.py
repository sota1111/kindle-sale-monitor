from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotificationCondition(Base):
    __tablename__ = "notification_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(Text)
    min_discount_rate: Mapped[int | None] = mapped_column(Integer)
    cashback_only: Mapped[bool] = mapped_column(Boolean, default=False)
    min_cashback_rate: Mapped[int | None] = mapped_column(Integer)
    volume_filter: Mapped[str | None] = mapped_column(Text)  # JSON array string e.g. '["1","2","3"]'
    cheapest_only: Mapped[bool] = mapped_column(Boolean, default=False)
    free_only: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    book = relationship("Book", backref="notification_conditions")
