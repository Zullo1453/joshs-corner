from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class JournalEntry(TimestampMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Note(TimestampMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="Untitled", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_favourite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Todo(TimestampMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GameJournal(TimestampMixin, db.Model):
    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating >= 0 AND rating <= 5)", name="game_rating_range"),
        CheckConstraint("hours_played IS NULL OR hours_played >= 0", name="game_hours_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Backlog", nullable=False)
    rating: Mapped[float | None] = mapped_column(Float)
    platform: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    hours_played: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    play_entries: Mapped[list["GamePlayEntry"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", passive_deletes=True
    )


class GamePlayEntry(TimestampMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(db.ForeignKey("game_journal.id", ondelete="CASCADE"), nullable=False, index=True)
    played_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    game: Mapped[GameJournal] = relationship(back_populates="play_entries")


class WatchlistItem(TimestampMixin, db.Model):
    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating >= 0 AND rating <= 5)", name="watch_rating_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Want to Watch", nullable=False)
    rating: Mapped[float | None] = mapped_column(Float)
    release_year: Mapped[int | None] = mapped_column()
    genre: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    recommendation_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class ReadingItem(TimestampMixin, db.Model):
    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating >= 0 AND rating <= 5)", name="reading_rating_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    format: Mapped[str] = mapped_column(String(10), default="Written", nullable=False)
    release_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="To Read", nullable=False)
    rating: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
