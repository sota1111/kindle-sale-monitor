import traceback
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.checker import run_check_all

router = APIRouter(prefix="/run", tags=["run"])

@router.post("")
def run_check(db: Session = Depends(get_db)):
    """
    Cloud Scheduler等から呼び出される実行用エンドポイント。
    同期的にチェックを実行し、結果を返す。
    """
    try:
        result = run_check_all(db)
        return result
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "detail": traceback.format_exc()
            }
        )
