from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class JobInfo(BaseModel):
    id: str
    next_run_time: Optional[datetime] = None
    trigger: str
    paused: bool


class RescheduleRequest(BaseModel):
    interval_hours: int
