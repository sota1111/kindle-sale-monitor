from fastapi import APIRouter, BackgroundTasks

router = APIRouter(prefix="/api/check", tags=["check"])


def _run_check_background(_unused=None):
    from app.database import SessionLocal
    from app.services.checker import run_check_all

    db = SessionLocal()
    try:
        run_check_all(db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Background check failed: {e}")
    finally:
        db.close()


@router.post("", status_code=202)
def manual_check(background_tasks: BackgroundTasks):
    """手動チェック実行。バックグラウンドで実行。"""
    background_tasks.add_task(_run_check_background)
    return {"message": "Check started"}


@router.post("/all", status_code=202)
def check_all(background_tasks: BackgroundTasks):
    """全件チェック実行。"""
    background_tasks.add_task(_run_check_background)
    return {"message": "Full check started"}
