from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

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
    notes: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_location: Mapped[str] = mapped_column(String(20), default="backlog", server_default="backlog", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", nullable=False, index=True)
    scheduled_date: Mapped[date | None] = mapped_column(Date, index=True)
    original_date: Mapped[date | None] = mapped_column(Date)
    carried_from_date: Mapped[date | None] = mapped_column(Date)
    carry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    rollover_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), index=True)
    project: Mapped["Project | None"] = relationship(back_populates="tasks")
    activities: Mapped[list["TodoActivity"]] = relationship(back_populates="todo")


class TodoActivity(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    todo_id: Mapped[int] = mapped_column(ForeignKey("todo.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    source_date: Mapped[date | None] = mapped_column(Date, index=True)
    destination_date: Mapped[date | None] = mapped_column(Date, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    todo: Mapped[Todo] = relationship(back_populates="activities")


class Project(TimestampMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    target_date: Mapped[date | None] = mapped_column(Date, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tasks: Mapped[list[Todo]] = relationship(back_populates="project")
    activities: Mapped[list["ProjectActivity"]] = relationship(back_populates="project")


class ProjectActivity(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    todo_id: Mapped[int | None] = mapped_column(ForeignKey("todo.id"), index=True)
    source_date: Mapped[date | None] = mapped_column(Date, index=True)
    destination_date: Mapped[date | None] = mapped_column(Date, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    project: Mapped[Project] = relationship(back_populates="activities")
    todo: Mapped[Todo | None] = relationship()


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
        CheckConstraint(
            "book_type IS NULL OR book_type IN ('fiction', 'non_fiction')",
            name="reading_book_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    format: Mapped[str] = mapped_column(String(10), default="Written", nullable=False)
    book_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="To Read", nullable=False)
    rating: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Attachment(db.Model):
    """A locally stored image linked to one rich-text record or a draft token."""

    __table_args__ = (
        CheckConstraint("file_size >= 0", name="attachment_file_size_nonnegative"),
        CheckConstraint("width > 0", name="attachment_width_positive"),
        CheckConstraint("height > 0", name="attachment_height_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(40), default="draft", nullable=False, index=True)
    owner_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    draft_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stored_filename: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Automation(TimestampMixin, db.Model):
    """Generic automation metadata; provider-specific settings belong in later stages."""

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'archived')",
            name="automation_status_valid",
        ),
    )

    VALID_STATUSES = frozenset({"active", "paused", "archived"})

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    automation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active", nullable=False, index=True
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    runs: Mapped[list["AutomationRun"]] = relationship(
        back_populates="automation", cascade="all, delete-orphan"
    )
    flight_tracker: Mapped["FlightTracker | None"] = relationship(
        back_populates="automation", uselist=False, cascade="all, delete-orphan"
    )

    @validates("status")
    def validate_status(self, _key, value):
        if value not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported automation status: {value}")
        return value


class AutomationRun(db.Model):
    """A minimal, local record of a future automation execution."""

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="automation_run_status_valid",
        ),
    )

    VALID_STATUSES = frozenset({"running", "succeeded", "failed"})

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("automation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="", server_default="", nullable=False)
    configuration_version: Mapped[int | None] = mapped_column(Integer, index=True)
    automation: Mapped[Automation] = relationship(back_populates="runs")
    offers: Mapped[list["FlightOffer"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    @validates("status")
    def validate_status(self, _key, value):
        if value not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported automation run status: {value}")
        return value


class FlightTracker(TimestampMixin, db.Model):
    """The flight-specific configuration attached to one generic automation.

    ``configuration_version`` advances only for material search changes: routes,
    dates, or cabin class. Price and quality preferences keep the same series.
    """

    __table_args__ = (
        CheckConstraint("adults >= 1 AND adults <= 9", name="flight_tracker_adults_valid"),
        CheckConstraint("target_price_cents > 0", name="flight_tracker_target_positive"),
        CheckConstraint(
            "primary_max_duration_minutes > 0 AND primary_max_duration_minutes <= 10080",
            name="flight_tracker_duration_valid",
        ),
        CheckConstraint("primary_max_stops >= 0 AND primary_max_stops <= 6", name="flight_tracker_stops_valid"),
        CheckConstraint(
            "cabin_class IN ('economy', 'premium_economy', 'business', 'first')",
            name="flight_tracker_cabin_valid",
        ),
        CheckConstraint("configuration_version >= 1", name="flight_tracker_config_version_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("automation.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    outbound_origin: Mapped[str] = mapped_column(String(3), nullable=False)
    outbound_destination: Mapped[str] = mapped_column(String(3), nullable=False)
    outbound_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    return_origin: Mapped[str] = mapped_column(String(3), nullable=False)
    return_destination: Mapped[str] = mapped_column(String(3), nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    adults: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    cabin_class: Mapped[str] = mapped_column(String(24), default="economy", server_default="economy", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="AUD", server_default="AUD", nullable=False)
    target_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_max_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_max_stops: Mapped[int] = mapped_column(Integer, nullable=False)
    secondary_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    configuration_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    automation: Mapped[Automation] = relationship(back_populates="flight_tracker")
    offers: Mapped[list["FlightOffer"]] = relationship(back_populates="tracker", cascade="all, delete-orphan")


class FlightOffer(db.Model):
    """A normalized, minimal observation from one manual flight search."""

    __table_args__ = (
        UniqueConstraint("run_id", "fingerprint", name="flight_offer_run_fingerprint_unique"),
        CheckConstraint("category IN ('primary', 'secondary')", name="flight_offer_category_valid"),
        CheckConstraint("total_price_cents > 0", name="flight_offer_price_positive"),
        CheckConstraint("outbound_duration_minutes >= 0", name="flight_offer_outbound_duration_valid"),
        CheckConstraint("return_duration_minutes >= 0", name="flight_offer_return_duration_valid"),
        CheckConstraint("outbound_stops >= 0", name="flight_offer_outbound_stops_valid"),
        CheckConstraint("return_stops >= 0", name="flight_offer_return_stops_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("automation_run.id", ondelete="CASCADE"), nullable=False, index=True)
    tracker_id: Mapped[int] = mapped_column(ForeignKey("flight_tracker.id", ondelete="CASCADE"), nullable=False, index=True)
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    total_price_cents: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    outbound_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    return_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    outbound_stops: Mapped[int] = mapped_column(Integer, nullable=False)
    return_stops: Mapped[int] = mapped_column(Integer, nullable=False)
    airline_summary: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    itinerary_summary: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    provider_offer_reference: Mapped[str] = mapped_column(String(160), default="", server_default="", nullable=False)
    booking_url: Mapped[str] = mapped_column(String(1000), default="", server_default="", nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    run: Mapped[AutomationRun] = relationship(back_populates="offers")
    tracker: Mapped[FlightTracker] = relationship(back_populates="offers")
