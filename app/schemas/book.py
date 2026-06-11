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


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    amazon_url: Optional[str] = None
    asin: Optional[str] = None
    sale_bon_url: Optional[str] = None
    target_volumes: Optional[str] = None
    series_watch: Optional[bool] = None
    note: Optional[str] = None
    enabled: Optional[bool] = None
    notify_on_cheapest: Optional[bool] = None
    notify_on_high_return: Optional[bool] = None
    notify_on_free: Optional[bool] = None
    notify_on_cashback: Optional[bool] = None
    notify_discount_threshold: Optional[int] = None
    notify_return_threshold: Optional[int] = None
    notify_price_threshold: Optional[int] = None


class BookResponse(BookCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
