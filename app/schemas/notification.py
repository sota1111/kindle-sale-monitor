from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationHistoryResponse(BaseModel):
    id: int
    book_id: int
    sale_history_id: Optional[int] = None
    reason: Optional[str] = None
    notified_at: datetime
    success: bool
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
