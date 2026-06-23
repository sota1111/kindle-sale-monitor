from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    book_count: int
    sale_record_count: int
    books_with_history: int
    on_sale_now: int
    all_time_low_hits: int
    avg_discount_rate: float


class PriceTrendPoint(BaseModel):
    fetched_at: datetime
    price: Optional[int] = None
    effective_price: Optional[int] = None


class PriceTrendSeries(BaseModel):
    book_id: int
    title: str
    points: list[PriceTrendPoint]
