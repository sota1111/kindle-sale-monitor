from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    amazon_url: Mapped[str | None] = mapped_column(Text)
    asin: Mapped[str | None] = mapped_column(Text)
    sale_bon_url: Mapped[str | None] = mapped_column(Text)
    target_volumes: Mapped[str | None] = mapped_column(Text)  # JSON array
    series_watch: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_cheapest: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_high_return: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_free: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_cashback: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_discount_threshold: Mapped[int | None] = mapped_column(Integer)
    notify_return_threshold: Mapped[int | None] = mapped_column(Integer)
    notify_price_threshold: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
