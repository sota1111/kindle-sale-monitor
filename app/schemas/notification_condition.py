import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class NotificationConditionCreate(BaseModel):
    name: Optional[str] = None
    min_discount_rate: Optional[int] = None
    cashback_only: bool = False
    min_cashback_rate: Optional[int] = None
    volume_filter: Optional[list[str]] = None
    cheapest_only: bool = False
    free_only: bool = False


class NotificationConditionUpdate(BaseModel):
    name: Optional[str] = None
    min_discount_rate: Optional[int] = None
    cashback_only: Optional[bool] = None
    min_cashback_rate: Optional[int] = None
    volume_filter: Optional[list[str]] = None
    cheapest_only: Optional[bool] = None
    free_only: Optional[bool] = None


class NotificationConditionResponse(BaseModel):
    id: int
    book_id: int
    name: Optional[str] = None
    min_discount_rate: Optional[int] = None
    cashback_only: bool
    min_cashback_rate: Optional[int] = None
    volume_filter: Optional[list[str]] = None
    cheapest_only: bool
    free_only: bool
    summary: str = ""
    created_at: datetime
    updated_at: datetime

    @field_validator("volume_filter", mode="before")
    @classmethod
    def parse_volume_filter(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v

    @model_validator(mode="after")
    def compute_summary(self) -> "NotificationConditionResponse":
        parts = []
        if self.min_discount_rate is not None:
            parts.append(f"{self.min_discount_rate}%以上OFF")
        if self.cashback_only:
            parts.append("キャッシュバック対象")
        if self.min_cashback_rate is not None:
            parts.append(f"CB{self.min_cashback_rate}%以上")
        if self.volume_filter:
            if self.volume_filter == ["latest"]:
                parts.append("最新巻")
            else:
                parts.append(f"{'/'.join(self.volume_filter)}巻")
        if self.cheapest_only:
            parts.append("過去最安更新のみ")
        if self.free_only:
            parts.append("無料のみ")
        self.summary = " / ".join(parts) if parts else "条件なし（全通知）"
        return self

    model_config = {"from_attributes": True}
