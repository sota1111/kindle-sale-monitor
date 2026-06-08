from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SaleHistory(Base):
    __tablename__ = "sale_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), index=True)
    volume: Mapped[str | None] = mapped_column(Text)
    sale_type: Mapped[str | None] = mapped_column(Text)
    discount_rate: Mapped[int | None] = mapped_column(Integer)
    point_rate: Mapped[int | None] = mapped_column(Integer)
    cashback_info: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int | None] = mapped_column(Integer)
    effective_price: Mapped[int | None] = mapped_column(Integer)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cheapest: Mapped[bool] = mapped_column(Boolean, default=False)
    is_high_return: Mapped[bool] = mapped_column(Boolean, default=False)
    categories: Mapped[str | None] = mapped_column(Text)  # JSON array
    tags: Mapped[str | None] = mapped_column(Text)  # JSON array
    display_text: Mapped[str | None] = mapped_column(Text)
    amazon_url: Mapped[str | None] = mapped_column(Text)
    sale_bon_url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    notified: Mapped[bool] = mapped_column(Boolean, default=False)

    book = relationship("Book", backref="sale_histories")
