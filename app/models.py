from datetime import date, datetime, time, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
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
    deadline_link: Mapped["Deadline | None"] = relationship(back_populates="source_journal_entry", uselist=False)
    upcoming_link: Mapped["UpcomingEvent | None"] = relationship(back_populates="source_journal_entry", uselist=False)


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


class RecurrenceRule(TimestampMixin, db.Model):
    """Standalone To-Do recurrence definition; project tasks intentionally do not use it."""
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    recurrence_type: Mapped[str] = mapped_column(String(16), nullable=False)
    interval: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    weekdays_json: Mapped[str] = mapped_column(String(32), default="", server_default="", nullable=False)
    day_of_month: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    rollover_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False, index=True)
    occurrences: Mapped[list["TaskOccurrence"]] = relationship(back_populates="rule", cascade="all, delete-orphan")


class TaskOccurrence(TimestampMixin, db.Model):
    """One generated obligation; its unique rule/date pair makes lazy generation idempotent."""
    __table_args__ = (UniqueConstraint("recurrence_rule_id", "due_date", name="uq_task_occurrence_rule_due_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recurrence_rule_id: Mapped[int] = mapped_column(ForeignKey("recurrence_rule.id"), nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rule: Mapped["RecurrenceRule"] = relationship(back_populates="occurrences")

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
    automation: Mapped[Automation] = relationship(back_populates="runs")

    @validates("status")
    def validate_status(self, _key, value):
        if value not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported automation run status: {value}")
        return value


class WeatherLocation(TimestampMixin, db.Model):
    """A location explicitly chosen by the local user for manual weather checks."""

    __table_args__ = (
        UniqueConstraint("display_name", "latitude", "longitude", name="weather_location_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str] = mapped_column(String(8), default="", server_default="", nullable=False)
    admin_area: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False, index=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cached_weather_json: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)


class CurrencyPair(TimestampMixin, db.Model):
    """A manually saved reference-rate pair with a compact local cache."""

    __table_args__ = (
        CheckConstraint("base_currency <> quote_currency", name="currency_pair_distinct"),
        UniqueConstraint("base_currency", "quote_currency", name="currency_pair_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False, index=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cached_rates_json: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)

    @validates("base_currency", "quote_currency")
    def validate_currency(self, _key, value):
        value = (value or "").strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("Currency codes must be three letters.")
        return value


BODY_PARTS = ("Chest", "Back", "Shoulders", "Biceps", "Triceps", "Legs", "Core", "Other")


class Exercise(TimestampMixin, db.Model):
    """A reusable exercise. Archiving retains all historical workout records."""

    __table_args__ = (
        CheckConstraint(
            "body_part IN ('Chest', 'Back', 'Shoulders', 'Biceps', 'Triceps', 'Legs', 'Core', 'Other')",
            name="exercise_body_part_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    body_part: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False, index=True)
    workout_exercises: Mapped[list["WorkoutExercise"]] = relationship(back_populates="exercise")

    @validates("body_part")
    def validate_body_part(self, _key, value):
        if value not in BODY_PARTS:
            raise ValueError("Choose a valid body part.")
        return value


class WorkoutSession(TimestampMixin, db.Model):
    """One workout occurrence. The UI resumes the unfinished session for today."""

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workout_exercises: Mapped[list["WorkoutExercise"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class WorkoutExercise(TimestampMixin, db.Model):
    """One exercise performed during one workout session."""

    __table_args__ = (
        UniqueConstraint("workout_session_id", "exercise_id", name="workout_exercise_session_exercise"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    session: Mapped[WorkoutSession] = relationship(back_populates="workout_exercises")
    exercise: Mapped[Exercise] = relationship(back_populates="workout_exercises")
    sets: Mapped[list["ExerciseSet"]] = relationship(
        back_populates="workout_exercise", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ExerciseSet.set_number",
    )


class ExerciseSet(TimestampMixin, db.Model):
    """A single completed set, stored independently for resilient workout logging."""

    __table_args__ = (
        CheckConstraint("weight_kg >= 0 AND weight_kg <= 1000", name="exercise_set_weight_range"),
        CheckConstraint("reps >= 1 AND reps <= 1000", name="exercise_set_reps_range"),
        UniqueConstraint("workout_exercise_id", "set_number", name="exercise_set_workout_exercise_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_exercise_id: Mapped[int] = mapped_column(
        ForeignKey("workout_exercise.id", ondelete="CASCADE"), nullable=False, index=True
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[object] = mapped_column(Numeric(8, 2), nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    workout_exercise: Mapped[WorkoutExercise] = relationship(back_populates="sets")


class Deadline(TimestampMixin, db.Model):
    """An independent, date-bound commitment; it deliberately does not create a Todo."""

    __table_args__ = (UniqueConstraint("source_journal_entry_id", name="uq_deadline_source_journal_entry_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="SET NULL"), index=True
    )
    source_journal_entry: Mapped[JournalEntry | None] = relationship(back_populates="deadline_link")


class UpcomingEvent(TimestampMixin, db.Model):
    """A date-bound event that naturally moves to Past after its event date."""

    __table_args__ = (UniqueConstraint("source_journal_entry_id", name="uq_upcoming_event_source_journal_entry_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_time: Mapped[time | None] = mapped_column(Time)
    source_journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="SET NULL"), index=True
    )
    source_journal_entry: Mapped[JournalEntry | None] = relationship(back_populates="upcoming_link")
