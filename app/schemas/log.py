from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MonitorLogResponse(BaseModel):
    id: Optional[int] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    books_checked: int
    sales_found: int
    notified: int
    status: str
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
