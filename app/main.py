import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api import books, check, history, run, settings
from app.api import scheduler as scheduler_api
from app.auth import AuthMiddleware
from app.config import settings as app_settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import (
    Book,
    ErrorLog,
    NotificationCondition,
    NotificationHistory,
    SaleHistory,
    SkipLog,
)

logging.basicConfig(
    level=getattr(logging, app_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)

Base.metadata.create_all(bind=engine)


def _init_default_settings():
    db = SessionLocal()
    try:
        from app.models.settings import AppSettings

        defaults = {
            "check_interval_hours": "12",
            "request_interval_seconds": "2",
            "request_timeout_seconds": "30",
            "max_retries": "3",
        }
        for key, value in defaults.items():
            if not db.query(AppSettings).filter(AppSettings.key == key).first():
                db.add(AppSettings(key=key, value=value))
        db.commit()
    finally:
        db.close()


_init_default_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.models.settings import AppSettings
    from app.services.scheduler import start_scheduler

    db = SessionLocal()
    try:
        interval_setting = (
            db.query(AppSettings).filter(AppSettings.key == "check_interval_hours").first()
        )
        interval_hours = (
            int(interval_setting.value)
            if interval_setting and interval_setting.value
            else app_settings.check_interval_hours
        )
    finally:
        db.close()
    start_scheduler(app, interval_hours=interval_hours)
    yield
    # Shutdown
    from app.services.scheduler import stop_scheduler

    stop_scheduler()


app = FastAPI(title="Kindle Sale Monitor", version="1.0.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("AUTH_SECRET", "change-this-secret"),
    https_only=True,
    same_site="lax",
)
templates = Jinja2Templates(directory="app/templates")

app.include_router(books.router)
app.include_router(check.router)
app.include_router(history.router)
app.include_router(settings.router)
app.include_router(run.router)
app.include_router(scheduler_api.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    book_count = db.query(Book).count()
    pending_count = db.query(SaleHistory).filter(SaleHistory.notified.is_(False)).count()
    recent_sales = db.query(SaleHistory).order_by(SaleHistory.fetched_at.desc()).limit(5).all()
    recent_notifications = (
        db.query(NotificationHistory)
        .order_by(NotificationHistory.notified_at.desc())
        .limit(5)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "book_count": book_count,
            "pending_count": pending_count,
            "recent_sales": recent_sales,
            "recent_notifications": recent_notifications,
        },
    )


@app.get("/books", response_class=HTMLResponse)
def books_page(request: Request, enabled: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Book)
    if enabled == "true":
        query = query.filter(Book.enabled.is_(True))
    elif enabled == "false":
        query = query.filter(Book.enabled.is_(False))
    books = query.all()

    # Add condition summaries to books
    book_ids = [b.id for b in books]
    conditions_raw = (
        db.query(NotificationCondition).filter(NotificationCondition.book_id.in_(book_ids)).all()
    )
    condition_map: dict = {}
    for c in conditions_raw:
        if c.book_id not in condition_map:
            condition_map[c.book_id] = []
        # Build a simple summary string
        parts = []
        if c.min_discount_rate is not None:
            parts.append(f"{c.min_discount_rate}%以上OFF")
        if c.cashback_only:
            parts.append("CB対象")
        if c.cheapest_only:
            parts.append("過去最安")
        if c.free_only:
            parts.append("無料")
        condition_map[c.book_id].append(" / ".join(parts) if parts else "条件なし")

    # Attach condition_summary to each book as a simple attribute
    for book in books:
        setattr(book, "condition_summary", " | ".join(condition_map.get(book.id, [])) or None)

    return templates.TemplateResponse(request, "books.html", {"books": books})


@app.get("/books/new", response_class=HTMLResponse)
def book_new_page(request: Request):
    return templates.TemplateResponse(
        request, "book_form.html", {"book": None, "title": "本を登録"}
    )


@app.post("/books/new")
def book_create_form(
    request: Request,
    title: str = Form(...),
    author: str = Form(""),
    publisher: str = Form(""),
    amazon_url: str = Form(""),
    asin: str = Form(""),
    sale_bon_url: str = Form(""),
    note: str = Form(""),
    series_watch: bool = Form(False),
    db: Session = Depends(get_db),
):
    from app.models.book import Book

    book = Book(
        title=title,
        author=author or None,
        publisher=publisher or None,
        amazon_url=amazon_url or None,
        asin=asin or None,
        sale_bon_url=sale_bon_url or None,
        note=note or None,
        series_watch=series_watch,
    )
    db.add(book)
    db.commit()
    return RedirectResponse(url="/books", status_code=303)


@app.get("/books/{book_id}", response_class=HTMLResponse)
def book_detail_page(book_id: int, request: Request, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    sales = (
        db.query(SaleHistory)
        .filter(SaleHistory.book_id == book_id)
        .order_by(SaleHistory.fetched_at.desc())
        .limit(50)
        .all()
    )
    conditions = (
        db.query(NotificationCondition).filter(NotificationCondition.book_id == book_id).all()
    )
    return templates.TemplateResponse(
        request, "book_detail.html", {"book": book, "sales": sales, "conditions": conditions}
    )


@app.get("/books/{book_id}/edit", response_class=HTMLResponse)
def book_edit_page(book_id: int, request: Request, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return templates.TemplateResponse(
        request, "book_form.html", {"book": book, "title": "本を編集"}
    )


@app.post("/books/{book_id}/edit")
def book_update_form(
    book_id: int,
    request: Request,
    title: str = Form(...),
    author: str = Form(""),
    publisher: str = Form(""),
    amazon_url: str = Form(""),
    asin: str = Form(""),
    sale_bon_url: str = Form(""),
    note: str = Form(""),
    series_watch: bool = Form(False),
    enabled: bool = Form(True),
    db: Session = Depends(get_db),
):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    book.title = title
    book.author = author or None
    book.publisher = publisher or None
    book.amazon_url = amazon_url or None
    book.asin = asin or None
    book.sale_bon_url = sale_bon_url or None
    book.note = note or None
    book.series_watch = series_watch
    book.enabled = enabled
    db.commit()
    return RedirectResponse(url=f"/books/{book_id}", status_code=303)


@app.post("/books/{book_id}/delete")
def book_delete_form(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if book:
        db.delete(book)
        db.commit()
    return RedirectResponse(url="/books", status_code=303)


@app.get("/sales", response_class=HTMLResponse)
def sales_page(request: Request, db: Session = Depends(get_db)):
    sales = db.query(SaleHistory).order_by(SaleHistory.fetched_at.desc()).limit(100).all()
    return templates.TemplateResponse(request, "sale_history.html", {"sales": sales})


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    notifs = (
        db.query(NotificationHistory)
        .order_by(NotificationHistory.notified_at.desc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(request, "notifications.html", {"notifications": notifs})


@app.get("/monitoring", response_class=HTMLResponse)
def monitoring_page(request: Request, db: Session = Depends(get_db)):
    logs = db.query(SkipLog).order_by(SkipLog.skipped_at.desc()).limit(100).all()
    return templates.TemplateResponse(request, "monitoring_history.html", {"logs": logs})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    from app.models.settings import AppSettings

    setting_list = db.query(AppSettings).all()
    return templates.TemplateResponse(request, "settings.html", {"settings": setting_list})


@app.post("/settings")
async def settings_update_form(request: Request, db: Session = Depends(get_db)):
    from app.models.settings import AppSettings

    form_data = await request.form()
    for key, value in form_data.items():
        setting = db.query(AppSettings).filter(AppSettings.key == key).first()
        if setting:
            setting.value = str(value)
        else:
            db.add(AppSettings(key=key, value=str(value)))
    db.commit()
    try:
        from app.services.scheduler import update_interval

        interval_val = form_data.get("check_interval_hours")
        if interval_val:
            update_interval(int(str(interval_val)))
    except Exception:
        pass
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/errors", response_class=HTMLResponse)
def error_logs_page(request: Request, db: Session = Depends(get_db)):
    errors = db.query(ErrorLog).order_by(ErrorLog.occurred_at.desc()).limit(100).all()
    return templates.TemplateResponse(request, "error_logs.html", {"errors": errors})


# Identity Toolkit REST endpoint for server-side email/password verification (案1).
# The browser never talks to Firebase directly; the server verifies credentials
# using the Firebase Web API key held server-side.
IDENTITY_TOOLKIT_SIGNIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)
_INVALID_CREDENTIALS_MSG = "メールアドレスまたはパスワードが正しくありません"


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    # Double-submit CSRF token: set as a non-HttpOnly cookie so the login script
    # can read it and echo it back in the X-CSRF-Token header.
    csrf_token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse(request, "login.html", {"csrf_token": csrf_token})
    response.set_cookie(
        "csrf_token",
        csrf_token,
        max_age=3600,
        httponly=False,
        secure=True,
        samesite="lax",
    )
    return response


@app.post("/session")
async def create_session(request: Request):
    # CSRF check (double-submit cookie): the cookie set on /login must match the
    # value echoed back in the X-CSRF-Token header.
    cookie_token = request.cookies.get("csrf_token", "")
    header_token = request.headers.get("x-csrf-token", "")
    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
    ):
        return JSONResponse(content={"error": "Invalid CSRF token"}, status_code=403)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": _INVALID_CREDENTIALS_MSG}, status_code=401)

    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    if not email or not password:
        return JSONResponse(content={"error": _INVALID_CREDENTIALS_MSG}, status_code=401)

    api_key = os.environ.get("FIREBASE_API_KEY", "")
    if not api_key:
        logging.error("FIREBASE_API_KEY is not configured")
        return JSONResponse(content={"error": "サーバ設定エラーです"}, status_code=500)

    # Verify credentials server-side. Never log the password or request body.
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            resp = await http_client.post(
                IDENTITY_TOOLKIT_SIGNIN_URL,
                params={"key": api_key},
                json={"email": email, "password": password, "returnSecureToken": True},
            )
    except httpx.HTTPError:
        logging.warning("Identity Toolkit request failed during login")
        return JSONResponse(
            content={"error": "認証サービスに接続できませんでした"}, status_code=503
        )

    if resp.status_code != 200:
        error_code = ""
        try:
            error_code = resp.json().get("error", {}).get("message", "")
        except Exception:
            error_code = ""
        if error_code.startswith("TOO_MANY_ATTEMPTS_TRY_LATER"):
            return JSONResponse(
                content={"error": "ログイン試行が多すぎます。しばらく待ってから再試行してください"},
                status_code=401,
            )
        return JSONResponse(content={"error": _INVALID_CREDENTIALS_MSG}, status_code=401)

    verified_email = (resp.json().get("email") or email).strip()

    allowed_emails_str = os.environ.get("ALLOWED_USER_EMAILS", "")
    allowed_emails = [e.strip() for e in allowed_emails_str.split(",") if e.strip()]
    if allowed_emails and verified_email not in allowed_emails:
        return JSONResponse(
            content={"error": "このメールアドレスは許可されていません"}, status_code=403
        )

    request.session["user"] = verified_email
    return JSONResponse(content={"success": True, "email": verified_email})


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
