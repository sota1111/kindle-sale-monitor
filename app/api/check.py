from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/api/check", tags=["check"])


@router.post("", status_code=202)
def manual_check(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """手動チェック実行（全件）。バックグラウンドで実行。"""
    from app.services.checker import run_check_all
    background_tasks.add_task(run_check_all, db)
    return {"message": "Check started"}


@router.post("/all", status_code=202)
def check_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """全件チェック実行。"""
    from app.services.checker import run_check_all
    background_tasks.add_task(run_check_all, db)
    return {"message": "Full check started"}
