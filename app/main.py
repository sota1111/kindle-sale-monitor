import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api import books, check, history, settings
from app.config import settings as app_settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import Book, ErrorLog, NotificationHistory, SaleHistory

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
            int(interval_setting.value) if interval_setting else app_settings.check_interval_hours
        )
    finally:
        db.close()
    start_scheduler(app, interval_hours=interval_hours)
    yield
    # Shutdown
    from app.services.scheduler import stop_scheduler

    stop_scheduler()


app = FastAPI(title="Kindle Sale Monitor", version="1.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory="app/templates")

app.include_router(books.router)
app.include_router(check.router)
app.include_router(history.router)
app.include_router(settings.router)


@app.get("/api/health")
def health():
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
def books_page(request: Request, enabled: str = None, db: Session = Depends(get_db)):
    query = db.query(Book)
    if enabled == "true":
        query = query.filter(Book.enabled.is_(True))
    elif enabled == "false":
        query = query.filter(Book.enabled.is_(False))
    book_list = query.all()
    return templates.TemplateResponse(request, "books.html", {"books": book_list})


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
    return templates.TemplateResponse(request, "book_detail.html", {"book": book, "sales": sales})


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
            update_interval(int(interval_val))
    except Exception:
        pass
    return RedirectResponse(url="/settings", status_code=303)



@app.get("/errors", response_class=HTMLResponse)
def error_logs_page(request: Request, db: Session = Depends(get_db)):
    errors = db.query(ErrorLog).order_by(ErrorLog.occurred_at.desc()).limit(100).all()
    return templates.TemplateResponse(request, "error_logs.html", {"errors": errors})
