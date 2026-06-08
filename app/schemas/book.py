from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BookCreate(BaseModel):
    title: str
    author: Optional[str] = None
    publisher: Optional[str] = None
    amazon_url: Optional[str] = None
    asin: Optional[str] = None
    sale_bon_url: Optional[str] = None
    target_volumes: Optional[str] = None
    series_watch: bool = False
    note: Optional[str] = None
    enabled: bool = True
    notify_on_cheapest: bool = True
    notify_on_high_return: bool = True
    notify_on_free: bool = True
    notify_on_cashback: bool = True
    notify_discount_threshold: Optional[int] = None
    notify_return_threshold: Optional[int] = None
    notify_price_threshold: Optional[int] = None


class BookUpdate(BookCreate):
    title: Optional[str] = None


class BookResponse(BookCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
