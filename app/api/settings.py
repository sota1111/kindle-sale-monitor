from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.settings import AppSettings
from app.schemas.settings import SettingResponse, SettingUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULT_SETTINGS = {
    "check_interval_hours": "12",
    "request_interval_seconds": "2",
    "request_timeout_seconds": "30",
    "max_retries": "3",
}


def _ensure_defaults(db: Session):
    for key, value in DEFAULT_SETTINGS.items():
        if not db.query(AppSettings).filter(AppSettings.key == key).first():
            db.add(AppSettings(key=key, value=value))
    db.commit()


@router.get("", response_model=list[SettingResponse])
def list_settings(db: Session = Depends(get_db)):
    _ensure_defaults(db)
    return db.query(AppSettings).all()


@router.put("/{key}", response_model=SettingResponse)
def update_setting(key: str, update: SettingUpdate, db: Session = Depends(get_db)):
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if not setting:
        setting = AppSettings(key=key, value=update.value)
        db.add(setting)
    else:
        setting.value = update.value
    db.commit()
    db.refresh(setting)
    return setting
