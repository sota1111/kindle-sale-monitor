import logging

from fastapi import Depends, FastAPI, Request, Form, HTTPException
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

app = FastAPI(title="Kindle Sale Monitor", version="1.0.0")
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
    pending_count = db.query(SaleHistory).filter(SaleHistory.notified == False).count()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "book_count": book_count, "pending_count": pending_count},
    )


@app.get("/books", response_class=HTMLResponse)
def books_page(request: Request, enabled: str = None, db: Session = Depends(get_db)):
    query = db.query(Book)
    if enabled == "true":
        query = query.filter(Book.enabled == True)
    elif enabled == "false":
        query = query.filter(Book.enabled == False)
    book_list = query.all()
    return templates.TemplateResponse("books.html", {"request": request, "books": book_list})


@app.get("/books/new", response_class=HTMLResponse)
def book_new_page(request: Request):
    return templates.TemplateResponse("book_form.html", {"request": request, "book": None, "title": "本を登録"})


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
    return templates.TemplateResponse(
        "book_detail.html", {"request": request, "book": book, "sales": sales}
    )


@app.get("/books/{book_id}/edit", response_class=HTMLResponse)
def book_edit_page(book_id: int, request: Request, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return templates.TemplateResponse("book_form.html", {"request": request, "book": book, "title": "本を編集"})


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
    return templates.TemplateResponse("sale_history.html", {"request": request, "sales": sales})


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    notifs = (
        db.query(NotificationHistory)
        .order_by(NotificationHistory.notified_at.desc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(
        "notifications.html", {"request": request, "notifications": notifs}
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    from app.models.settings import AppSettings
    setting_list = db.query(AppSettings).all()
    return templates.TemplateResponse(
        "settings.html", {"request": request, "settings": setting_list}
    )


@app.get("/errors", response_class=HTMLResponse)
def error_logs_page(request: Request, db: Session = Depends(get_db)):
    errors = db.query(ErrorLog).order_by(ErrorLog.occurred_at.desc()).limit(100).all()
    return templates.TemplateResponse("error_logs.html", {"request": request, "errors": errors})
