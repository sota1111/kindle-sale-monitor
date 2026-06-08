from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SaleHistoryResponse(BaseModel):
    id: int
    book_id: int
    volume: Optional[str] = None
    sale_type: Optional[str] = None
    discount_rate: Optional[int] = None
    point_rate: Optional[int] = None
    cashback_info: Optional[str] = None
    price: Optional[int] = None
    effective_price: Optional[int] = None
    is_free: bool
    is_cheapest: bool
    is_high_return: bool
    categories: Optional[str] = None
    tags: Optional[str] = None
    display_text: Optional[str] = None
    amazon_url: Optional[str] = None
    sale_bon_url: Optional[str] = None
    fetched_at: datetime
    notified: bool

    class Config:
        from_attributes = True
