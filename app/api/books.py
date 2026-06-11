import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.book import Book
from app.models.notification_condition import NotificationCondition
from app.schemas.book import BookCreate, BookResponse, BookUpdate
from app.schemas.notification_condition import (
    NotificationConditionCreate,
    NotificationConditionResponse,
    NotificationConditionUpdate,
)

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("", response_model=list[BookResponse])
def list_books(enabled: Optional[bool] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Book)
    if enabled is not None:
        query = query.filter(Book.enabled == enabled)
    return query.all()


@router.post("", response_model=BookResponse, status_code=201)
def create_book(book: BookCreate, db: Session = Depends(get_db)):
    db_book = Book(**book.model_dump())
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book


@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.put("/{book_id}", response_model=BookResponse)
def update_book(book_id: int, book_update: BookUpdate, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    update_data = book_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(book, key, value)
    db.commit()
    db.refresh(book)
    return book


@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    db.delete(book)
    db.commit()


@router.get("/{book_id}/conditions", response_model=list[NotificationConditionResponse])
def list_conditions(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    conditions = (
        db.query(NotificationCondition)
        .filter(NotificationCondition.book_id == book_id)
        .all()
    )
    return [NotificationConditionResponse.model_validate(c) for c in conditions]


@router.post("/{book_id}/conditions", response_model=NotificationConditionResponse, status_code=201)
def create_condition(
    book_id: int, condition: NotificationConditionCreate, db: Session = Depends(get_db)
):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    data = condition.model_dump()
    if data.get("volume_filter") is not None:
        data["volume_filter"] = json.dumps(data["volume_filter"], ensure_ascii=False)
    db_condition = NotificationCondition(book_id=book_id, **data)
    db.add(db_condition)
    db.commit()
    db.refresh(db_condition)
    return NotificationConditionResponse.model_validate(db_condition)


@router.put(
    "/{book_id}/conditions/{condition_id}", response_model=NotificationConditionResponse
)
def update_condition(
    book_id: int,
    condition_id: int,
    condition_update: NotificationConditionUpdate,
    db: Session = Depends(get_db),
):
    condition = (
        db.query(NotificationCondition)
        .filter(
            NotificationCondition.id == condition_id,
            NotificationCondition.book_id == book_id,
        )
        .first()
    )
    if not condition:
        raise HTTPException(status_code=404, detail="Condition not found")
    update_data = condition_update.model_dump(exclude_unset=True)
    if "volume_filter" in update_data and update_data["volume_filter"] is not None:
        update_data["volume_filter"] = json.dumps(
            update_data["volume_filter"], ensure_ascii=False
        )
    for key, value in update_data.items():
        setattr(condition, key, value)
    db.commit()
    db.refresh(condition)
    return NotificationConditionResponse.model_validate(condition)


@router.delete("/{book_id}/conditions/{condition_id}", status_code=204)
def delete_condition(book_id: int, condition_id: int, db: Session = Depends(get_db)):
    condition = (
        db.query(NotificationCondition)
        .filter(
            NotificationCondition.id == condition_id,
            NotificationCondition.book_id == book_id,
        )
        .first()
    )
    if not condition:
        raise HTTPException(status_code=404, detail="Condition not found")
    db.delete(condition)
    db.commit()
