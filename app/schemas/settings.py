from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SettingResponse(BaseModel):
    key: str
    value: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class SettingUpdate(BaseModel):
    value: str
